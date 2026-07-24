"""Documenti di esempio scaricabili dall'interfaccia (uno per ogni tipo gestito).

I PDF sono asset versionati sotto ``seed_assets/samples/`` (package-data): così
sono nell'immagine di produzione senza dipendere da reportlab (dev-only) né dal
repo ``data/``. Servono a chi prova l'app per avere un documento da caricare.
"""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import utente_corrente
from app.core.auth import Utente

router = APIRouter(tags=["samples"])

SAMPLES_DIR = (Path(__file__).resolve().parent.parent / "seed_assets" / "samples").resolve()


def _catalogo() -> list[dict[str, Any]]:
    percorso = SAMPLES_DIR / "index.json"
    if not percorso.is_file():
        return []
    try:
        voci = json.loads(percorso.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    # Solo gli esempi il cui PDF è davvero presente nell'immagine.
    return [v for v in voci if (SAMPLES_DIR / str(v.get("file", ""))).is_file()]


@router.get("/samples")
def elenco_esempi(_utente: Utente = Depends(utente_corrente)) -> dict[str, Any]:
    """I documenti di esempio disponibili (metadati per la UI)."""
    return {"esempi": _catalogo()}


@router.get("/samples/{file}")
def scarica_esempio(
    file: str,
    _utente: Utente = Depends(utente_corrente),
) -> FileResponse:
    """Scarica un PDF di esempio: solo i file del catalogo, path confinato."""
    consentiti = {str(v["file"]) for v in _catalogo()}
    percorso = (SAMPLES_DIR / file).resolve()
    if (
        file not in consentiti
        or SAMPLES_DIR not in percorso.parents
        or not percorso.is_file()
    ):
        raise HTTPException(status_code=404, detail="esempio non trovato")
    return FileResponse(percorso, media_type="application/pdf", filename=percorso.name)
