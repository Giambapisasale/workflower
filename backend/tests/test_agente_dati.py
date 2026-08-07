"""Agente dati: tool-only, conversazione persistente e perimetro cantiere."""

from __future__ import annotations

import json
from typing import Any

from aiuti import accedi
from fastapi.testclient import TestClient

from app.core.agente_dati import (
    RISPOSTA_NON_COPERTA,
    EvolutoreAgente,
    RegistryToolDati,
    _risposta_pubblica,
)


class CompleterAgente:
    def __init__(self) -> None:
        self.system: str | None = None

    def __call__(self, *, model: str, messages: list[dict[str, Any]], **_kw: Any) -> dict[str, Any]:
        self.system = str(messages[0]["content"])
        if not any(m.get("role") == "tool" for m in messages):
            messaggio: dict[str, Any] = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-cantieri",
                        "type": "function",
                        "function": {"name": "cerca_cantieri", "arguments": '{"cerca": null}'},
                    }
                ],
            }
        else:
            messaggio = {"role": "assistant", "content": "Ho trovato il cantiere che ti riguarda."}
        return {
            "choices": [{"message": messaggio}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "model": model,
            "_hidden_params": {"response_cost": 0.0},
        }


class CompleterProposta:
    def __call__(self, *, model: str, **_kw: Any) -> dict[str, Any]:
        proposta = {
            "analisi": "manca un riepilogo minimale dei cantieri",
            "motivazione": "lettura limitata e verificabile",
            "intenti": ["contare i cantieri"],
            "parametri": [],
            "esempi": ["quanti cantieri ci sono?"],
            "risultato_atteso": "un elenco breve di cantieri",
            "tool": {
                "name": "collaudo_cantieri",
                "description": "Mostra i cantieri per il collaudo della proposta.",
                "roles": ["admin"],
                "scope": "globale",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                "implementation": {
                    "source": "cantieri",
                    "filters": [],
                    "aggregations": [],
                    "ordering": "nome",
                },
                "test": {"arguments": {}, "role": "admin", "cantieri": [], "min_results": 1},
            },
            "skill": None,
        }
        return {
            "choices": [{"message": {"role": "assistant", "content": json.dumps(proposta)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "model": model,
            "_hidden_params": {"response_cost": 0.0},
        }


def test_registry_ha_15_tool_e_non_esporta_l_implementazione(dati_rw) -> None:
    registry = RegistryToolDati(dati_rw)
    elenco = registry.elenco("admin", [])
    assert len(elenco) == 15
    assert all("query" not in tool for tool in elenco)
    schemi = registry.schemi("admin", [])
    assert len(schemi) == 15
    assert all("SELECT" not in str(schema) for schema in schemi)


def test_tutte_le_famiglie_compilano_dalla_dsl(dati_rw) -> None:
    registry = RegistryToolDati(dati_rw)
    for tool in registry.elenco_admin():
        proprieta = tool["parameters"].get("properties", {})
        argomenti = {nome: None for nome in proprieta}
        risultato = registry.esegui_spec(tool, argomenti, "admin", [])
        assert set(risultato) == {"risultati", "troncato"}


def test_risposta_non_mostra_dettagli_sql() -> None:
    assert _risposta_pubblica("Eseguo SELECT da v_cantieri") == RISPOSTA_NON_COPERTA


def test_skill_proposta_non_reintroduce_dettagli_tecnici() -> None:
    verifica = EvolutoreAgente._verifica_skill(
        {"name": "risposta_sicura", "content": "usa SELECT per cercare i dati"}
    )
    assert verifica["ok"] is False


def test_tool_operatore_filtra_il_cantiere_sul_server(dati_rw) -> None:
    registry = RegistryToolDati(dati_rw)
    risultato = registry.esegui("riepilogo_costi", {}, "op", ["CNT-001"])
    assert risultato["risultati"]
    assert {r["cantiere_id"] for r in risultato["risultati"]} == {"CNT-001"}
    nomi_operatore = {
        schema["function"]["name"]
        for schema in registry.schemi("op", ["CNT-001"])
    }
    assert "cerca_fornitori" not in nomi_operatore


def test_chat_persistente_tracciata_e_senza_sql_nel_prompt(crea_client) -> None:
    fake = CompleterAgente()
    client: TestClient = crea_client(fake)
    op = accedi(client, "salvo")

    risposta = client.post("/api/agent/messages", headers=op, json={"content": "Dove lavoro?"})
    assert risposta.status_code == 200, risposta.text
    corpo = risposta.json()
    assert corpo["answer"] == "Ho trovato il cantiere che ti riguarda."
    assert corpo["used_tools"] == []
    assert [m["role"] for m in corpo["messages"]] == ["user", "assistant"]
    assert fake.system is not None and "SQL" not in fake.system.upper()

    conversazione = client.get("/api/agent/conversation", headers=op).json()
    assert conversazione["messages"] == corpo["messages"]
    assert client.post("/api/agent/conversation/reset", headers=op).json()["messages"] == []


def test_limite_memoria_amministrabile_e_isolato_per_utente(crea_client) -> None:
    client = crea_client(CompleterAgente())
    admin = accedi(client, "giovanna")
    op = accedi(client, "salvo")
    assert client.put("/api/agent/config", headers=op, json={"max_messages": 6}).status_code == 403
    for i in range(4):
        risposta = client.post("/api/agent/messages", headers=op, json={"content": f"domanda {i}"})
        assert risposta.status_code == 200
    assert client.put("/api/agent/config", headers=admin, json={"max_messages": 6}).json() == {
        "max_messages": 6
    }
    assert len(client.get("/api/agent/conversation", headers=op).json()["messages"]) == 6
    assert client.get("/api/agent/conversation", headers=admin).json()["messages"] == []


def test_endpoint_storici_ritornano_gone(crea_client) -> None:
    client = crea_client(CompleterAgente())
    admin = accedi(client, "giovanna")
    for percorso in ("/api/ask", "/api/golden/domande", "/api/dataset/consolida", "/api/dataset/consolida-tool"):
        risposta = client.post(percorso, headers=admin, json={})
        assert risposta.status_code == 410


def test_proposta_tool_viene_collaudata_e_bloccata_se_i_golden_regrediscono(
    crea_client, monkeypatch
) -> None:
    client = crea_client(CompleterProposta())
    admin = accedi(client, "giovanna")
    monkeypatch.setattr(
        EvolutoreAgente,
        "_replay_golden",
        lambda _self: {"totale": 90, "ok": 90, "falliti": 0},
    )
    proposta = client.post(
        "/api/agent/evolution/proposals",
        headers=admin,
        json={"feedback": "mi serve il conteggio dei cantieri"},
    ).json()
    assert proposta["compilazione"] == {"ok": True, "righe": 3, "minimo": 1}
    approvata = client.post(
        f"/api/agent/evolution/proposals/{proposta['id']}/approve", headers=admin
    )
    assert approvata.status_code == 200, approvata.text
    assert len(client.get("/api/agent/evolution", headers=admin).json()["tools"]) == 16

    monkeypatch.setattr(
        EvolutoreAgente,
        "_replay_golden",
        lambda _self: {"totale": 90, "ok": 89, "falliti": 1},
    )
    bloccata = client.post(
        "/api/agent/evolution/proposals",
        headers=admin,
        json={"feedback": "stessa lacuna ma golden non verdi"},
    ).json()
    risposta = client.post(
        f"/api/agent/evolution/proposals/{bloccata['id']}/approve", headers=admin
    )
    assert risposta.status_code == 409
