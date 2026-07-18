"""Fixtures dei documenti di Fase 2 (DDT, SAL, rapportini, …).

Le fatture restano in ``app.fixtures`` (intatte: golden set e test M2/M5 vi
dipendono). Qui vivono i documenti dei nuovi tipi, con lo stesso patto: layout
deterministico, riga per riga, così il fake LLM (tests/fake_llm.py) li rilegge
con pymupdf come farebbe un modello che guarda la pagina. ``FIXTURES`` espone,
accanto a ogni PDF, la trascrizione attesa: un'unica fonte per generatore e test.

Aggiungere un tipo = una voce in ``FIXTURES`` + un disegnatore + un "atteso".
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
    {
        "tipo": "sal",
        "file": "sal-capannone-etna.pdf",
        "cantiere": "Capannone logistico Etna Sud, Misterbianco",
        "numero": "4",
        "data": "10/07/2026",
        "importo_lavori": 1980000.00,
        "importo_progressivo": 742500.00,
        "percentuale_avanzamento": 37.5,
        "atteso": {"cantiere_id": "CNT-003", "data_iso": "2026-07-10"},
    },
    {
        "tipo": "rapportino",
        "file": "rapportino-le-palme.pdf",
        "cantiere": "Residenza Le Palme, Catania",
        "data": "13/07/2026",
        "righe": [
            ("Salvo Torrisi", "Capocantiere", "8", "32,00"),
            ("Mario Rossi", "Muratore", "8", "26,50"),
            ("Squadra carpentieri", "Carpenteria", "24", "24,00"),
        ],
        "atteso": {"cantiere_id": "CNT-001", "data_iso": "2026-07-13"},
    },
]


def _num(testo: str | None) -> float | None:
    if not testo:
        return None
    try:
        return float(testo.replace(".", "").replace(",", "."))
    except ValueError:
        return None


# --------------------------------------------------------------- dati attesi


def _attesi_ddt(spec: dict[str, Any]) -> dict[str, Any]:
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


def _attesi_sal(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "cantiere_id": spec["atteso"]["cantiere_id"],
        "numero": spec["numero"],
        "data": spec["atteso"]["data_iso"],
        "importo_lavori": spec["importo_lavori"],
        "importo_progressivo": spec["importo_progressivo"],
        "percentuale_avanzamento": spec["percentuale_avanzamento"],
    }


def _attesi_rapportino(spec: dict[str, Any]) -> dict[str, Any]:
    righe = [
        {
            "nominativo": nominativo,
            "mansione": mansione or None,
            "ore": _num(ore),
            "costo_orario": _num(costo),
        }
        for nominativo, mansione, ore, costo in spec["righe"]
    ]
    return {
        "cantiere_id": spec["atteso"]["cantiere_id"],
        "data": spec["atteso"]["data_iso"],
        "righe": righe,
    }


ATTESI = {"ddt": _attesi_ddt, "sal": _attesi_sal, "rapportino": _attesi_rapportino}


def dati_attesi(spec: dict[str, Any]) -> dict[str, Any]:
    """Trascrizione corretta (ground truth) attesa dall'estrazione del documento."""
    return ATTESI[spec["tipo"]](spec)


# ------------------------------------------------------------------ disegno


def _foglio(percorso: Path):
    foglio = canvas.Canvas(str(percorso), pagesize=A4)
    _, altezza = A4
    stato = {"y": altezza - 25 * mm}

    def riga(testo: str, font: str = "Helvetica", corpo: int = 11, salto: float = 7 * mm) -> None:
        foglio.setFont(font, corpo)
        foglio.drawString(20 * mm, stato["y"], testo)
        stato["y"] -= salto

    def spazio(mm_: float) -> None:
        stato["y"] -= mm_ * mm

    return foglio, riga, spazio


def _disegna_ddt(percorso: Path, spec: dict[str, Any]) -> None:
    foglio, riga, spazio = _foglio(percorso)
    riga(spec["fornitore"], "Helvetica-Bold", 16, 8 * mm)
    riga(f"P.IVA {spec['partita_iva']} - {spec['indirizzo']}")
    spazio(4)
    riga("DOCUMENTO DI TRASPORTO (D.D.T.)", "Helvetica-Bold", 13, 9 * mm)
    riga(f"DDT N. {spec['numero']} del {spec['data']}", "Helvetica-Bold", 12, 9 * mm)
    riga(f"Spett.le {DESTINATARIO}")
    riga(f"Destinazione (cantiere): {spec['cantiere']}")
    riga(f"Causale: {spec['causale'] or '-'}")
    riga(f"Rif. ordine: {spec['riferimento_ordine'] or '-'}")
    spazio(4)
    riga("Descrizione | Quantita | UM", "Helvetica-Bold")
    for descrizione, quantita, unita in spec["righe"]:
        riga(f"{descrizione} | {quantita} | {unita}")
    spazio(4)
    riga("Merce resa franco cantiere. Documento senza valore fiscale.", "Helvetica", 9)
    foglio.showPage()
    foglio.save()


def _euro(valore: float) -> str:
    testo = f"{valore:,.2f}"
    return testo.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _disegna_sal(percorso: Path, spec: dict[str, Any]) -> None:
    foglio, riga, spazio = _foglio(percorso)
    riga("STATO AVANZAMENTO LAVORI (S.A.L.)", "Helvetica-Bold", 15, 9 * mm)
    riga(f"SAL N. {spec['numero']} del {spec['data']}", "Helvetica-Bold", 12, 9 * mm)
    riga(f"Cantiere: {spec['cantiere']}")
    riga(f"Impresa: {DESTINATARIO}")
    spazio(4)
    riga(f"Importo lavori contrattuali: EUR {_euro(spec['importo_lavori'])}")
    riga(f"Lavori eseguiti a tutto il presente SAL: EUR {_euro(spec['importo_progressivo'])}")
    riga(f"Avanzamento complessivo: {_euro(spec['percentuale_avanzamento'])} %")
    foglio.showPage()
    foglio.save()


def _disegna_rapportino(percorso: Path, spec: dict[str, Any]) -> None:
    foglio, riga, spazio = _foglio(percorso)
    riga("RAPPORTINO DI CANTIERE", "Helvetica-Bold", 15, 9 * mm)
    riga(f"Data: {spec['data']}", "Helvetica-Bold", 12)
    riga(f"Cantiere: {spec['cantiere']}")
    spazio(4)
    riga("Nominativo | Mansione | Ore | EUR/h", "Helvetica-Bold")
    for nominativo, mansione, ore, costo in spec["righe"]:
        riga(f"{nominativo} | {mansione or '-'} | {ore} | {costo or '-'}")
    foglio.showPage()
    foglio.save()


DISEGNATORI = {"ddt": _disegna_ddt, "sal": _disegna_sal, "rapportino": _disegna_rapportino}


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
