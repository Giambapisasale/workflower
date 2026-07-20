"""Gateway LLM: unico punto di accesso ai modelli (ADR-2).

I workflow dichiarano un *tier* (T1/T2), mai un modello: la mappa
tier → modello vive nelle variabili d'ambiente ``LLM_T1_MODEL`` /
``LLM_T2_MODEL``. Il trasporto è ``litellm.completion``, iniettabile nei
test; ogni chiamata riuscita finisce nel trace con token, costo e latenza.
"""

import json
import os
import time
from collections.abc import Callable
from typing import Any

import litellm
from litellm.exceptions import (
    APIConnectionError,
    InternalServerError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from pydantic import BaseModel

from app.core.tracer import Tracer

ERRORI_TRANSITORI = (
    APIConnectionError,
    InternalServerError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)


class GatewayError(Exception):
    """Errore del gateway (trasporto esaurito, risposta malformata)."""


class ModelloNonConfigurato(GatewayError):
    """Variabile d'ambiente del tier assente."""


class ToolCallRichiesta(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class RispostaLLM(BaseModel):
    text: str | None
    tool_calls: list[ToolCallRichiesta]
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int


class Gateway:
    def __init__(
        self,
        completer: Callable[..., Any] | None = None,
        max_retry: int = 2,
        attesa_retry: float = 0.5,
    ) -> None:
        self._completer = completer or litellm.completion
        self.max_retry = max_retry
        self.attesa_retry = attesa_retry

    def modello(self, tier: str) -> str:
        variabile = f"LLM_{tier}_MODEL"
        modello = os.environ.get(variabile)
        if not modello and tier == "T3":
            # Tier T3 (modello locale fine-tuned) predisposto ma non ancora attivo:
            # si ricade su T1. Il router sposterà i workflow su T3 quando LLM_T3_MODEL
            # sarà configurato, senza toccare i manifest (§3.1). Escalation su bassa
            # confidence/errore: lavoro futuro.
            modello = os.environ.get("LLM_T1_MODEL")
        if not modello:
            raise ModelloNonConfigurato(f"{variabile} non configurata (tier {tier})")
        return modello

    def t3_attivo(self) -> bool:
        """Vero se il tier locale T3 è cablato (``LLM_T3_MODEL`` impostato).

        È l'interruttore di §3.1: finché è spento, un workflow su T3 ricade su T1
        (comportamento invariato); acceso, il runtime instrada su T3 e — su
        errore/bassa confidence/output fuori contratto — escala a T1.
        """
        return bool(os.environ.get("LLM_T3_MODEL"))

    def complete(
        self,
        tier: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
        tracer: Tracer | None = None,
        step: str | None = None,
    ) -> RispostaLLM:
        """Una chiamata al tier richiesto, con retry sui soli errori transitori.

        ``response_schema`` attiva lo structured output nativo quando il
        provider lo supporta; in ogni caso il chiamante rivalida il JSON
        contro lo schema (§7: reparse con retry).
        """
        modello = self.modello(tier)
        kwargs: dict[str, Any] = {"model": modello, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        elif response_schema and self._supporta_response_schema(modello):
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": response_schema},
            }

        ultimo_errore: Exception | None = None
        for tentativo in range(self.max_retry + 1):
            partenza = time.monotonic()
            try:
                grezza = self._completer(**kwargs)
                break
            except ERRORI_TRANSITORI as exc:
                ultimo_errore = exc
                if tentativo < self.max_retry:
                    time.sleep(self.attesa_retry * (2**tentativo))
        else:
            raise GatewayError(
                f"LLM {modello} non raggiungibile dopo {self.max_retry + 1} tentativi: "
                f"{ultimo_errore}"
            ) from ultimo_errore

        latenza_ms = int((time.monotonic() - partenza) * 1000)
        risposta = self._normalizza(grezza, modello, latenza_ms)
        if tracer is not None:
            tracer.llm_call(
                step=step or "?",
                tier=tier,
                model=risposta.model,
                messages=messages,
                tokens_in=risposta.tokens_in,
                tokens_out=risposta.tokens_out,
                cost_usd=risposta.cost_usd,
                latency_ms=risposta.latency_ms,
            )
        return risposta

    # ------------------------------------------------------------- interni

    @staticmethod
    def _supporta_response_schema(modello: str) -> bool:
        try:
            return bool(litellm.supports_response_schema(model=modello))
        except Exception:
            return False

    @staticmethod
    def _normalizza(grezza: Any, modello: str, latenza_ms: int) -> RispostaLLM:
        """Riduce la risposta (litellm ModelResponse o dict equivalente)."""
        dati = grezza if isinstance(grezza, dict) else grezza.model_dump()
        try:
            messaggio = dati["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise GatewayError(f"risposta LLM malformata: {exc}") from exc

        tool_calls = []
        for indice, chiamata in enumerate(messaggio.get("tool_calls") or []):
            funzione = chiamata.get("function") or {}
            try:
                argomenti = json.loads(funzione.get("arguments") or "{}")
            except json.JSONDecodeError as exc:
                raise GatewayError(
                    f"argomenti non JSON per il tool {funzione.get('name')}: {exc}"
                ) from exc
            tool_calls.append(
                ToolCallRichiesta(
                    id=chiamata.get("id") or f"call_{indice}",
                    name=funzione.get("name") or "?",
                    arguments=argomenti,
                )
            )

        uso = dati.get("usage") or {}
        return RispostaLLM(
            text=messaggio.get("content"),
            tool_calls=tool_calls,
            model=dati.get("model") or modello,
            tokens_in=uso.get("prompt_tokens") or 0,
            tokens_out=uso.get("completion_tokens") or 0,
            cost_usd=_costo(grezza, dati),
            latency_ms=latenza_ms,
        )


def _costo(grezza: Any, dati: dict[str, Any]) -> float:
    """Costo in USD: litellm lo calcola per i modelli noti, altrimenti 0."""
    nascosti = getattr(grezza, "_hidden_params", None) or dati.get("_hidden_params") or {}
    costo = nascosti.get("response_cost")
    if costo is None:
        try:
            costo = litellm.completion_cost(completion_response=grezza)
        except Exception:
            costo = 0.0
    return float(costo or 0.0)


def estrai_json(testo: str) -> Any:
    """JSON dal testo del modello: tollera fence markdown e testo attorno."""
    pulito = testo.strip()
    if pulito.startswith("```"):
        righe = pulito.splitlines()
        if righe and righe[-1].strip().startswith("```"):
            righe = righe[:-1]
        pulito = "\n".join(righe[1:]).strip()
    try:
        return json.loads(pulito)
    except json.JSONDecodeError:
        pass
    inizio, fine = pulito.find("{"), pulito.rfind("}")
    if inizio == -1 or fine <= inizio:
        raise GatewayError("nessun JSON nella risposta del modello")
    try:
        return json.loads(pulito[inizio : fine + 1])
    except json.JSONDecodeError as exc:
        raise GatewayError(f"JSON non valido nella risposta del modello: {exc}") from exc
