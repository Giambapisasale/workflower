"""End-to-end del workflow carica-fattura con il modello fake (AC M2).

Il fake (tests/fake_llm.py) legge davvero il PDF e segue davvero la skill:
tutto il resto — runtime, gateway, tool, tracer, DAL, regole — è codice vero.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from fake_llm import FakeCompleter
from git import Repo
from litellm.exceptions import AuthenticationError

from app.core.dal import DAL
from app.core.gateway import Gateway
from app.core.runtime import WorkflowRuntime
from app.fixtures import FIXTURES

pytestmark = pytest.mark.usefixtures("ambiente_llm")


@pytest.fixture
def banco(dati_rw: Path, fixtures_dir: Path):
    """Banco di prova: repo dati scrivibile + costruttore del runtime col fake."""

    def prepara(indice: int = 0, **opzioni_fake: Any):
        spec = FIXTURES[indice]
        doc = f"blobs/fatture/2026/{spec['file']}"
        shutil.copy(fixtures_dir / spec["file"], dati_rw / doc)
        dal = DAL(dati_rw)
        fake = FakeCompleter(dati_rw, **opzioni_fake)
        runtime = WorkflowRuntime(dal, Gateway(completer=fake, attesa_retry=0))
        return runtime, dal, fake, doc

    return prepara


def _eventi_trace(dati_rw: Path, run_id: str) -> list[dict[str, Any]]:
    percorsi = list(dati_rw.glob(f"traces/*/*/{run_id}.jsonl"))
    assert len(percorsi) == 1, f"trace di {run_id} non trovato"
    return [json.loads(riga) for riga in percorsi[0].read_text(encoding="utf-8").splitlines()]


def _righe_dataset(dati_rw: Path, run_id: str) -> list[dict[str, Any]]:
    contenuto = (dati_rw / "dataset" / "toolcalls.jsonl").read_text(encoding="utf-8")
    righe = [json.loads(riga) for riga in contenuto.splitlines() if riga.strip()]
    return [riga for riga in righe if riga["run_id"] == run_id]


# ------------------------------------------------------------- percorso felice


def test_e2e_bozza_conforme_trace_e_dataset(banco, dati_rw: Path) -> None:
    runtime, dal, fake, doc = banco(indice=0)
    esito = runtime.esegui("carica-fattura", doc, run_id="run-e2e")

    assert esito.esito == "ok"
    assert esito.entity_id == "FT-2026-0006"  # il seed arriva a 0005
    assert esito.stato == "bozza"
    assert esito.richiede_revisione is False
    assert fake.chiamate == 4  # ocr + 2 ricerche + risposta finale

    envelope = dal.read("fattura", "FT-2026-0006")
    dati = envelope.dati
    assert envelope.stato == "bozza"
    assert dati["fornitore_id"] == "FRN-001"
    assert dati["cantiere_id"] == "CNT-001"
    assert dati["numero"] == "112/2026"
    assert dati["data"] == "2026-07-05"
    assert (dati["imponibile"], dati["iva"], dati["totale"]) == (8330.0, 1832.6, 10162.6)
    assert dati["ritenuta_acconto"] is None
    assert len(dati["righe"]) == 2
    assert envelope.meta.workflow == "carica-fattura@1.0"
    assert envelope.meta.run_id == "run-e2e"
    assert envelope.meta.origine == doc
    # confidence per campo presente (AC M2): una voce per ogni campo di 1° livello
    assert set(envelope.meta.confidence) == set(dati)

    eventi = _eventi_trace(dati_rw, "run-e2e")
    tipi = [evento["evento"] for evento in eventi]
    assert tipi[0] == "run_start"
    assert tipi[-1] == "run_end"
    assert tipi.count("llm_call") == 4
    assert eventi[-1]["outcome"] == "ok"
    assert eventi[-1]["entity_id"] == "FT-2026-0006"

    chiamate_tool = [evento for evento in eventi if evento["evento"] == "tool_call"]
    assert [chiamata["name"] for chiamata in chiamate_tool] == [
        "ocr_pdf",
        "cerca_fornitore",
        "cerca_cantiere",
        "salva_bozza",
    ]
    assert all(chiamata["ok"] for chiamata in chiamate_tool)

    chiamate_llm = [evento for evento in eventi if evento["evento"] == "llm_call"]
    assert all(evento["cost_usd"] == 0.0021 for evento in chiamate_llm)
    assert all(evento["tier"] == "T1" for evento in chiamate_llm)
    assert all(evento["tokens_in"] > 0 for evento in chiamate_llm)

    validazioni = [evento for evento in eventi if evento["evento"] == "validation"]
    assert [validazione["esito"] for validazione in validazioni] == ["ok"]

    # dataset: una riga per tool call, col contesto, e senza base64 in chiaro
    righe = _righe_dataset(dati_rw, "run-e2e")
    assert [riga["tool_call"]["name"] for riga in righe] == [
        "ocr_pdf",
        "cerca_fornitore",
        "cerca_cantiere",
        "salva_bozza",
    ]
    assert all(riga["workflow"] == "carica-fattura@1.0" for riga in righe)
    assert righe[1]["messages"], "contesto per il fine-tuning assente"
    assert righe[0]["result"]["immagini_png_base64"][0].startswith("<"), "base64 nel dataset"

    # ogni mutazione è un commit: bozza + artefatti del run
    messaggi = [commit.message.strip() for commit in Repo(dati_rw).iter_commits(max_count=5)]
    assert "fattura FT-2026-0006: crea [run-e2e]" in messaggi
    assert "trace run-e2e: registra artefatti [run-e2e]" in messaggi


# --------------------------------------------------------- scenario ritenuta M5


def test_ritenuta_in_calce_non_estratta_dalla_v1_0(banco, dati_rw: Path) -> None:
    """Seme dello scenario M5: il documento la riporta, la skill v1.0 la ignora."""
    runtime, dal, fake, doc = banco(indice=2)
    with pymupdf.open(dati_rw / doc) as documento:
        assert "Ritenuta d'acconto" in documento[0].get_text()

    esito = runtime.esegui("carica-fattura", doc)
    assert esito.esito == "ok"
    envelope = dal.read("fattura", esito.entity_id)
    assert envelope.dati["fornitore_id"] == "FRN-007"
    assert envelope.dati["ritenuta_acconto"] is None  # v1.0: null nonostante il PDF


def test_skill_con_istruzione_in_calce_estrae_la_ritenuta(banco, dati_rw: Path) -> None:
    """Il meccanismo che l'Improver userà in M5: patch alla skill, stesso runtime."""
    skill = dati_rw / "workflows" / "carica-fattura" / "skills" / "estrazione-fattura.md"
    skill.write_text(
        skill.read_text(encoding="utf-8")
        + "\n- Controlla sempre la dicitura in calce \"Ritenuta d'acconto\": "
        "se presente, riporta l'importo in `ritenuta_acconto`.\n",
        encoding="utf-8",
    )
    runtime, dal, fake, doc = banco(indice=2)
    esito = runtime.esegui("carica-fattura", doc)
    assert esito.esito == "ok"
    envelope = dal.read("fattura", esito.entity_id)
    assert envelope.dati["ritenuta_acconto"] == 800.0


# ------------------------------------------------------- regole e fallimenti


def test_regola_fallita_il_retry_recupera(banco, dati_rw: Path) -> None:
    runtime, dal, fake, doc = banco(indice=0, totale_errato_volte=1)
    esito = runtime.esegui("carica-fattura", doc, run_id="run-retry")

    assert esito.esito == "ok"
    assert fake.risposte_finali == 2  # estrazione sbagliata + retry corretto
    envelope = dal.read("fattura", esito.entity_id)
    assert envelope.dati["totale"] == 10162.6

    validazioni = [
        evento for evento in _eventi_trace(dati_rw, "run-retry") if evento["evento"] == "validation"
    ]
    assert [validazione["esito"] for validazione in validazioni] == ["fallita", "ok"]


def test_regole_fallite_anche_al_retry_stato_errore_e_issue(banco, dati_rw: Path) -> None:
    runtime, dal, fake, doc = banco(indice=0, totale_errato_volte=2)
    esito = runtime.esegui("carica-fattura", doc, run_id="run-flag")

    assert esito.esito == "errore"
    assert esito.stato == "errore"
    assert esito.entity_id == "FT-2026-0006"
    assert esito.issue_id == "ISS-0001"
    assert "abs(dati.totale" in esito.errore

    envelope = dal.read("fattura", "FT-2026-0006")
    assert envelope.stato == "errore"  # salvata comunque: ci pensa l'ufficio

    issue = json.loads((dati_rw / "issues" / "ISS-0001.json").read_text(encoding="utf-8"))
    assert issue["origine"] == "auto"
    assert issue["run_id"] == "run-flag"
    assert issue["entity_id"] == "FT-2026-0006"
    assert issue["stato"] == "aperta"

    eventi = _eventi_trace(dati_rw, "run-flag")
    assert eventi[-1]["outcome"] == "errore"
    validazioni = [evento for evento in eventi if evento["evento"] == "validation"]
    assert [validazione["esito"] for validazione in validazioni] == ["fallita", "fallita"]


def test_errore_duro_issue_automatica_mai_eccezione(banco, dati_rw: Path) -> None:
    guasto = AuthenticationError("chiave errata", llm_provider="test", model="finto")
    runtime, dal, fake, doc = banco(indice=0, guasti=[guasto])
    esito = runtime.esegui("carica-fattura", doc, run_id="run-ko")  # non deve sollevare

    assert esito.esito == "errore"
    assert esito.entity_id is None
    assert esito.issue_id == "ISS-0001"
    assert len(dal.list_all("fattura")) == 5  # nessuna bozza salvata

    eventi = _eventi_trace(dati_rw, "run-ko")
    assert eventi[-1]["outcome"] == "errore"
    assert (dati_rw / "issues" / "ISS-0001.json").is_file()


def test_workflow_inesistente_issue_automatica(banco, dati_rw: Path) -> None:
    runtime, dal, fake, doc = banco(indice=0)
    esito = runtime.esegui("workflow-fantasma", doc)
    assert esito.esito == "errore"
    assert esito.issue_id == "ISS-0001"
    assert "manifest" in esito.errore


def test_confidence_sotto_soglia_richiede_revisione(banco, dati_rw: Path) -> None:
    runtime, dal, fake, doc = banco(indice=1, confidence_override={"totale": 0.55})
    esito = runtime.esegui("carica-fattura", doc)
    assert esito.esito == "ok"  # si salva comunque come bozza…
    assert esito.richiede_revisione is True  # …ma la revisione umana è obbligatoria
