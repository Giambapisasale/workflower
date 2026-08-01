#!/usr/bin/env python3
"""Genera i documenti d'esempio della guida: uno per ogni strada del sistema.

Non sono decorazione. Ogni file esiste per far vedere **una cosa che altrimenti
non si vedrebbe**: il Word che nessun modello vision sa aprire, la foto storta
che solo l'OCR regge, la fattura intestata a un'altra impresa, quella con la
ritenuta d'acconto, quella di un fornitore che in anagrafica non c'è, quella coi
conti che non tornano, e il file che non si può proprio leggere.

Uso:
    python guida_utente/genera_esempi.py

I file finiscono in ``guida_utente/esempi/``. Sono deterministici: rigenerarli
produce gli stessi documenti, così la demo si ripete uguale.
"""

import sys
import zipfile
from pathlib import Path

for _flusso in (sys.stdout, sys.stderr):
    if hasattr(_flusso, "reconfigure"):
        _flusso.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

DESTINAZIONE = Path(__file__).resolve().parent / "esempi"

NOSTRA_AZIENDA = "Costruzioni Aitho S.r.l. - Viale Africa 31, Catania"
ALTRA_AZIENDA = "Costruzioni Delta S.r.l. - Via Etnea 155, Catania"


# --------------------------------------------------------------------- PDF


def _pdf(percorso: Path, righe: list[tuple[str, str, int]]) -> None:
    """Disegna un documento riga per riga. Layout deterministico, come le fixture."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    foglio = canvas.Canvas(str(percorso), pagesize=A4)
    _, altezza = A4
    y = altezza - 25 * mm
    for testo, font, corpo in righe:
        if not testo:
            y -= 4 * mm
            continue
        foglio.setFont(font, corpo)
        foglio.drawString(20 * mm, y, testo)
        y -= 7 * mm if corpo <= 11 else 9 * mm
    foglio.showPage()
    foglio.save()


def _fattura(
    percorso: Path,
    *,
    fornitore: str,
    partita_iva: str,
    indirizzo: str,
    numero: str,
    data: str,
    cantiere: str,
    destinatario: str = NOSTRA_AZIENDA,
    righe: list[tuple[str, str, str]],
    imponibile: str,
    iva: str,
    totale: str,
    ritenuta: str | None = None,
    netto: str | None = None,
) -> None:
    corpo: list[tuple[str, str, int]] = [
        (fornitore, "Helvetica-Bold", 16),
        (f"P.IVA {partita_iva} - {indirizzo}", "Helvetica", 11),
        ("", "Helvetica", 11),
        (f"FATTURA N. {numero} del {data}", "Helvetica-Bold", 13),
        (f"Spett.le {destinatario}", "Helvetica", 11),
        (f"Cantiere: {cantiere}", "Helvetica", 11),
        ("", "Helvetica", 11),
        ("Descrizione | Quantita | Importo", "Helvetica-Bold", 11),
    ]
    corpo += [(f"{d} | {q} | EUR {i}", "Helvetica", 11) for d, q, i in righe]
    corpo += [
        ("", "Helvetica", 11),
        (f"Imponibile: EUR {imponibile}", "Helvetica", 11),
        (f"IVA 22%: EUR {iva}", "Helvetica", 11),
        (f"TOTALE: EUR {totale}", "Helvetica-Bold", 12),
    ]
    if ritenuta:
        corpo += [
            ("", "Helvetica", 11),
            (f"Ritenuta d'acconto 20%: EUR {ritenuta}", "Helvetica", 10),
            (f"Netto a pagare: EUR {netto}", "Helvetica", 10),
        ]
    _pdf(percorso, corpo)


# -------------------------------------------------------------------- DOCX


def _docx(percorso: Path, paragrafi: list[tuple[str, bool]], tabella: list[list[str]]) -> None:
    """Un .docx minimo scritto a mano (niente python-docx fra le dipendenze).

    Serve un file Word *vero*, con una tabella vera: è il caso che dimostra
    Docling, e un finto .docx non dimostrerebbe niente.
    """

    def esc(testo: str) -> str:
        return testo.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def paragrafo(testo: str, grassetto: bool = False) -> str:
        stile = "<w:rPr><w:b/></w:rPr>" if grassetto else ""
        return (
            f"<w:p><w:r>{stile}<w:t xml:space='preserve'>{esc(testo)}</w:t></w:r></w:p>"
        )

    def cella(testo: str, grassetto: bool = False) -> str:
        # La larghezza dichiarata non è cosmetica: senza `w:tcW` (e senza il
        # `w:tblGrid` qui sotto) la tabella è formalmente incompleta e i parser
        # la saltano — il documento arriva senza righe e sembra che il parser
        # non sappia leggere le tabelle. Verificato: prima di questa riga il
        # Markdown usciva con la sola intestazione.
        return (
            "<w:tc><w:tcPr><w:tcW w:w='3000' w:type='dxa'/></w:tcPr>"
            f"{paragrafo(testo, grassetto)}</w:tc>"
        )

    corpo = "".join(paragrafo(t, b) for t, b in paragrafi)
    if tabella:
        colonne = max(len(riga) for riga in tabella)
        griglia = "".join("<w:gridCol w:w='3000'/>" for _ in range(colonne))
        righe = "".join(
            "<w:tr>" + "".join(cella(c, n == 0) for c in riga) + "</w:tr>"
            for n, riga in enumerate(tabella)
        )
        corpo += (
            "<w:tbl><w:tblPr><w:tblW w:w='9000' w:type='dxa'/></w:tblPr>"
            f"<w:tblGrid>{griglia}</w:tblGrid>{righe}</w:tbl>"
        )

    documento = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        f"<w:body>{corpo}</w:body></w:document>"
    )
    tipi = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
        "<Default Extension='xml' ContentType='application/xml'/>"
        "<Default Extension='rels' "
        "ContentType='application/vnd.openxmlformats-package.relationships+xml'/>"
        "<Override PartName='/word/document.xml' ContentType='application/vnd."
        "openxmlformats-officedocument.wordprocessingml.document.main+xml'/></Types>"
    )
    rels = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
        "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/"
        "relationships/officeDocument' Target='word/document.xml'/></Relationships>"
    )
    with zipfile.ZipFile(percorso, "w", zipfile.ZIP_DEFLATED) as zip_:
        zip_.writestr("[Content_Types].xml", tipi)
        zip_.writestr("_rels/.rels", rels)
        zip_.writestr("word/document.xml", documento)


# ------------------------------------------------------------- foto (JPG)


def _foto_da_pdf(pdf: Path, jpg: Path, *, rotazione: float = 1.6) -> None:
    """Rende una pagina come immagine leggermente storta: la foto dal cantiere.

    L'inclinazione non è un vezzo — è la differenza fra una scansione e una foto
    scattata al volo, ed è il caso in cui il modello che *guarda* la pagina
    lavora meglio di un parser che si aspetta righe dritte.
    """
    import fitz

    with fitz.open(pdf) as documento:
        pagina = documento[0]
        matrice = fitz.Matrix(2, 2).prerotate(rotazione)
        pagina.get_pixmap(matrix=matrice).save(jpg, jpg_quality=70)


# ------------------------------------------------------------------ esempi


def genera() -> list[Path]:
    DESTINAZIONE.mkdir(parents=True, exist_ok=True)
    fatti = []

    # 1. La strada normale: PDF nato al computer, fornitore e cantiere in anagrafica.
    percorso = DESTINAZIONE / "01-fattura-digitale.pdf"
    _fattura(
        percorso,
        fornitore="Calcestruzzi Etna S.p.A.",
        partita_iva="01234567890",
        indirizzo="Zona Industriale, Catania",
        numero="1180/26",
        data="12/07/2026",
        cantiere="Residenza Le Palme",
        righe=[
            ("Calcestruzzo Rck 30 preconfezionato", "42,00 mc", "5.460,00"),
            ("Nolo autopompa", "2,00 gg", "1.100,00"),
        ],
        imponibile="6.560,00",
        iva="1.443,20",
        totale="8.003,20",
    )
    fatti.append(percorso)

    # 2. Ritenuta d'acconto: lo scenario che il sistema sbagliava e ha imparato.
    percorso = DESTINAZIONE / "02-fattura-con-ritenuta.pdf"
    _fattura(
        percorso,
        fornitore="Studio Tecnico Ing. Bianchi",
        partita_iva="02644330877",
        indirizzo="Piazza Verga 6, Catania",
        numero="24/2026",
        data="18/07/2026",
        cantiere="Residenza Le Palme",
        righe=[
            ("Direzione lavori strutture - III acconto", "-", "4.500,00"),
            ("Coordinamento sicurezza in esecuzione", "-", "1.500,00"),
        ],
        imponibile="6.000,00",
        iva="1.320,00",
        totale="7.320,00",
        ritenuta="1.200,00",
        netto="6.120,00",
    )
    fatti.append(percorso)

    # 3. Word: nessun modello vision sa aprirlo. Serve il parser su GPU.
    percorso = DESTINAZIONE / "03-fattura-word.docx"
    _docx(
        percorso,
        [
            ("Ferramenta Siciliana S.r.l.", True),
            ("P.IVA 04455660873 - Via Palermo 88, Catania", False),
            ("FATTURA N. 512/2026 del 20/07/2026", True),
            (f"Spett.le {NOSTRA_AZIENDA}", False),
            ("Cantiere: Ristrutturazione Scuola Manzoni", False),
        ],
        [
            ["Descrizione", "Quantita", "Importo"],
            ["Ponteggio a telai - nolo mensile", "1,00", "2.800,00"],
            ["Reti di protezione", "150,00", "450,00"],
            ["Imponibile", "", "3.250,00"],
            ["IVA 22%", "", "715,00"],
            ["TOTALE", "", "3.965,00"],
        ],
    )
    fatti.append(percorso)

    # 4. La foto storta dal cantiere: la strada dell'OCR e del modello che guarda.
    percorso = DESTINAZIONE / "04-fattura-foto.jpg"
    _foto_da_pdf(DESTINAZIONE / "01-fattura-digitale.pdf", percorso)
    fatti.append(percorso)

    # 5. Intestata a un'altra impresa: il controllo del destinatario.
    percorso = DESTINAZIONE / "05-fattura-intestata-ad-altri.pdf"
    _fattura(
        percorso,
        fornitore="Calcestruzzi Etna S.p.A.",
        partita_iva="01234567890",
        indirizzo="Zona Industriale, Catania",
        numero="1181/26",
        data="12/07/2026",
        cantiere="Residenza Le Palme",
        destinatario=ALTRA_AZIENDA,
        righe=[("Calcestruzzo Rck 30 preconfezionato", "18,00 mc", "2.340,00")],
        imponibile="2.340,00",
        iva="514,80",
        totale="2.854,80",
    )
    fatti.append(percorso)

    # 6. Fornitore che in anagrafica non c'è: il riferimento resta da risolvere.
    percorso = DESTINAZIONE / "06-fattura-fornitore-nuovo.pdf"
    _fattura(
        percorso,
        fornitore="Impresa Verdi & Figli S.n.c.",
        partita_iva="05566770874",
        indirizzo="Via Dusmet 12, Aci Castello",
        numero="77/2026",
        data="21/07/2026",
        cantiere="Capannone logistico Etna Sud",
        righe=[("Scavo di sbancamento e trasporto a discarica", "320,00 mc", "4.160,00")],
        imponibile="4.160,00",
        iva="915,20",
        totale="5.075,20",
    )
    fatti.append(percorso)

    # 7. I conti non tornano: la validazione ferma il documento e apre una issue.
    percorso = DESTINAZIONE / "07-fattura-totale-sbagliato.pdf"
    _fattura(
        percorso,
        fornitore="Edil Sud S.r.l.",
        partita_iva="03502180872",
        indirizzo="Via Garibaldi 210, Misterbianco",
        numero="903/26",
        data="22/07/2026",
        cantiere="Ristrutturazione Scuola Manzoni",
        righe=[("Fornitura laterizi", "1,00", "2.000,00")],
        imponibile="2.000,00",
        iva="440,00",
        totale="9.999,00",  # non è imponibile + IVA: la regola del manifest lo prende
    )
    fatti.append(percorso)

    # 8. DDT: merce in cantiere, nessun importo.
    percorso = DESTINAZIONE / "08-ddt.pdf"
    _pdf(
        percorso,
        [
            ("Edil Sud S.r.l.", "Helvetica-Bold", 16),
            ("P.IVA 03502180872 - Via Garibaldi 210, Misterbianco", "Helvetica", 11),
            ("", "Helvetica", 11),
            ("DOCUMENTO DI TRASPORTO (D.D.T.)", "Helvetica-Bold", 13),
            ("DDT N. 812/T del 23/07/2026", "Helvetica-Bold", 12),
            (f"Spett.le {NOSTRA_AZIENDA}", "Helvetica", 11),
            ("Destinazione (cantiere): Ristrutturazione Scuola Manzoni, Acireale", "Helvetica", 11),
            ("Causale: Vendita", "Helvetica", 11),
            ("Rif. ordine: ODA-2026-131", "Helvetica", 11),
            ("", "Helvetica", 11),
            ("Descrizione | Quantita | UM", "Helvetica-Bold", 11),
            ("Blocchi in laterizio 25x25x25 | 800 | pz", "Helvetica", 11),
            ("Malta premiscelata | 60 | sacchi", "Helvetica", 11),
            ("", "Helvetica", 11),
            ("Merce resa franco cantiere. Documento senza valore fiscale.", "Helvetica", 10),
        ],
    )
    fatti.append(percorso)

    # 9. DDT in Word: stessa strada del Word, su un tipo diverso.
    percorso = DESTINAZIONE / "09-ddt-word.docx"
    _docx(
        percorso,
        [
            ("Calcestruzzi Etna S.p.A.", True),
            ("P.IVA 01234567890 - Zona Industriale, Catania", False),
            ("DOCUMENTO DI TRASPORTO (D.D.T.)", True),
            ("DDT N. 1204/26 del 24/07/2026", True),
            (f"Spett.le {NOSTRA_AZIENDA}", False),
            ("Destinazione (cantiere): Residenza Le Palme, Catania", False),
            ("Causale: Vendita", False),
        ],
        [
            ["Descrizione", "Quantita", "UM"],
            ["Calcestruzzo Rck 30 preconfezionato", "24,00", "mc"],
            ["Additivo fluidificante", "40", "kg"],
        ],
    )
    fatti.append(percorso)

    # 10. SAL: avanzamento lavori, percentuali.
    percorso = DESTINAZIONE / "10-sal.pdf"
    _pdf(
        percorso,
        [
            ("STATO AVANZAMENTO LAVORI", "Helvetica-Bold", 16),
            ("", "Helvetica", 11),
            ("SAL N. 5 del 25/07/2026", "Helvetica-Bold", 13),
            ("Cantiere: Capannone logistico Etna Sud, Misterbianco", "Helvetica", 11),
            ("", "Helvetica", 11),
            ("Importo lavori a base d'appalto: EUR 1.980.000,00", "Helvetica", 11),
            ("Importo progressivo dei lavori eseguiti: EUR 891.000,00", "Helvetica", 11),
            ("Percentuale di avanzamento: 45,0%", "Helvetica-Bold", 12),
        ],
    )
    fatti.append(percorso)

    # 11. Rapportino: ore e persone, il costo della manodopera.
    percorso = DESTINAZIONE / "11-rapportino.pdf"
    _pdf(
        percorso,
        [
            ("RAPPORTINO GIORNALIERO DI CANTIERE", "Helvetica-Bold", 16),
            ("", "Helvetica", 11),
            ("Cantiere: Residenza Le Palme, Catania", "Helvetica", 11),
            ("Data: 24/07/2026", "Helvetica-Bold", 12),
            ("", "Helvetica", 11),
            ("Nominativo | Mansione | Ore | Tariffa", "Helvetica-Bold", 11),
            ("Salvo Torrisi | Capocantiere | 8 | 32,00", "Helvetica", 11),
            ("Mario Rossi | Muratore | 8 | 26,50", "Helvetica", 11),
            ("Giuseppe Leotta | Manovale | 6 | 22,00", "Helvetica", 11),
            ("", "Helvetica", 11),
            ("Lavorazioni: getto solaio piano primo, casseratura pilastri.", "Helvetica", 10),
        ],
    )
    fatti.append(percorso)

    # 12. Il file che non si può leggere: l'operatore non deve vedere un errore.
    percorso = DESTINAZIONE / "12-file-non-leggibile.txt"
    percorso.write_text(
        "Questo non e' un documento di cantiere.\n"
        "Serve a mostrare cosa succede quando si carica un file che il sistema\n"
        "non sa leggere: nessun errore in faccia a chi carica, se ne occupa l'ufficio.\n",
        encoding="utf-8",
    )
    fatti.append(percorso)

    return fatti


if __name__ == "__main__":
    for percorso in genera():
        print(f"{percorso.stat().st_size:>8} B  {percorso.name}")
