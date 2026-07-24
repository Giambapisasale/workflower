"""Diagnosi: l'analisi automatica degli errori con proposta di risoluzione.

Solo admin. Sono le API dietro la pagina "Diagnosi": elenco delle diagnosi
(categoria ``dato`` = risolvibile modificando skill/tool/schema; ``architettura``
= sola analisi sul codice-cornice), l'avvio dell'analisi sui log recenti e la
chiusura (risolta/archiviata). Nulla si applica da qui: è una proposta.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_dal, get_diagnostico, richiedi_admin
from app.core.auth import Utente
from app.core.dal import DAL, NotFoundError
from app.core.diagnostico import Diagnostico

router = APIRouter(tags=["diagnoses"])


@router.get("/diagnoses")
def elenco_diagnosi(
    stato: str | None = Query(default=None),
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Le diagnosi registrate, dalla più recente (filtrabili per stato)."""
    diagnosi = dal.list_diagnosi()
    if stato:
        diagnosi = [d for d in diagnosi if d.get("stato") == stato]
    diagnosi.sort(key=lambda d: d.get("creato") or "", reverse=True)
    return {"diagnosi": diagnosi}


@router.get("/diagnoses/{diagnosi_id}")
def dettaglio_diagnosi(
    diagnosi_id: str,
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    try:
        return dal.leggi_diagnosi(diagnosi_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="diagnosi non trovata") from exc


class AnalizzaRichiesta(BaseModel):
    giorni: int = 1


@router.post("/diagnoses/analyze")
def analizza(
    body: AnalizzaRichiesta | None = None,
    _admin: Utente = Depends(richiedi_admin),
    diagnostico: Diagnostico = Depends(get_diagnostico),
) -> dict[str, Any]:
    """Avvia l'analisi degli errori recenti: una diagnosi per firma distinta."""
    giorni = body.giorni if body else 1
    diagnosi = diagnostico.analizza_recenti(giorni=giorni)
    return {"analizzate": len(diagnosi), "diagnosi": diagnosi}


@router.post("/diagnoses/{diagnosi_id}/resolve")
def risolvi(
    diagnosi_id: str,
    admin: Utente = Depends(richiedi_admin),
    diagnostico: Diagnostico = Depends(get_diagnostico),
) -> dict[str, Any]:
    try:
        return diagnostico.risolvi(diagnosi_id, admin.username)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="diagnosi non trovata") from exc


@router.post("/diagnoses/{diagnosi_id}/archive")
def archivia(
    diagnosi_id: str,
    admin: Utente = Depends(richiedi_admin),
    diagnostico: Diagnostico = Depends(get_diagnostico),
) -> dict[str, Any]:
    try:
        return diagnostico.archivia(diagnosi_id, admin.username)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="diagnosi non trovata") from exc
