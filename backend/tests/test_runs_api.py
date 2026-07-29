"""Elenco dei run e golden set: le due porte che l'interfaccia non aveva.

``GET /api/runs`` esisteva solo come ``/runs/{id}/trace``: per aprire un trace
bisognava già conoscere il run. Le esecuzioni fallite senza segnalazione — quelle
che si vogliono vedere — erano invisibili. ``GET /api/golden`` rende ispezionabile
la rete di regressione, e la ``DELETE`` permette di togliere un caso costruito su
un dato poi ripudiato.
"""

from pathlib import Path

import httpx
from aiuti import accedi
from fastapi.testclient import TestClient

from app.core.dal import DAL
from app.core.golden import carica_golden


def _carica(client: TestClient, headers: dict[str, str], percorso: Path) -> httpx.Response:
    return client.post(
        "/api/documents",
        headers=headers,
        files={"file": (percorso.name, percorso.read_bytes(), "application/pdf")},
    )


# ------------------------------------------------------------------ elenco run


def test_elenco_run_riassume_l_esecuzione(
    client: TestClient, dati_rw: Path, fixtures_dir: Path
) -> None:
    salvo = accedi(client, "salvo")
    corpo = _carica(client, salvo, fixtures_dir / "fattura-calcestruzzi-etna.pdf").json()
    run_id = corpo["run_id"]

    admin = accedi(client, "giovanna")
    run = client.get("/api/runs", headers=admin).json()["run"]
    voce = next(r for r in run if r["run_id"] == run_id)
    assert voce["workflow"] == "carica-fattura"
    assert voce["esito"] == "ok"
    assert voce["entity_id"] == DAL(dati_rw).read("documento", corpo["doc_id"]).dati["entity_id"]
    assert voce["input"].startswith("blobs/caricati/")
    assert voce["n_llm"] >= 1
    assert voce["durata_ms"] >= 0 and voce["costo_usd"] >= 0
    assert voce["ts"]

    # il trace dello stesso run è raggiungibile e coerente
    eventi = client.get(f"/api/runs/{run_id}/trace", headers=admin).json()["eventi"]
    tipi = {e["evento"] for e in eventi}
    assert {"run_start", "run_end"} <= tipi


def test_elenco_run_filtri_e_limite(client: TestClient, fixtures_dir: Path) -> None:
    salvo = accedi(client, "salvo")
    _carica(client, salvo, fixtures_dir / "fattura-calcestruzzi-etna.pdf")
    _carica(client, salvo, fixtures_dir / "fattura-edil-sud.pdf")
    admin = accedi(client, "giovanna")

    tutti = client.get("/api/runs", headers=admin).json()["run"]
    assert len(tutti) >= 2
    # dal più recente
    assert [r["ts"] for r in tutti] == sorted((r["ts"] for r in tutti), reverse=True)

    per_workflow = client.get("/api/runs?workflow=carica-fattura", headers=admin).json()["run"]
    assert per_workflow and all(r["workflow"] == "carica-fattura" for r in per_workflow)

    inesistente = client.get("/api/runs?workflow=non-esiste", headers=admin).json()["run"]
    assert inesistente == []

    riusciti = client.get("/api/runs?esito=ok", headers=admin).json()["run"]
    assert riusciti and all(r["esito"] == "ok" for r in riusciti)

    uno = client.get("/api/runs?limite=1", headers=admin).json()["run"]
    assert len(uno) == 1


def test_elenco_run_solo_admin(client: TestClient) -> None:
    op = accedi(client, "salvo")
    assert client.get("/api/runs", headers=op).status_code == 403
    assert client.get("/api/runs").status_code == 401


# ------------------------------------------------------------------ golden set


def test_golden_elenco_e_rimozione(client: TestClient, dati_rw: Path) -> None:
    admin = accedi(client, "giovanna")
    casi = client.get("/api/golden", headers=admin).json()["golden"]
    # il seed porta i due casi senza ritenuta: la rete minima dell'Improver
    assert len(casi) == 2
    assert all(c["workflow"] == "carica-fattura" for c in casi)
    assert all(c["originale_presente"] for c in casi), "l'originale deve essere rieseguibile"
    assert all(c["n_campi"] > 0 for c in casi)

    solo_uno = client.get("/api/golden?workflow=carica-fattura", headers=admin).json()["golden"]
    assert len(solo_uno) == 2
    assert client.get("/api/golden?workflow=non-esiste", headers=admin).json()["golden"] == []

    vittima = casi[0]["id"]
    assert client.delete(f"/api/golden/{vittima}", headers=admin).status_code == 200
    assert not any(g.id == vittima for g in carica_golden(dati_rw))
    assert client.delete(f"/api/golden/{vittima}", headers=admin).status_code == 404


def test_golden_solo_admin(client: TestClient) -> None:
    op = accedi(client, "salvo")
    assert client.get("/api/golden", headers=op).status_code == 403
    assert client.delete("/api/golden/GOLD-0001", headers=op).status_code == 403
    assert client.get("/api/golden").status_code == 401
