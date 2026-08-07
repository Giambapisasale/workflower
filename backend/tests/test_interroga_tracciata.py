"""Ogni interrogazione è un run tracciato come quelle sui documenti.

Prima ``/ask`` non lasciava traccia, e la conseguenza non era solo estetica: il
costo delle domande non compariva da nessuna parte, le domande degli **operatori**
non venivano nemmeno contate (solo quelle dell'ufficio), e non c'era materia
prima per misurare un tier locale sull'interrogazione.

Il rovescio della medaglia da tenere d'occhio: sommando le interrogazioni al
costo totale, il "costo per documento" diventerebbe una media fra due cose
diverse. I due costi restano separati.
"""

import json
from collections.abc import Callable
from pathlib import Path

from aiuti import accedi
from fake_ask import FakeCompleterInterroga
from fastapi.testclient import TestClient

from app.core.dataset import statistiche

import pytest

pytestmark = pytest.mark.skip(reason="trace storico: l'agente dati è coperto da test_agente_dati")

CANTIERI = "SELECT id, nome FROM v_cantieri ORDER BY id LIMIT 10"


def _eventi(dati: Path) -> list[dict]:
    """Tutti gli eventi di tutti i trace del repo (i run sono pochi, nei test)."""
    eventi = []
    for trace in (dati / "traces").glob("*/*/*.jsonl"):
        for riga in trace.read_text(encoding="utf-8").splitlines():
            if riga.strip():
                eventi.append(json.loads(riga))
    return eventi


def _trace_interroga(dati: Path) -> list[dict]:
    """Gli eventi dei soli run del workflow ``interroga``, in ordine."""
    run = {
        e["run_id"]
        for e in _eventi(dati)
        if e.get("evento") == "run_start" and e.get("workflow") == "interroga"
    }
    return [e for e in _eventi(dati) if e.get("run_id") in run]


# --------------------------------------------------------------- il trace


def test_ask_admin_apre_un_run_tracciato(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    admin = accedi(client, "giovanna")
    corpo = client.post(
        "/api/ask", json={"question": "quali cantieri abbiamo?", "mode": "admin"}, headers=admin
    ).json()

    assert corpo["run_id"].startswith("run-")
    eventi = {e["evento"]: e for e in _trace_interroga(dati_rw)}
    assert eventi["run_start"]["workflow"] == "interroga"
    # dove per un documento c'è il blob, qui c'è la domanda: è ciò che il run elabora
    assert eventi["run_start"]["input"] == "quali cantieri abbiamo?"
    assert eventi["llm_call"]["step"] == "genera_sql"
    assert eventi["query"]["righe"] > 0
    assert eventi["query"]["fingerprint"]
    assert eventi["run_end"]["outcome"] == "ok"


def test_ask_operatore_traccia_le_due_chiamate(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    """L'operatore costa due chiamate: la query e la frase. Devono stare sullo stesso run."""
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    op = accedi(client, "salvo")
    client.post("/api/ask", json={"question": "quanti cantieri?"}, headers=op)

    eventi = _trace_interroga(dati_rw)
    passi = [e["step"] for e in eventi if e["evento"] == "llm_call"]
    assert passi == ["genera_sql", "risposta_operatore"]
    assert len({e["run_id"] for e in eventi}) == 1  # un run, non due


def test_una_query_rifiutata_chiude_il_run_in_errore(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    """Il fallimento va tracciato: un run senza esito sarebbe un buco nei conti."""
    client = crea_client(FakeCompleterInterroga("DELETE FROM v_fatture"))
    admin = accedi(client, "giovanna")
    risposta = client.post(
        "/api/ask", json={"question": "cancella tutto", "mode": "admin"}, headers=admin
    )
    assert risposta.status_code == 400

    fine = [e for e in _trace_interroga(dati_rw) if e["evento"] == "run_end"]
    assert [e["outcome"] for e in fine] == ["errore"]
    # il motivo del rifiuto resta sul trace, ed è il primo guardrail a scattare
    assert "solo query di lettura" in fine[0]["errore"]


def test_l_operatore_non_vede_l_errore_ma_il_run_lo_registra(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    """Contratto UI: mai un errore tecnico all'operatore. Nei log invece sì."""
    client = crea_client(FakeCompleterInterroga("DROP TABLE v_fatture"))
    op = accedi(client, "salvo")
    corpo = client.post("/api/ask", json={"question": "e adesso?"}, headers=op).json()

    assert "Non sono riuscito" in corpo["risposta"]
    fine = [e for e in _trace_interroga(dati_rw) if e["evento"] == "run_end"]
    assert [e["outcome"] for e in fine] == ["errore"]


# ------------------------------------------------------- il dataset delle query


def test_anche_le_domande_degli_operatori_finiscono_nel_dataset(
    crea_client: Callable[..., TestClient],
) -> None:
    """Erano il buco più grosso: le domande più vere non venivano contate.

    ``registra_query`` stava nell'endpoint, nel ramo ``admin``. Le domande degli
    operatori — quelle su cui si dovrebbe consolidare (§3.6) — passavano invisibili.
    """
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    op = accedi(client, "salvo")
    client.post("/api/ask", json={"question": "quanti cantieri?"}, headers=op)

    admin = accedi(client, "giovanna")
    gruppi = client.get("/api/dataset/queries", headers=admin).json()["gruppi"]
    assert sum(g["conteggio"] for g in gruppi) == 1


# ------------------------------------------------------------------- i costi


def test_le_interrogazioni_non_gonfiano_il_costo_per_documento(
    crea_client: Callable[..., TestClient], dati_rw: Path, fixtures_dir: Path
) -> None:
    """Due costi separati: uno per documento elaborato, uno per domanda posta."""
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    admin = accedi(client, "giovanna")
    prima = statistiche(dati_rw)

    for i in range(3):
        client.post(
            "/api/ask", json={"question": f"domanda {i}", "mode": "admin"}, headers=admin
        )

    dopo = statistiche(dati_rw)
    assert dopo["interrogazioni"] == 3
    assert dopo["costo_interrogazioni_usd"] > 0
    # il costo dei documenti non si muove: nessun documento è stato elaborato
    assert dopo["costo_documenti_usd"] == prima["costo_documenti_usd"]
    assert dopo["costo_per_documento_usd"] == prima["costo_per_documento_usd"]
    # e il totale invece sì: le domande costano, e il totale è il totale
    assert dopo["costo_totale_usd"] > prima["costo_totale_usd"]
    assert dopo["costo_per_interrogazione_usd"] > 0
    assert dopo["run_per_workflow"]["interroga"] == 3
