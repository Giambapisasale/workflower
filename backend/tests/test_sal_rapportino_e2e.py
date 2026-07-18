"""M8 — entità SAL e Rapportino Ore sullo stesso runtime; classificatore a 4 tipi.

Confermano l'invariante di Fase 2: due entità dato-only (avanzamento lavori e
manodopera), senza fornitore, girano sul runtime esistente. SAL e rapportino
usano solo `cerca_cantiere`: il fake segue i tool offerti dal manifest.
"""

import shutil
from pathlib import Path

import pytest
from aiuti import accedi
from fake_llm import FakeCompleter
from fastapi.testclient import TestClient

from app import fixtures_docs
from app.core.classificatore import Classificatore
from app.core.dal import DAL
from app.core.gateway import Gateway
from app.core.runtime import WorkflowRuntime
from app.core.views import query

pytestmark = pytest.mark.usefixtures("ambiente_llm")

PER_TIPO = {spec["tipo"]: spec for spec in fixtures_docs.FIXTURES}


@pytest.fixture
def banco(dati_rw: Path, fixtures_docs_dir: Path):
    """Copia una fixture di Fase 2 nel repo dati e prepara runtime + DAL col fake."""

    def prepara(tipo: str):
        spec = PER_TIPO[tipo]
        doc = f"blobs/caricati/2026/{spec['file']}"
        (dati_rw / doc).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fixtures_docs_dir / spec["file"], dati_rw / doc)
        dal = DAL(dati_rw)
        gateway = Gateway(completer=FakeCompleter(dati_rw), attesa_retry=0)
        return dal, WorkflowRuntime(dal, gateway), doc

    return prepara


# ------------------------------------------------------------- classificatore


def test_catalogo_quattro_tipi(banco) -> None:
    dal, _rt, _doc = banco("sal")
    classificatore = Classificatore(dal, Gateway(completer=FakeCompleter(dal.data_dir)))
    labels = {v["label"] for v in classificatore.catalogo()}
    assert {"fattura", "ddt", "sal", "rapportino"} <= labels


def test_classificatore_instrada_sal_e_rapportino(banco) -> None:
    dal, _rt, sal_doc = banco("sal")
    _dal2, _rt2, rap_doc = banco("rapportino")
    classificatore = Classificatore(dal, Gateway(completer=FakeCompleter(dal.data_dir)))
    assert classificatore.workflow_per(sal_doc) == "carica-sal"
    assert classificatore.workflow_per(rap_doc) == "carica-rapportino"


# --------------------------------------------------------------- SAL (runtime)


def test_sal_e2e_solo_cerca_cantiere(banco) -> None:
    dal, runtime, doc = banco("sal")
    esito = runtime.esegui("carica-sal", doc, run_id="run-sal")

    assert esito.esito == "ok"
    assert esito.entity_id == "SAL-2026-0003"  # il seed arriva a 0002
    sal = dal.read("sal", esito.entity_id)
    assert sal.dati["cantiere_id"] == "CNT-003"
    assert sal.dati["numero"] == "4"
    assert sal.dati["data"] == "2026-07-10"
    assert sal.dati["importo_lavori"] == 1980000.0
    assert sal.dati["importo_progressivo"] == 742500.0
    assert sal.dati["percentuale_avanzamento"] == 37.5
    assert "fornitore_id" not in sal.dati  # un SAL non ha fornitore
    assert sal.meta.workflow == "carica-sal@1.0"


# ------------------------------------------------------------ rapportino (rt)


def test_rapportino_e2e_ore_manodopera(banco) -> None:
    dal, runtime, doc = banco("rapportino")
    esito = runtime.esegui("carica-rapportino", doc, run_id="run-rap")

    assert esito.esito == "ok"
    assert esito.entity_id == "RAP-2026-0003"
    rap = dal.read("rapportino", esito.entity_id)
    assert rap.dati["cantiere_id"] == "CNT-001"
    assert rap.dati["data"] == "2026-07-13"
    assert len(rap.dati["righe"]) == 3
    prima = rap.dati["righe"][0]
    assert prima["nominativo"] == "Salvo Torrisi"
    assert prima["mansione"] == "Capocantiere"
    assert prima["ore"] == 8.0
    assert prima["costo_orario"] == 32.0


# ----------------------------------------------------------------- viste


def test_viste_sal_e_rapportini_dal_seed(dati_rw: Path) -> None:
    sal = query(dati_rw, "SELECT id, cantiere_id, percentuale_avanzamento FROM v_sal ORDER BY id")
    assert [r["id"] for r in sal] == ["SAL-2026-0001", "SAL-2026-0002"]

    rap = query(dati_rw, "SELECT id, ore_totali FROM v_rapportini ORDER BY id")
    assert rap[0]["id"] == "RAP-2026-0001"
    assert rap[0]["ore_totali"] == 24.0  # 8 + 8 + 8

    righe = query(
        dati_rw,
        "SELECT nominativo, ore, costo FROM v_rapportini_righe "
        "WHERE rapportino_id = 'RAP-2026-0001' ORDER BY nominativo",
    )
    costi = {r["nominativo"]: r["costo"] for r in righe}
    assert costi["Salvo Torrisi"] == 8 * 32.0
    assert costi["Mario Rossi"] == 8 * 26.5


# --------------------------------------------------------------- upload API


def test_upload_sal_e_rapportino_instradati(
    client: TestClient, dati_rw: Path, fixtures_docs_dir: Path
) -> None:
    intestazioni = accedi(client, "giovanna")
    attesi = {"sal": ("carica-sal", "sal"), "rapportino": ("carica-rapportino", "rapportino")}
    dal = DAL(dati_rw)
    for tipo, (workflow, entity_tipo) in attesi.items():
        nome = PER_TIPO[tipo]["file"]
        risposta = client.post(
            "/api/documents",
            headers=intestazioni,
            files={"file": (nome, (fixtures_docs_dir / nome).read_bytes(), "application/pdf")},
        )
        assert risposta.status_code == 200
        doc = dal.read("documento", risposta.json()["doc_id"])
        assert doc.dati["workflow"] == workflow
        assert doc.dati["entity_tipo"] == entity_tipo
