"""Tool ``ocr_pdf``: pagine del documento → immagini PNG per l'LLM multimodale."""

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


def esegui(data_dir: Path, path: str) -> dict:
    base = Path(data_dir).resolve()
    file = (base / path).resolve()
    if not file.is_relative_to(base):
        raise ToolError(f"percorso fuori dal repo dati: {path}")
    if file.suffix.lower() not in ESTENSIONI:
        raise ToolError(f"formato non supportato: {file.suffix} (attesi pdf/png/jpg)")
    if not file.is_file():
        raise ToolError(f"documento non trovato: {path}")

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
