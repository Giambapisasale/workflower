"""Contratto ritirato del precedente percorso di interrogazione."""

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["legacy"])


@router.post("/ask")
def ask_ritirato() -> None:
    """Non riattivare: l'interrogazione passa esclusivamente da ``/agent``."""
    raise HTTPException(
        status_code=410,
        detail="interrogazione storica ritirata: usa l'agente dati conversazionale",
    )
