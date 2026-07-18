"""Le fixtures PDF di `make fixtures`: tre fatture, una con ritenuta in calce."""

from pathlib import Path

import pymupdf

from app.fixtures import FIXTURES


def test_tre_pdf_generati(fixtures_dir: Path) -> None:
    nomi = sorted(percorso.name for percorso in fixtures_dir.glob("*.pdf"))
    assert nomi == sorted(spec["file"] for spec in FIXTURES)
    assert len(nomi) == 3


def test_la_terza_ha_la_ritenuta_in_calce(fixtures_dir: Path) -> None:
    with pymupdf.open(fixtures_dir / "fattura-studio-bianchi.pdf") as documento:
        testo = documento[0].get_text()
    assert "FATTURA N. 15/2026 del 08/07/2026" in testo
    assert "TOTALE: EUR 4.880,00" in testo
    assert "Ritenuta d'acconto 20%: EUR 800,00" in testo
    assert "Netto a pagare: EUR 4.080,00" in testo


def test_le_altre_non_hanno_ritenuta(fixtures_dir: Path) -> None:
    for nome in ("fattura-calcestruzzi-etna.pdf", "fattura-edil-sud.pdf"):
        with pymupdf.open(fixtures_dir / nome) as documento:
            assert "Ritenuta" not in documento[0].get_text()
