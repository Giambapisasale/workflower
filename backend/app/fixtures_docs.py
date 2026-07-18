"""Fixtures dei documenti di Fase 2 (DDT, e in seguito SAL/rapportini/computo).

Le fatture restano in ``app.fixtures`` (intatte: golden set e test M2/M5 vi
dipendono). Qui vivono i documenti dei nuovi tipi, con lo stesso patto: layout
deterministico, riga per riga, così il fake LLM (tests/fake_llm.py) li rilegge
con pymupdf come farebbe un modello che guarda la pagina. ``FIXTURES`` espone,
accanto a ogni PDF, la trascrizione attesa: un'unica fonte per generatore e test.
"""

import os
import sys
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

DESTINATARIO = "Costruzioni Aitho S.r.l. - Viale Africa 31, Catania"

FIXTURES: list[dict[str, Any]] = [
    {
        "tipo": "ddt",
        "file": "ddt-edil-sud.pdf",
        "fornitore": "Edil Sud S.r.l.",
        "partita_iva": "03502180872",
        "indirizzo": "Via Garibaldi 210, Misterbianco",
        "cantiere": "Ristrutturazione Scuola Manzoni, Acireale",
        "numero": "778/T",
        "data": "15/07/2026",
        "causale": "Vendita",
        "riferimento_ordine": "ODA-2026-114",
        "righe": [
            ("Pannelli isolanti XPS 40mm", "120", "pz"),
            ("Guaina bituminosa 4mm", "60", "mq"),
            ("Profili metallici per cartongesso", "200", "m"),
        ],
        "atteso": {"fornitore_id": "FRN-002", "cantiere_id": "CNT-002", "data_iso": "2026-07-15"},
    },
]


def _num(testo: str) -> float | None:
    try:
        return float(testo.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def dati_attesi(spec: dict[str, Any]) -> dict[str, Any]:
    """Trascrizione corretta (ground truth) attesa dall'estrazione del DDT."""
    righe = [
        {
            "descrizione": descrizione,
            "quantita": _num(quantita),
            "unita_misura": unita or None,
            "voce_computo_id": None,
        }
        for descrizione, quantita, unita in spec["righe"]
    ]
    return {
        "fornitore_id": spec["atteso"]["fornitore_id"],
        "cantiere_id": spec["atteso"]["cantiere_id"],
        "numero": spec["numero"],
        "data": spec["atteso"]["data_iso"],
        "causale": spec["causale"],
        "riferimento_ordine": spec["riferimento_ordine"],
        "righe": righe,
    }


def _disegna_ddt(percorso: Path, spec: dict[str, Any]) -> None:
    foglio = canvas.Canvas(str(percorso), pagesize=A4)
    _, altezza = A4
    y = altezza - 25 * mm

    def riga(testo: str, font: str = "Helvetica", corpo: int = 11, salto: float = 7 * mm) -> None:
        nonlocal y
        foglio.setFont(font, corpo)
        foglio.drawString(20 * mm, y, testo)
        y -= salto

    riga(spec["fornitore"], "Helvetica-Bold", 16, 8 * mm)
    riga(f"P.IVA {spec['partita_iva']} - {spec['indirizzo']}")
    y -= 4 * mm
    riga("DOCUMENTO DI TRASPORTO (D.D.T.)", "Helvetica-Bold", 13, 9 * mm)
    riga(f"DDT N. {spec['numero']} del {spec['data']}", "Helvetica-Bold", 12, 9 * mm)
    riga(f"Spett.le {DESTINATARIO}")
    riga(f"Destinazione (cantiere): {spec['cantiere']}")
    riga(f"Causale: {spec['causale'] or '-'}")
    riga(f"Rif. ordine: {spec['riferimento_ordine'] or '-'}")
    y -= 4 * mm
    riga("Descrizione | Quantita | UM", "Helvetica-Bold")
    for descrizione, quantita, unita in spec["righe"]:
        riga(f"{descrizione} | {quantita} | {unita}")
    y -= 4 * mm
    riga("Merce resa franco cantiere. Documento senza valore fiscale.", "Helvetica", 9)
    foglio.showPage()
    foglio.save()


DISEGNATORI = {"ddt": _disegna_ddt}


def disegna(percorso: Path, spec: dict[str, Any]) -> None:
    DISEGNATORI[spec["tipo"]](percorso, spec)


def genera(destinazione: Path | str) -> list[Path]:
    cartella = Path(destinazione)
    cartella.mkdir(parents=True, exist_ok=True)
    percorsi = []
    for spec in FIXTURES:
        percorso = cartella / spec["file"]
        disegna(percorso, spec)
        percorsi.append(percorso)
    return percorsi


def main() -> None:
    predefinita = os.environ.get("FIXTURES_DIR", "./fixtures")
    destinazione = Path(sys.argv[1] if len(sys.argv) > 1 else predefinita)
    percorsi = genera(destinazione)
    print(f"Generati {len(percorsi)} documenti (Fase 2) in {destinazione.resolve()}:")
    for percorso in percorsi:
        print(f"  {percorso.name}")


if __name__ == "__main__":
    main()
