"""API admin (AC M4): cruscotto, revisione→validazione→golden, segnalazioni, workflows.

RBAC: l'operatore non deve poter chiamare nessun endpoint admin (403).
"""

from pathlib import Path

import httpx
from aiuti import accedi
from fastapi.testclient import TestClient

from app.core.dal import DAL
from app.core.golden import carica_golden
from app.core.tracer import leggi_eventi


def _carica(client: TestClient, headers: dict[str, str], percorso: Path) -> httpx.Response:
    return client.post(
        "/api/documents",
        headers=headers,
        files={"file": (percorso.name, percorso.read_bytes(), "application/pdf")},
    )


# ------------------------------------------------------------------ cruscotto


def test_dashboard_costi(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    corpo = client.get("/api/dashboard/costs", headers=admin).json()
    assert corpo["totali"]["n_fatture"] == 5
    assert corpo["totali"]["ritenute"] == 800.0  # la parcella con ritenuta del seed
    assert corpo["totali"]["da_validare"] == 0  # il seed è tutto validato
    per_cantiere = {c["cantiere_id"]: c for c in corpo["per_cantiere"]}
    assert per_cantiere["CNT-001"]["speso"] == 15042.60
    assert 0 < per_cantiere["CNT-001"]["quota_budget"] < 1
    assert per_cantiere["CNT-001"]["residuo"] == round(1850000.0 - 15042.60, 2)


# --------------------------------------------------------------------- RBAC


def test_operatore_mai_su_endpoint_admin(client: TestClient) -> None:
    op = accedi(client, "salvo")
    for metodo, percorso in (
        ("get", "/api/dashboard/costs"),
        ("get", "/api/review"),
        ("get", "/api/review/FT-2026-0001"),
        ("post", "/api/review/FT-2026-0001/validate"),
        ("get", "/api/issues"),
        ("get", "/api/workflows"),
        ("get", "/api/runs/run-x/trace"),
    ):
        risposta = getattr(client, metodo)(percorso, headers=op)
        assert risposta.status_code == 403, f"{metodo} {percorso} → {risposta.status_code}"


# ------------------------------------------------------------ revisione + golden


def test_revisione_valida_e_copia_nel_golden(
    client: TestClient, dati_rw: Path, fixtures_dir: Path
) -> None:
    salvo = accedi(client, "salvo")
    corpo = _carica(client, salvo, fixtures_dir / "fattura-calcestruzzi-etna.pdf").json()
    entity_id = DAL(dati_rw).read("documento", corpo["doc_id"]).dati["entity_id"]

    admin = accedi(client, "giovanna")
    dettaglio = client.get(f"/api/review/{entity_id}", headers=admin).json()
    assert dettaglio["tipo"] == "fattura"
    assert dettaglio["confidence"]  # l'admin vede la confidence per campo
    assert dettaglio["blob"].startswith("blobs/caricati/")
    assert dettaglio["validato"] is False

    # la bozza è in coda di revisione…
    coda = client.get("/api/review", headers=admin).json()["da_rivedere"]
    assert any(v["id"] == entity_id for v in coda)

    prima = len(carica_golden(dati_rw))
    esito = client.post(f"/api/review/{entity_id}/validate", headers=admin)
    assert esito.status_code == 200
    assert esito.json()["stato"] == "validato"
    assert esito.json()["golden_id"] is not None

    # dietro le quinte: stato validato, autore ufficio, nuovo caso golden
    fattura = DAL(dati_rw).read("fattura", entity_id)
    assert fattura.stato == "validato" and fattura.meta.validato_da == "giovanna"
    golden = carica_golden(dati_rw)
    assert len(golden) == prima + 1
    nuovo = next(g for g in golden if g.entity_id == entity_id)
    assert nuovo.atteso["totale"] == 10162.60
    assert (dati_rw / nuovo.doc).is_file()  # l'originale è rieseguibile

    # …e sparisce dalla coda
    coda = client.get("/api/review", headers=admin).json()["da_rivedere"]
    assert not any(v["id"] == entity_id for v in coda)


def test_feedback_campo_sul_trace(
    client: TestClient, dati_rw: Path, fixtures_dir: Path
) -> None:
    salvo = accedi(client, "salvo")
    corpo = _carica(client, salvo, fixtures_dir / "fattura-studio-bianchi.pdf").json()
    entity_id = DAL(dati_rw).read("documento", corpo["doc_id"]).dati["entity_id"]

    admin = accedi(client, "giovanna")
    risposta = client.post(
        f"/api/review/{entity_id}/feedback",
        json={"campo": "ritenuta_acconto", "nota": "manca la ritenuta in calce"},
        headers=admin,
    )
    assert risposta.status_code == 200

    eventi = leggi_eventi(dati_rw, corpo["run_id"], {"field_feedback"})
    assert eventi and eventi[0]["campo"] == "ritenuta_acconto"
    assert eventi[0]["utente"] == "giovanna"
    # e la revisione lo rilegge
    dettaglio = client.get(f"/api/review/{entity_id}", headers=admin).json()
    assert dettaglio["feedback"][0]["nota"] == "manca la ritenuta in calce"


def test_review_originale_scaricabile(
    client: TestClient, dati_rw: Path, fixtures_dir: Path
) -> None:
    salvo = accedi(client, "salvo")
    corpo = _carica(client, salvo, fixtures_dir / "fattura-calcestruzzi-etna.pdf").json()
    entity_id = DAL(dati_rw).read("documento", corpo["doc_id"]).dati["entity_id"]

    admin = accedi(client, "giovanna")
    risposta = client.get(f"/api/review/{entity_id}/originale", headers=admin)
    assert risposta.status_code == 200
    assert risposta.headers["content-type"] == "application/pdf"
    assert risposta.content[:4] == b"%PDF"


# ---------------------------------------------------------------- segnalazioni


def test_coda_segnalazioni_e_chiusura(
    client: TestClient, dati_rw: Path, fixtures_dir: Path
) -> None:
    salvo = accedi(client, "salvo")
    corpo = _carica(client, salvo, fixtures_dir / "fattura-studio-bianchi.pdf").json()
    client.post(
        f"/api/documents/{corpo['doc_id']}/issue",
        json={"testo": "manca la ritenuta d'acconto in fondo"},
        headers=salvo,
    )

    admin = accedi(client, "giovanna")
    issues = client.get("/api/issues", headers=admin).json()["issues"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue["origine"] == "operatore" and issue["stato"] == "aperta"
    assert issue["entita"]["tipo"] == "fattura"  # arricchita con l'entità
    assert issue["entita"]["fornitore"] == "Studio Tecnico Ing. Bianchi"

    chiusura = client.post(f"/api/issues/{issue['id']}/close", headers=admin)
    assert chiusura.status_code == 200 and chiusura.json()["stato"] == "chiusa"
    aperte = client.get("/api/issues?stato=aperta", headers=admin).json()["issues"]
    assert aperte == []


# ------------------------------------------------------------------ workflows


def test_workflows_e_trace(client: TestClient, dati_rw: Path, fixtures_dir: Path) -> None:
    salvo = accedi(client, "salvo")
    corpo = _carica(client, salvo, fixtures_dir / "fattura-calcestruzzi-etna.pdf").json()

    admin = accedi(client, "giovanna")
    elenco = client.get("/api/workflows", headers=admin).json()["workflows"]
    workflows = {w["name"]: w for w in elenco}
    carica = workflows["carica-fattura"]
    assert carica["version"] == "1.0"
    assert carica["golden"] == 2  # i due casi del seed
    assert carica["stats"]["ok"] >= 1  # il run appena eseguito

    trace = client.get(f"/api/runs/{corpo['run_id']}/trace", headers=admin)
    assert trace.status_code == 200
    tipi = {e["evento"] for e in trace.json()["eventi"]}
    assert {"run_start", "run_end"} <= tipi
    assert client.get("/api/runs/run-inesistente/trace", headers=admin).status_code == 404
