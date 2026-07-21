"""Diagnostica: il logbook trasversale + il livello di log (osservabilità §3.7).

Solo admin. Sono le API dietro la pagina "Log" della console: elenco filtrabile
degli eventi (tutte le fasi, errori in evidenza), conteggi, cambio del livello a
runtime e scarico del file del giorno.
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import get_data_dir, richiedi_admin
from app.core.auth import Utente
from app.core.logbook import (
    FASI,
    LIVELLI,
    file_log_odierno,
    imposta_livello,
    leggi_log,
    livello_corrente,
    statistiche_log,
)

router = APIRouter(tags=["logs"])

NDJSON = "application/x-ndjson"


@router.get("/logs")
def elenco_log(
    livello: str = Query(default="DEBUG"),
    fase: str | None = Query(default=None),
    q: str | None = Query(default=None),
    giorni: int = Query(default=7, ge=1, le=90),
    limite: int = Query(default=500, ge=1, le=5000),
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> dict[str, Any]:
    """Eventi di log filtrati, dal più recente. ``livello`` è la soglia minima."""
    voci = leggi_log(
        data_dir, livello_min=livello, fase=fase, testo=q, giorni=giorni, limite=limite
    )
    return {"voci": voci, "fasi": list(FASI), "livelli": list(LIVELLI)}


@router.get("/logs/stats")
def stats_log(
    giorni: int = Query(default=7, ge=1, le=90),
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> dict[str, Any]:
    """Conteggi per livello e per fase sulla finestra scelta."""
    return statistiche_log(data_dir, giorni=giorni)


@router.get("/logs/config")
def config_log(_admin: Utente = Depends(richiedi_admin)) -> dict[str, Any]:
    """Il livello di log attivo e quelli selezionabili."""
    return {"livello": livello_corrente(), "livelli": list(LIVELLI)}


class ConfigRichiesta(BaseModel):
    livello: str


@router.put("/logs/config")
def imposta_config_log(
    body: ConfigRichiesta,
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> dict[str, Any]:
    """Cambia il livello di log a runtime (persistito: sopravvive al riavvio)."""
    try:
        livello = imposta_livello(data_dir, body.livello)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"livello": livello, "livelli": list(LIVELLI)}


@router.get("/logs/export")
def export_log(
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> FileResponse:
    """Scarica il file di log di oggi (``AAAA/MM/GG.jsonl``)."""
    percorso = file_log_odierno(data_dir)
    if not percorso.is_file():
        raise HTTPException(status_code=404, detail="nessun log per oggi")
    return FileResponse(percorso, media_type=NDJSON, filename="log-oggi.jsonl")
