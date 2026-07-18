"""Fixtures: 3 fatture PDF sintetiche coerenti con il seed (``make fixtures``).

La terza è la parcella di un professionista con la ritenuta d'acconto in
calce: è il documento dello scenario M5 ("la v1.0 non estrae la ritenuta").
Il layout è volutamente deterministico, riga per riga: i test lo rileggono
con pymupdf per simulare l'estrazione.

``FIXTURES`` espone, accanto a ogni PDF, i dati attesi dall'estrazione:
un'unica fonte per generatore e test.
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
        "file": "fattura-calcestruzzi-etna.pdf",
        "fornitore": "Calcestruzzi Etna S.p.A.",
        "partita_iva": "04811230871",
        "indirizzo": "Contrada Torre Allegra 8, Catania",
        "cantiere": "Residenza Le Palme, Catania",
        "numero": "112/2026",
        "data": "05/07/2026",
        "aliquota": 22,
        "imponibile": 8330.00,
        "iva": 1832.60,
        "totale": 10162.60,
        "ritenuta": None,
        "righe": [
            ("Calcestruzzo C28/35 XC2 pompato", "60 m3", 6180.00),
            ("Servizio pompa autocarrata", "10 h", 2150.00),
        ],
        "atteso": {
            "fornitore_id": "FRN-001",
            "cantiere_id": "CNT-001",
            "data_iso": "2026-07-05",
        },
    },
    {
        "file": "fattura-edil-sud.pdf",
        "fornitore": "Edil Sud S.r.l.",
        "partita_iva": "03502180872",
        "indirizzo": "Via Garibaldi 210, Misterbianco",
        "cantiere": "Ristrutturazione Scuola Manzoni, Acireale",
        "numero": "131/E",
        "data": "30/06/2026",
        "aliquota": 10,
        "imponibile": 5718.00,
        "iva": 571.80,
        "totale": 6289.80,
        "ritenuta": None,
        "righe": [
            ("Blocchi Poroton P800 25x30x19", "294 pz", 3675.00),
            ("Malta bastarda M5", "149 sacco", 1043.00),
            ("Rete elettrosaldata diam. 8 20x20", "50 pz", 1000.00),
        ],
        "atteso": {
            "fornitore_id": "FRN-002",
            "cantiere_id": "CNT-002",
            "data_iso": "2026-06-30",
        },
    },
    {
        "file": "fattura-studio-bianchi.pdf",
        "fornitore": "Studio Tecnico Ing. Bianchi",
        "partita_iva": "02644330877",
        "indirizzo": "Piazza Verga 6, Catania",
        "cantiere": "Residenza Le Palme, Catania",
        "numero": "15/2026",
        "data": "08/07/2026",
        "aliquota": 22,
        "imponibile": 4000.00,
        "iva": 880.00,
        "totale": 4880.00,
        "ritenuta": 800.00,  # in calce: lo scenario M5 nasce qui
        "righe": [
            ("Direzione lavori strutture - secondo acconto", None, 4000.00),
        ],
        "atteso": {
            "fornitore_id": "FRN-007",
            "cantiere_id": "CNT-001",
            "data_iso": "2026-07-08",
        },
    },
]


def _euro(valore: float) -> str:
    """8330.0 → '8.330,00' (formato italiano, come stampato in fattura)."""
    testo = f"{valore:,.2f}"
    return testo.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _quantita(testo: str | None) -> tuple[float | None, str | None]:
    """'60 m3' → (60.0, 'm3'); None o non numerica → (None, None)."""
    if not testo:
        return None, None
    numero, _, unita = testo.partition(" ")
    try:
        return float(numero.replace(".", "").replace(",", ".")), (unita or None)
    except ValueError:
        return None, None


def dati_attesi(spec: dict[str, Any]) -> dict[str, Any]:
    """La trascrizione corretta (ground truth) attesa dall'estrazione della fixture.

    Fonte unica per il seed del golden set (M5) e per i test: è il dato
    "validato" contro cui si misura una nuova versione del workflow.
    """
    righe = []
    for descrizione, quantita_testo, importo in spec["righe"]:
        quantita, unita = _quantita(quantita_testo)
        righe.append(
            {
                "descrizione": descrizione,
                "quantita": quantita,
                "unita_misura": unita,
                "importo": importo,
                "voce_computo_id": None,
            }
        )
    return {
        "fornitore_id": spec["atteso"]["fornitore_id"],
        "cantiere_id": spec["atteso"]["cantiere_id"],
        "numero": spec["numero"],
        "data": spec["atteso"]["data_iso"],
        "imponibile": spec["imponibile"],
        "iva": spec["iva"],
        "totale": spec["totale"],
        "ritenuta_acconto": spec["ritenuta"],
        "righe": righe,
    }


def disegna(percorso: Path, spec: dict[str, Any]) -> None:
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
    riga(f"FATTURA N. {spec['numero']} del {spec['data']}", "Helvetica-Bold", 13, 9 * mm)
    riga(f"Spett.le {DESTINATARIO}")
    riga(f"Cantiere: {spec['cantiere']}")
    y -= 4 * mm
    riga("Descrizione | Quantita | Importo", "Helvetica-Bold")
    for descrizione, quantita, importo in spec["righe"]:
        riga(f"{descrizione} | {quantita or '-'} | EUR {_euro(importo)}")
    y -= 4 * mm
    riga(f"Imponibile: EUR {_euro(spec['imponibile'])}")
    riga(f"IVA {spec['aliquota']}%: EUR {_euro(spec['iva'])}")
    riga(f"TOTALE: EUR {_euro(spec['totale'])}", "Helvetica-Bold", 12)
    if spec["ritenuta"]:
        y -= 8 * mm  # dicitura in calce, staccata dal riepilogo
        riga(f"Ritenuta d'acconto 20%: EUR {_euro(spec['ritenuta'])}", "Helvetica", 10)
        riga(f"Netto a pagare: EUR {_euro(spec['totale'] - spec['ritenuta'])}", "Helvetica", 10)
    foglio.showPage()
    foglio.save()


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
    print(f"Generati {len(percorsi)} PDF in {destinazione.resolve()}:")
    for percorso in percorsi:
        print(f"  {percorso.name}")


if __name__ == "__main__":
    main()
