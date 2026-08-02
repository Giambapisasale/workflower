#!/usr/bin/env python3
"""Verifica del parser documenti (Docling): risponde, converte, e usa la GPU.

NON è un test pytest: si lancia a mano (o in un runbook di deploy) e stampa
PASS/FAIL per passo, con exit code != 0 al primo problema bloccante.

Le tre domande a cui risponde, nell'ordine in cui contano:

1. **C'è?** — ``DOCLING_URL`` configurata e ``/health`` che risponde.
2. **Converte?** — un PDF e un DOCX generati al volo, con tabella, e si controlla
   che la tabella torni davvero come tabella. Il DOCX è il caso che senza Docling
   non esiste proprio: nessun modello vision apre un file Word.
3. **Usa la GPU?** — si campiona ``nvidia-smi`` durante la conversione. Se la GPU
   non si muove, il container sta girando su CPU: funziona lo stesso, ma dieci
   volte più piano, e su questa infrastruttura non è ciò che vogliamo.

Uso:
    make docling-check
    make docling-check ARGS="--url http://127.0.0.1:5001"

Su Windows usare 127.0.0.1 e non "localhost": il resolver tenta prima IPv6 e paga
~21 secondi di timeout a ogni chiamata prima di ripiegare su IPv4.
"""

import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path

# I messaggi usano frecce ed em-dash: su Windows la console è cp1252 e un print()
# fallirebbe con UnicodeEncodeError proprio mentre stampa un [PASS].
for _flusso in (sys.stdout, sys.stderr):
    if hasattr(_flusso, "reconfigure"):
        _flusso.reconfigure(encoding="utf-8", errors="replace")

import httpx  # noqa: E402  (dopo la riconfigurazione dei flussi)
import pymupdf  # noqa: E402

from app.core.docling import DoclingClient, DoclingConfig, DoclingError  # noqa: E402

ESITO = {True: "[PASS]", False: "[FAIL]"}
_problemi = 0


def passo(ok: bool, titolo: str, dettaglio: str = "") -> bool:
    global _problemi
    if not ok:
        _problemi += 1
    print(f"{ESITO[ok]} {titolo}" + (f" — {dettaglio}" if dettaglio else ""))
    return ok


# ------------------------------------------------------------ documenti di prova


def pdf_di_prova(cartella: Path) -> Path:
    """Un PDF con una riga tabellare, generato senza dipendenze extra."""
    percorso = cartella / "prova-docling.pdf"
    documento = pymupdf.open()
    pagina = documento.new_page()
    pagina.insert_text((60, 80), "IMPRESA DI PROVA S.r.l.", fontsize=14)
    pagina.insert_text((60, 110), "FATTURA N. 1/2026 del 31/07/2026", fontsize=12)
    pagina.insert_text((60, 150), "Descrizione | Quantita | Importo", fontsize=10)
    pagina.insert_text((60, 170), "Calcestruzzo Rck 30 | 12,50 mc | EUR 1.775,00", fontsize=10)
    pagina.insert_text((60, 210), "TOTALE: EUR 1.775,00", fontsize=11)
    documento.save(percorso)
    documento.close()
    return percorso


def docx_di_prova(cartella: Path) -> Path | None:
    """Un DOCX minimo ma valido, scritto a mano (niente python-docx da installare).

    Un ``.docx`` è uno zip di XML: per provare che Docling apra i file d'ufficio
    basta il minimo sindacale, ed è meglio di una dipendenza in più in uno script
    diagnostico.
    """
    import zipfile

    percorso = cartella / "prova-docling.docx"
    tipi = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    def paragrafo(testo: str) -> str:
        return f"<w:p><w:r><w:t>{testo}</w:t></w:r></w:p>"

    def cella(testo: str) -> str:
        return f"<w:tc><w:tcPr/>{paragrafo(testo)}</w:tc>"

    def riga(*celle: str) -> str:
        return "<w:tr>" + "".join(cella(c) for c in celle) + "</w:tr>"

    tabella = (
        "<w:tbl><w:tblPr/><w:tblGrid><w:gridCol/><w:gridCol/><w:gridCol/></w:tblGrid>"
        + riga("Codice", "Descrizione", "Importo")
        + riga("01.A02.001", "Scavo a sezione obbligata", "4.132,50")
        + riga("01.A04.012", "Calcestruzzo per fondazioni", "8.875,00")
        + "</w:tbl>"
    )
    documento = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + paragrafo("COMPUTO METRICO DI PROVA")
        + tabella
        + paragrafo("TOTALE: 13.007,50")
        + "</w:body></w:document>"
    )
    try:
        with zipfile.ZipFile(percorso, "w", zipfile.ZIP_DEFLATED) as pacchetto:
            pacchetto.writestr("[Content_Types].xml", tipi)
            pacchetto.writestr("_rels/.rels", rels)
            pacchetto.writestr("word/document.xml", documento)
    except OSError as exc:
        print(f"       (DOCX di prova non creato: {exc})")
        return None
    return percorso


# ---------------------------------------------------------------- sonda della GPU


class SondaGpu:
    """Campiona ``nvidia-smi`` in un thread mentre gira la conversione."""

    def __init__(self) -> None:
        self.campioni: list[tuple[int, int]] = []
        self.disponibile = True
        self._attivo = False
        self._thread: threading.Thread | None = None

    def _leggi(self) -> tuple[int, int] | None:
        try:
            esito = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            self.disponibile = False
            return None
        righe = (esito.stdout or "").strip().splitlines()
        if not righe:
            self.disponibile = False
            return None
        try:
            util, memoria = (int(x.strip()) for x in righe[0].split(",")[:2])
        except ValueError:
            self.disponibile = False
            return None
        return util, memoria

    def _ciclo(self) -> None:
        while self._attivo:
            campione = self._leggi()
            if campione is None:
                return
            self.campioni.append(campione)
            time.sleep(0.1)

    def __enter__(self) -> "SondaGpu":
        self._attivo = True
        self._thread = threading.Thread(target=self._ciclo, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._attivo = False
        if self._thread:
            self._thread.join(timeout=2)

    def usata(self) -> tuple[bool, str]:
        if not self.disponibile:
            return False, "nvidia-smi non disponibile: non posso dirlo da qui"
        if not self.campioni:
            return False, "nessun campione raccolto"
        util = [c[0] for c in self.campioni]
        memoria = [c[1] for c in self.campioni]
        dettaglio = (
            f"utilizzo max {max(util)}%, VRAM {min(memoria)}→{max(memoria)} MiB "
            f"({len(self.campioni)} campioni)"
        )
        return max(util) > 0, dettaglio


# ------------------------------------------------------------------------ passi


def main() -> int:
    argomenti = argparse.ArgumentParser(description=__doc__)
    argomenti.add_argument("--url", help="URL del sidecar (default: DOCLING_URL dall'ambiente)")
    opzioni = argomenti.parse_args()

    config = (
        DoclingConfig(base_url=opzioni.url) if opzioni.url else DoclingConfig.da_env()
    )
    if not passo(
        config is not None,
        "configurazione",
        ""
        if config is not None
        else "DOCLING_URL assente e nessun --url: il tool leggi_documento resterebbe spento",
    ):
        return 1
    assert config is not None
    print(f"       sidecar: {config.base_url}")

    try:
        salute = httpx.get(config.base_url.rstrip("/") + "/health", timeout=10)
        raggiungibile = salute.status_code == 200
        dettaglio = f"HTTP {salute.status_code}"
    except Exception as exc:
        raggiungibile, dettaglio = False, str(exc)[:120]
    if not passo(raggiungibile, "il sidecar risponde", dettaglio):
        print("\n       Avvialo con:  make docling-up")
        return 1

    cartella = Path(__file__).resolve().parent.parent / "fixtures"
    cartella.mkdir(exist_ok=True)
    client = DoclingClient(config=config)

    pdf = pdf_di_prova(cartella)
    with SondaGpu() as sonda:
        try:
            avvio = time.perf_counter()
            esito = client.converti(pdf)
            secondi = time.perf_counter() - avvio
        except DoclingError as exc:
            passo(False, "conversione del PDF", str(exc)[:160])
            return 1
    passo(
        "TOTALE" in esito["markdown"],
        "conversione del PDF",
        f"{len(esito['markdown'])} caratteri in {secondi:.2f}s "
        f"(qualità: {esito['qualita']}, motore: {esito['secondi']}s)",
    )

    usata, dettaglio_gpu = sonda.usata()
    passo(usata, "la GPU sta lavorando", dettaglio_gpu)

    docx = docx_di_prova(cartella)
    if docx is not None:
        try:
            esito_docx = client.converti(docx)
            markdown = esito_docx["markdown"]
            passo(
                "Calcestruzzo per fondazioni" in markdown and "|" in markdown,
                "conversione del DOCX (con tabella)",
                f"{len(markdown)} caratteri, tabella {'ricostruita' if '|' in markdown else 'PERSA'}",
            )
        except DoclingError as exc:
            passo(False, "conversione del DOCX", str(exc)[:160])

    print()
    if _problemi:
        print(f"{_problemi} problema/i: vedi sopra.")
        return 1
    print("Tutto a posto: il parser è raggiungibile, converte e usa la GPU.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
