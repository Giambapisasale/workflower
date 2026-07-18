"""Log & Dataset admin (piano §M6): conteggi, costi, export, fingerprint query."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import get_data_dir, richiedi_admin
from app.core.auth import Utente
from app.core.dataset import conteggio_fingerprint, statistiche

router = APIRouter(tags=["dataset"])


@router.get("/dataset/stats")
def stats(
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> dict[str, Any]:
    return statistiche(data_dir)


@router.get("/dataset/queries")
def queries(
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> dict[str, Any]:
    """Le query di ``/ask`` per fingerprint: i duplicati sono candidati a tool (§3.6)."""
    return {"gruppi": conteggio_fingerprint(data_dir)}


@router.get("/dataset/export")
def export(
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> FileResponse:
    """Scarica ``dataset/toolcalls.jsonl`` (esempi per il fine-tuning, §3.7)."""
    percorso = Path(data_dir) / "dataset" / "toolcalls.jsonl"
    if not percorso.is_file():
        raise HTTPException(status_code=404, detail="dataset non ancora disponibile")
    return FileResponse(
        percorso, media_type="application/x-ndjson", filename="toolcalls.jsonl"
    )
