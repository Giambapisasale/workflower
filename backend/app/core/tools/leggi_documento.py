"""Tool ``leggi_documento``: il documento come **testo strutturato** (Docling).

È il gemello testuale di ``ocr_pdf``, non il suo sostituto. I due convivono di
proposito, e la differenza è nel *tipo* di documento, non nella qualità:

- ``leggi_documento`` — PDF nati digitali, Word, Excel: restituisce Markdown con
  **tabelle ricostruite** e ordine di lettura. Costa 16–34 volte meno token delle
  stesse pagine come immagini, e legge formati che il sistema oggi rifiuta.
- ``ocr_pdf`` — foto scattate in cantiere, scansioni storte: su quelle un modello
  con torre visiva legge meglio di qualunque pipeline OCR + layout.

Il lavoro pesante (layout, TableFormer) gira **su GPU nel sidecar**, mai in questo
processo: qui c'è solo una POST. Se il sidecar non è configurato il tool non viene
nemmeno registrato nel ``Toolset``, e per il modello non esiste.

Ogni fallimento diventa :class:`ToolError`, che il runtime rimanda al modello come
risultato d'errore: il modello prosegue con ``ocr_pdf`` e lo step si chiude
comunque. **Mai un single-point-of-failure sull'ingestione.**
"""

from pathlib import Path

import pymupdf

from app.core.docling import ESTENSIONI as ESTENSIONI_DOCLING
from app.core.docling import QUALITA_BASSA, DoclingClient, DoclingError
from app.core.tools.base import ToolError, percorso_nel_repo

# Stesso tetto di ``ocr_pdf``: un documento più lungo non è un documento di
# cantiere, è un allegato tecnico, e riempirebbe la finestra di contesto.
MAX_PAGINE = 10

SCHEMA = {
    "type": "function",
    "function": {
        "name": "leggi_documento",
        "description": (
            "Legge un documento nato digitale (PDF, Word .docx, Excel .xlsx) e te "
            "lo restituisce come testo Markdown, con le tabelle ricostruite. "
            "Usalo come PRIMA scelta su questi formati: è più preciso sulle tabelle "
            "e molto più economico delle immagini. NON usarlo per le foto scattate "
            "col telefono: per quelle usa ocr_pdf."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Percorso del documento relativo al repo dati, "
                        "es. blobs/caricati/2026/doc.pdf"
                    ),
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
}


def _pagine_pdf(file: Path) -> int | None:
    """Il numero di pagine, se è un PDF; ``None`` per gli altri formati.

    Serve a fermare un documento enorme **prima** di occupare la GPU del sidecar,
    come fa ``ocr_pdf`` prima di rasterizzare. Su un PDF illeggibile non si
    solleva: sarà Docling a dire che non ce la fa, con un messaggio migliore del
    nostro.
    """
    if file.suffix.lower() != ".pdf":
        return None
    try:
        with pymupdf.open(file) as documento:
            return int(documento.page_count)
    except Exception:
        return None


def esegui(data_dir: Path, client: DoclingClient, path: str) -> dict:
    file = percorso_nel_repo(data_dir, path, ESTENSIONI_DOCLING, "pdf/docx/xlsx/pptx/html/csv")

    pagine = _pagine_pdf(file)
    if pagine is not None and pagine > MAX_PAGINE:
        raise ToolError(f"troppe pagine ({pagine} > {MAX_PAGINE})")

    try:
        esito = client.converti(file)
    except DoclingError as exc:
        # Il modello legge questo messaggio e deve capirci cosa fare dopo.
        raise ToolError(f"{exc} — riprova leggendo le pagine con ocr_pdf") from exc

    risultato: dict = {"markdown": esito["markdown"]}
    if pagine is not None:
        risultato["pagine"] = pagine
    if esito["troncato"]:
        risultato["avviso"] = (
            "Il documento è più lungo di quanto entri qui: il testo è troncato. "
            "Se ti serve la parte finale, leggi le pagine con ocr_pdf."
        )
    if esito["qualita"] in QUALITA_BASSA:
        # Docling stesso dichiara di non essersi fidato: passarlo al modello è più
        # onesto che consegnare un testo dubbio senza dirlo.
        risultato["avviso_qualita"] = (
            f"La lettura automatica è di qualità '{esito['qualita']}': se un dato "
            "non torna, ricontrolla la pagina con ocr_pdf."
        )
    return risultato
