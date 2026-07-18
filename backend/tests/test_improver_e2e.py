"""Ciclo Improver (AC M5) — la *definition of done* della v1.

Scenario "ritenuta d'acconto": la v1.0 non la estrae → l'operatore segnala →
l'Improver propone una patch alla skill → il replay sul golden set regge →
l'admin approva → v1.1 → la riesecuzione estrae la ritenuta.

Questo test NON deve mai rompersi (CLAUDE.md).
"""

import shutil
from pathlib import Path
from typing import Any

import httpx
import yaml
from aiuti import accedi
from fake_improver import FakeCompleterImprover
from fake_llm import FakeCompleter
from fastapi.testclient import TestClient

from app.core.dal import DAL
from app.core.golden import carica_golden
from app.fixtures import FIXTURES, dati_attesi

STUDIO = next(f for f in FIXTURES if f["ritenuta"])  # la parcella con ritenuta


class FakeCompleterM5:
    """Un trasporto per due workflow: estrazione fattura + Improver."""

    def __init__(self, data_dir: Path, aggiunge_calce: bool = True) -> None:
        self.fattura = FakeCompleter(data_dir)
        self.improver = FakeCompleterImprover(aggiunge_calce=aggiunge_calce)

    def __call__(self, *, model: str, messages: list[dict[str, Any]], **kw: Any) -> Any:
        sistema = str(messages[0]["content"])
        if "Miglioramento del workflow" in sistema or "Giudizio di regressione" in sistema:
            return self.improver(model=model, messages=messages)
        return self.fattura(model=model, messages=messages, **kw)


def _versione_manifest(dati_rw: Path) -> str:
    percorso = dati_rw / "workflows" / "carica-fattura" / "manifest.yaml"
    return str(yaml.safe_load(percorso.read_text("utf-8"))["version"])


def _carica(client: TestClient, headers: dict[str, str], percorso: Path) -> httpx.Response:
    return client.post(
        "/api/documents",
        headers=headers,
        files={"file": (percorso.name, percorso.read_bytes(), "application/pdf")},
    )


def _aggiungi_golden_ritenuta(dati_rw: Path, fixtures_dir: Path) -> None:
    """Mette nel golden set il caso con ritenuta (atteso = ritenuta valorizzata)."""
    dal = DAL(dati_rw)
    origine = fixtures_dir / STUDIO["file"]
    destinazione = dati_rw / "blobs" / "golden" / STUDIO["file"]
    shutil.copy(origine, destinazione)
    dal.commit_paths([destinazione], "golden: originale con ritenuta [test]")
    dal.crea_golden(
        workflow="carica-fattura",
        version="1.0",
        doc=f"blobs/golden/{STUDIO['file']}",
        entity_tipo="fattura",
        atteso=dati_attesi(STUDIO),
        validato_da="test",
    )


# --------------------------------------------------------- definition of done


def test_scenario_ritenuta(crea_client, dati_rw: Path, fixtures_dir: Path) -> None:
    client = crea_client(FakeCompleterM5(dati_rw))
    salvo = accedi(client, "salvo")

    # 1. l'operatore carica la parcella: la v1.0 estrae senza la ritenuta
    corpo = _carica(client, salvo, fixtures_dir / STUDIO["file"]).json()
    doc_id = corpo["doc_id"]
    dal = DAL(dati_rw)
    entita_uno = dal.read("documento", doc_id).dati["entity_id"]
    assert dal.read("fattura", entita_uno).dati["ritenuta_acconto"] is None

    # 2. l'operatore segnala "manca la ritenuta"
    seg = client.post(
        f"/api/documents/{doc_id}/issue",
        json={"testo": "manca la ritenuta d'acconto, in fondo al foglio"},
        headers=salvo,
    ).json()
    issue_id = seg["issue_id"]

    # 3. l'ufficio avvia l'Improver: patch + replay sul golden
    admin = accedi(client, "giovanna")
    patch = client.post(
        "/api/workflows/carica-fattura/improve", json={"issue_id": issue_id}, headers=admin
    ).json()
    assert patch["stato"] == "proposta"
    assert patch["da_versione"] == "1.0" and patch["a_versione"] == "1.1"
    assert "calce" in patch["diff_skill"].lower()  # la patch aggiunge la ritenuta
    assert patch["replay"]["totale"] == 2 and patch["replay"]["ok"] == 2  # golden regge
    assert all(c["uguale"] for c in patch["replay"]["casi"])

    # 4. l'ufficio approva → v1.1 + riesecuzione del documento d'origine
    esito = client.post(f"/api/patches/{patch['id']}/approve", headers=admin).json()
    assert esito["versione"] == "1.1"
    assert esito["rerun"]["ritenuta"] == 800.0  # ORA la ritenuta viene estratta

    # 5. lo stato del mondo: manifest a 1.1, nuova bozza con ritenuta, issue chiusa
    assert _versione_manifest(dati_rw) == "1.1"
    entita_due = esito["rerun"]["entity_id"]
    assert entita_due != entita_uno
    assert dal.read("fattura", entita_due).dati["ritenuta_acconto"] == 800.0
    assert dal.leggi_issue(issue_id).stato == "chiusa"
    # il documento d'origine ora punta alla trascrizione corretta
    assert dal.read("documento", doc_id).dati["entity_id"] == entita_due


# ----------------------------------------------- il replay è una vera barriera


def test_replay_boccia_patch_che_non_risolve(
    crea_client, dati_rw: Path, fixtures_dir: Path
) -> None:
    """Con la ritenuta nel golden, una patch che NON la estrae fa fallire il replay."""
    _aggiungi_golden_ritenuta(dati_rw, fixtures_dir)
    client = crea_client(FakeCompleterM5(dati_rw, aggiunge_calce=False))
    salvo = accedi(client, "salvo")
    corpo = _carica(client, salvo, fixtures_dir / STUDIO["file"]).json()

    admin = accedi(client, "giovanna")
    patch = client.post(
        "/api/workflows/carica-fattura/improve",
        json={"run_id": corpo["run_id"], "feedback": "manca la ritenuta"},
        headers=admin,
    ).json()

    assert patch["replay"]["totale"] == 3  # 2 senza ritenuta + 1 con ritenuta
    assert patch["replay"]["ok"] == 2  # il caso con ritenuta non regge
    bocciato = next(c for c in patch["replay"]["casi"] if not c["uguale"])
    assert "ritenuta_acconto" in bocciato["differenze"]


# ------------------------------------------------------------- approva/rifiuta


def test_rifiuta_lascia_il_workflow_intatto(
    crea_client, dati_rw: Path, fixtures_dir: Path
) -> None:
    client = crea_client(FakeCompleterM5(dati_rw))
    salvo = accedi(client, "salvo")
    corpo = _carica(client, salvo, fixtures_dir / STUDIO["file"]).json()
    admin = accedi(client, "giovanna")
    patch = client.post(
        "/api/workflows/carica-fattura/improve",
        json={"run_id": corpo["run_id"]},
        headers=admin,
    ).json()

    rifiuto = client.post(f"/api/patches/{patch['id']}/reject", headers=admin)
    assert rifiuto.status_code == 200 and rifiuto.json()["stato"] == "rifiutata"

    assert _versione_manifest(dati_rw) == "1.0"  # nulla è cambiato
    # una patch già decisa non si riapprova
    assert client.post(f"/api/patches/{patch['id']}/approve", headers=admin).status_code == 409


def test_golden_cresce_con_le_validazioni(
    crea_client, dati_rw: Path, fixtures_dir: Path
) -> None:
    """Ponte M4→M5: validare una bozza aggiunge un caso al golden set."""
    client = crea_client(FakeCompleterM5(dati_rw))
    salvo = accedi(client, "salvo")
    corpo = _carica(client, salvo, fixtures_dir / "fattura-calcestruzzi-etna.pdf").json()
    entity_id = DAL(dati_rw).read("documento", corpo["doc_id"]).dati["entity_id"]

    prima = len(carica_golden(dati_rw, "carica-fattura"))
    admin = accedi(client, "giovanna")
    client.post(f"/api/review/{entity_id}/validate", headers=admin)
    assert len(carica_golden(dati_rw, "carica-fattura")) == prima + 1
