"""Tool nativi: ocr_pdf, ricerche fuzzy, salva_bozza, dispatch del Toolset."""

import base64
import shutil
from pathlib import Path

import pytest

from app.core.dal import DAL
from app.core.tools import Toolset
from app.core.tools.base import ToolError


@pytest.fixture
def toolset(dati_rw: Path) -> Toolset:
    return Toolset(DAL(dati_rw))


def _porta_fixture_nei_blob(dati_rw: Path, fixtures_dir: Path, nome: str) -> str:
    relativo = f"blobs/fatture/2026/{nome}"
    shutil.copy(fixtures_dir / nome, dati_rw / relativo)
    return relativo


# ------------------------------------------------------------------ ocr_pdf


def test_ocr_pdf_rende_le_pagine_png(
    toolset: Toolset, dati_rw: Path, fixtures_dir: Path
) -> None:
    doc = _porta_fixture_nei_blob(dati_rw, fixtures_dir, "fattura-calcestruzzi-etna.pdf")
    risultato = toolset.esegui("ocr_pdf", {"path": doc})
    assert risultato["pagine"] == 1
    png = base64.b64decode(risultato["immagini_png_base64"][0])
    assert png.startswith(b"\x89PNG")


def test_ocr_pdf_percorsi_e_formati_rifiutati(toolset: Toolset) -> None:
    with pytest.raises(ToolError, match="fuori dal repo dati"):
        toolset.esegui("ocr_pdf", {"path": "../segreti.pdf"})
    with pytest.raises(ToolError, match="non supportato"):
        toolset.esegui("ocr_pdf", {"path": "config/views.sql"})
    with pytest.raises(ToolError, match="non trovato"):
        toolset.esegui("ocr_pdf", {"path": "blobs/fatture/2026/inesistente.pdf"})


# ------------------------------------------------------------------ ricerche


def test_cerca_fornitore_per_nome_e_partita_iva(toolset: Toolset) -> None:
    per_nome = toolset.esegui("cerca_fornitore", {"query": "Calcestruzzi Etna Spa"})
    assert per_nome["risultati"][0]["id"] == "FRN-001"
    per_piva = toolset.esegui("cerca_fornitore", {"query": "02644330877"})
    assert per_piva["risultati"][0]["id"] == "FRN-007"


def test_cerca_cantiere_match_parziale(toolset: Toolset) -> None:
    risultato = toolset.esegui("cerca_cantiere", {"query": "Scuola Manzoni"})
    assert risultato["risultati"][0]["id"] == "CNT-002"
    assert risultato["risultati"][0]["punteggio"] >= 0.9  # contenimento


# ---------------------------------------------------------------- salva_bozza

DATI_FATTURA = {
    "fornitore_id": "FRN-003",
    "cantiere_id": "CNT-001",
    "numero": "77/2026",
    "data": "2026-07-10",
    "imponibile": 100.0,
    "iva": 22.0,
    "totale": 122.0,
    "ritenuta_acconto": None,
    "righe": [
        {
            "descrizione": "Minuteria",
            "quantita": None,
            "unita_misura": None,
            "importo": 100.0,
            "voce_computo_id": None,
        }
    ],
}


def test_salva_bozza_id_progressivo_e_meta(toolset: Toolset, dati_rw: Path) -> None:
    risultato = toolset.esegui(
        "salva_bozza",
        {
            "tipo": "fattura",
            "dati": DATI_FATTURA,
            "confidence": {"totale": 0.99},
            "origine": "blobs/fatture/2026/x.pdf",
            "workflow": "carica-fattura@1.0",
            "run_id": "run-tool",
        },
    )
    assert risultato == {"id": "FT-2026-0006", "stato": "bozza"}  # il seed arriva a 0005

    envelope = DAL(dati_rw).read("fattura", "FT-2026-0006")
    assert envelope.stato == "bozza"
    assert envelope.meta.workflow == "carica-fattura@1.0"
    assert envelope.meta.run_id == "run-tool"
    assert envelope.meta.confidence == {"totale": 0.99}

    secondo = toolset.esegui("salva_bozza", {"tipo": "fattura", "dati": DATI_FATTURA})
    assert secondo["id"] == "FT-2026-0007"


# ------------------------------------------------------------------- Toolset


def test_toolset_limita_ai_tool_dello_step(toolset: Toolset) -> None:
    with pytest.raises(ToolError, match="non disponibile"):
        toolset.esegui("salva_bozza", {}, consentiti=["ocr_pdf"])
    with pytest.raises(ToolError, match="sconosciuto"):
        toolset.esegui("cancella_tutto", {})
    with pytest.raises(ToolError, match="argomenti non validi"):
        toolset.esegui("cerca_fornitore", {"interrogazione": "x"})


def test_toolset_schemi_function_calling(toolset: Toolset) -> None:
    schemi = toolset.schemi(["ocr_pdf", "cerca_fornitore", "cerca_cantiere"])
    assert [s["function"]["name"] for s in schemi] == [
        "ocr_pdf",
        "cerca_fornitore",
        "cerca_cantiere",
    ]
    assert all(s["type"] == "function" for s in schemi)
