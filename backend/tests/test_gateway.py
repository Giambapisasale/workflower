"""Gateway LLM: tier da env, retry sui transitori, normalizzazione, trace."""

import json
from pathlib import Path

import pytest
from litellm.exceptions import AuthenticationError, RateLimitError

from app.core.gateway import Gateway, GatewayError, ModelloNonConfigurato, estrai_json
from app.core.tracer import Tracer

MESSAGGI = [{"role": "user", "content": "ciao"}]


def _finale(testo: str = "ok") -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": testo}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        "model": "test/finto-t1",
        "_hidden_params": {"response_cost": 0.0042},
    }


def _rate_limit() -> RateLimitError:
    return RateLimitError("troppe richieste", llm_provider="test", model="finto")


def test_modello_del_tier_da_env(ambiente_llm: None) -> None:
    gateway = Gateway(completer=lambda **kw: _finale())
    assert gateway.modello("T1") == "test/finto-t1"
    assert gateway.modello("T2") == "test/finto-t2"


def test_tier_non_configurato(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_T9_MODEL", raising=False)
    with pytest.raises(ModelloNonConfigurato):
        Gateway(completer=lambda **kw: _finale()).modello("T9")


def test_retry_sui_transitori_poi_successo(ambiente_llm: None) -> None:
    guasti = [_rate_limit(), _rate_limit()]
    chiamate = 0

    def completer(**kw):
        nonlocal chiamate
        chiamate += 1
        if guasti:
            raise guasti.pop(0)
        return _finale()

    gateway = Gateway(completer=completer, max_retry=2, attesa_retry=0)
    risposta = gateway.complete("T1", MESSAGGI)
    assert risposta.text == "ok"
    assert chiamate == 3


def test_trasporto_esaurito_solleva_gateway_error(ambiente_llm: None) -> None:
    def completer(**kw):
        raise _rate_limit()

    gateway = Gateway(completer=completer, max_retry=1, attesa_retry=0)
    with pytest.raises(GatewayError, match="dopo 2 tentativi"):
        gateway.complete("T1", MESSAGGI)


def test_errore_non_transitorio_passa_subito(ambiente_llm: None) -> None:
    chiamate = 0

    def completer(**kw):
        nonlocal chiamate
        chiamate += 1
        raise AuthenticationError("chiave errata", llm_provider="test", model="finto")

    gateway = Gateway(completer=completer, max_retry=2, attesa_retry=0)
    with pytest.raises(AuthenticationError):
        gateway.complete("T1", MESSAGGI)
    assert chiamate == 1  # niente retry: riprovare non aggiusta una chiave


def test_normalizzazione_e_trace(ambiente_llm: None, tmp_path: Path) -> None:
    tracer = Tracer(tmp_path, "run-test", "wf", "1.0")
    gateway = Gateway(completer=lambda **kw: _finale("risposta"))
    risposta = gateway.complete("T1", MESSAGGI, tracer=tracer, step="estrai")

    assert risposta.text == "risposta"
    assert (risposta.tokens_in, risposta.tokens_out) == (10, 5)
    assert risposta.cost_usd == 0.0042
    assert risposta.tool_calls == []

    eventi = [json.loads(riga) for riga in tracer.trace_path.read_text().splitlines()]
    assert [e["evento"] for e in eventi] == ["llm_call"]
    evento = eventi[0]
    assert evento["tier"] == "T1"
    assert evento["step"] == "estrai"
    assert evento["model"] == "test/finto-t1"
    assert evento["cost_usd"] == 0.0042
    assert evento["latency_ms"] >= 0
    assert evento["messages_digest"]


def test_normalizzazione_tool_calls(ambiente_llm: None) -> None:
    risposta_llm = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "cerca_fornitore",
                                "arguments": '{"query": "Edil Sud"}',
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        "model": "test/finto-t1",
    }
    gateway = Gateway(completer=lambda **kw: risposta_llm)
    risposta = gateway.complete("T1", MESSAGGI)
    assert risposta.text is None
    assert len(risposta.tool_calls) == 1
    assert risposta.tool_calls[0].name == "cerca_fornitore"
    assert risposta.tool_calls[0].arguments == {"query": "Edil Sud"}


def test_reasoning_effort_none_con_i_tool(ambiente_llm: None) -> None:
    """Con function tools i modelli reasoning (gpt-5.x) richiedono reasoning_effort='none'."""
    visti: dict = {}

    def completer(**kw):
        visti.update(kw)
        return _finale()

    tools = [{"type": "function", "function": {"name": "ocr_pdf", "parameters": {}}}]
    Gateway(completer=completer).complete("T1", MESSAGGI, tools=tools)
    assert visti["reasoning_effort"] == "none"
    assert visti["tool_choice"] == "auto"

    # Senza tool NON si tocca il reasoning (Improver/giudizio/text-to-SQL restano SOTA).
    visti.clear()
    Gateway(completer=completer).complete("T1", MESSAGGI)
    assert "reasoning_effort" not in visti


def test_estrai_json_tollerante() -> None:
    assert estrai_json('{"a": 1}') == {"a": 1}
    assert estrai_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert estrai_json('Ecco il risultato:\n{"a": {"b": 2}}\nfine') == {"a": {"b": 2}}
    with pytest.raises(GatewayError):
        estrai_json("nessun json qui")
