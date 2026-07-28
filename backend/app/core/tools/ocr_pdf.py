"""Tool ``ocr_pdf``: pagine del documento → immagini PNG per l'LLM multimodale.

Accanto al tool vive :func:`testo_pagine`, che rende le stesse pagine come
**testo**: non è un tool (l'LLM non la chiama), serve all'harness T3 per valutare
un modello locale che non ha una torre visiva. Sta qui perché qui vivono già
pymupdf e la validazione del percorso.
"""

import base64
from pathlib import Path

import pymupdf

from app.core.tools.base import ToolError

DPI = 150
MAX_PAGINE = 10
ESTENSIONI = {".pdf", ".png", ".jpg", ".jpeg"}

SCHEMA = {
    "type": "function",
    "function": {
        "name": "ocr_pdf",
        "description": (
            "Converte le pagine di un documento (PDF o foto) in immagini PNG "
            "che ti vengono mostrate. Usalo per leggere il contenuto del documento."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Percorso del documento relativo al repo dati, "
                        "es. blobs/fatture/2026/doc.pdf"
                    ),
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
}


def _percorso_valido(data_dir: Path, path: str) -> Path:
    base = Path(data_dir).resolve()
    file = (base / path).resolve()
    if not file.is_relative_to(base):
        raise ToolError(f"percorso fuori dal repo dati: {path}")
    if file.suffix.lower() not in ESTENSIONI:
        raise ToolError(f"formato non supportato: {file.suffix} (attesi pdf/png/jpg)")
    if not file.is_file():
        raise ToolError(f"documento non trovato: {path}")
    return file


def esegui(data_dir: Path, path: str) -> dict:
    file = _percorso_valido(data_dir, path)
    try:
        documento = pymupdf.open(file)
    except Exception as exc:
        raise ToolError(f"documento illeggibile: {exc}") from exc
    with documento:
        if documento.page_count > MAX_PAGINE:
            raise ToolError(f"troppe pagine ({documento.page_count} > {MAX_PAGINE})")
        immagini = [
            base64.b64encode(pagina.get_pixmap(dpi=DPI).tobytes("png")).decode("ascii")
            for pagina in documento
        ]
    return {"pagine": len(immagini), "immagini_png_base64": immagini}


def testo_pagine(data_dir: Path, path: str) -> list[str]:
    """Lo strato testuale delle pagine, una stringa per pagina.

    Non è un tool: è la controparte testuale di :func:`esegui`, per valutare un
    modello T3 che non legge immagini. Attenzione a cosa si perde: il **layout**
    (su una fattura, "Ritenuta d'acconto" in calce è riconoscibile perché è in
    calce) e le tabelle, che arrivano appiattite. Su un documento *scansionato* lo
    strato testuale non esiste: la pagina torna stringa vuota, e chi chiama deve
    trattarlo come "non disponibile", non come "pagina vuota".
    """
    file = _percorso_valido(data_dir, path)
    try:
        documento = pymupdf.open(file)
    except Exception as exc:
        raise ToolError(f"documento illeggibile: {exc}") from exc
    with documento:
        if documento.page_count > MAX_PAGINE:
            raise ToolError(f"troppe pagine ({documento.page_count} > {MAX_PAGINE})")
        return [pagina.get_text().strip() for pagina in documento]
