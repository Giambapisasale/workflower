"""M7 — instradamento documenti (classificatore T2) + entità DDT.

Prova l'invariante di Fase 2: una seconda entità gira sullo *stesso* runtime,
senza codice nuovo. E prova il classificatore che instrada l'upload al workflow
giusto (fattura vs DDT), auto-scoprendo i tipi dai manifest con blocco `ingest`.
"""

import shutil
from pathlib import Path

import pytest
from aiuti import accedi
from fake_llm import FakeCompleter
from fastapi.testclient import TestClient

from app import fixtures, fixtures_docs
from app.core.classificatore import Classificatore
from app.core.dal import DAL
from app.core.gateway import Gateway
from app.core.runtime import WorkflowRuntime

pytestmark = pytest.mark.usefixtures("ambiente_llm")


@pytest.fixture
def banco(dati_rw: Path, fixtures_dir: Path, fixtures_docs_dir: Path):
    """Repo dati scrivibile con una fattura e un DDT già copiati nei blob."""

    def prepara():
        ddt_spec = fixtures_docs.FIXTURES[0]
        ddt_doc = f"blobs/caricati/2026/{ddt_spec['file']}"
        (dati_rw / ddt_doc).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixtures_docs_dir / ddt_spec["file"], dati_rw / ddt_doc)
        ft_spec = fixtures.FIXTURES[0]
        ft_doc = f"blobs/caricati/2026/{ft_spec['file']}"
        shutil.copy(fixtures_dir / ft_spec["file"], dati_rw / ft_doc)
        dal = DAL(dati_rw)
        gateway = Gateway(completer=FakeCompleter(dati_rw), attesa_retry=0)
        return dal, gateway, ddt_doc, ft_doc

    return prepara


# ------------------------------------------------------------- classificatore


def test_catalogo_auto_scoperto_dai_manifest(banco) -> None:
    dal, gateway, *_ = banco()
    catalogo = Classificatore(dal, gateway).catalogo()
    per_label = {v["label"]: v for v in catalogo}
    assert {"fattura", "ddt"} <= set(per_label)
    assert per_label["ddt"]["workflow"] == "carica-ddt"
    assert per_label["fattura"]["workflow"] == "carica-fattura"


def test_classificatore_instrada_fattura_e_ddt(banco) -> None:
    dal, gateway, ddt_doc, ft_doc = banco()
    classificatore = Classificatore(dal, gateway)
    assert classificatore.workflow_per(ddt_doc) == "carica-ddt"
    assert classificatore.workflow_per(ft_doc) == "carica-fattura"


def test_classificatore_incerto_usa_il_fallback(banco) -> None:
    """Documento illeggibile → nessun errore all'operatore: si instrada al fallback."""
    dal, gateway, *_ = banco()
    assert Classificatore(dal, gateway).workflow_per("blobs/caricati/2026/inesistente.pdf") == (
        "carica-fattura"
    )


# --------------------------------------------------------- estrazione DDT (runtime)


def test_ddt_e2e_bozza_conforme_stesso_runtime(banco) -> None:
    dal, gateway, ddt_doc, _ = banco()
    esito = WorkflowRuntime(dal, gateway).esegui("carica-ddt", ddt_doc, run_id="run-ddt")

    assert esito.esito == "ok"
    assert esito.entity_id == "DDT-2026-0003"  # il seed arriva a 0002
    assert esito.stato == "bozza"

    ddt = dal.read("ddt", esito.entity_id)
    assert ddt.stato == "bozza"
    assert ddt.dati["fornitore_id"] == "FRN-002"
    assert ddt.dati["cantiere_id"] == "CNT-002"
    assert ddt.dati["numero"] == "778/T"
    assert ddt.dati["data"] == "2026-07-15"
    assert ddt.dati["causale"] == "Vendita"
    assert ddt.dati["riferimento_ordine"] == "ODA-2026-114"
    assert len(ddt.dati["righe"]) == 3
    assert ddt.dati["righe"][0]["unita_misura"] == "pz"
    assert ddt.meta.workflow == "carica-ddt@1.0"
    assert set(ddt.meta.confidence) == set(ddt.dati)


# --------------------------------------------------------- upload via API


def test_upload_ddt_instradato_dal_classificatore(
    client: TestClient, dati_rw: Path, fixtures_docs_dir: Path
) -> None:
    intestazioni = accedi(client, "giovanna")  # admin: nessun vincolo di cantiere
    ddt = fixtures_docs.FIXTURES[0]["file"]
    risposta = client.post(
        "/api/documents",
        headers=intestazioni,
        files={"file": (ddt, (fixtures_docs_dir / ddt).read_bytes(), "application/pdf")},
    )
    assert risposta.status_code == 200
    doc_id = risposta.json()["doc_id"]

    dal = DAL(dati_rw)
    documento = dal.read("documento", doc_id)
    assert documento.dati["workflow"] == "carica-ddt"  # instradato, non hard-coded
    assert documento.dati["entity_tipo"] == "ddt"
    assert documento.dati["entity_id"] == "DDT-2026-0003"
    ddt_entita = dal.read("ddt", documento.dati["entity_id"])
    assert ddt_entita.dati["cantiere_id"] == "CNT-002"
    assert not dal.repo.is_dirty(untracked_files=True)  # ogni mutazione committata


def test_ddt_in_coda_revisione(client: TestClient, fixtures_docs_dir: Path) -> None:
    intestazioni = accedi(client, "giovanna")
    ddt = fixtures_docs.FIXTURES[0]["file"]
    client.post(
        "/api/documents",
        headers=intestazioni,
        files={"file": (ddt, (fixtures_docs_dir / ddt).read_bytes(), "application/pdf")},
    )
    coda = client.get("/api/review", headers=intestazioni).json()["da_rivedere"]
    ddt_righe = [r for r in coda if r["tipo"] == "ddt"]
    assert ddt_righe and ddt_righe[0]["id"] == "DDT-2026-0003"
    assert ddt_righe[0]["cantiere"] == "Ristrutturazione Scuola Manzoni"
