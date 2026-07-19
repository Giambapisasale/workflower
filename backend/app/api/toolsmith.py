"""Toolsmith admin (Fase 3, §3.6 punti 1–2, M16).

Espone il consolidamento skill→tool Python: i **candidati** (calcoli corretti in
modo ricorrente, dal delta estratto→validato) e la generazione di una **proposta**
di tool — codice + schema (T1) e test ricavati dalle coppie storiche validate,
eseguiti in sandbox. La proposta è dato ispezionabile; **nulla viene attivato**:
l'approvazione e la registrazione nel registry sono di M17.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_dal, get_toolsmith, richiedi_admin
from app.core.auth import Utente
from app.core.dal import DAL, NotFoundError
from app.core.toolsmith import Toolsmith, ToolsmithError

router = APIRouter(prefix="/toolsmith", tags=["toolsmith"])


@router.get("/candidati")
def candidati(
    _admin: Utente = Depends(richiedi_admin),
    toolsmith: Toolsmith = Depends(get_toolsmith),
) -> dict[str, Any]:
    """I campi corretti in modo ricorrente: dove vale la pena consolidare un tool."""
    return {"candidati": toolsmith.candidati()}


class Candidato(BaseModel):
    nome: str
    tipo: str
    campi_input: list[str]
    campo_output: str
    workflow: str | None = None


@router.post("/proponi")
def proponi(
    body: Candidato,
    _admin: Utente = Depends(richiedi_admin),
    toolsmith: Toolsmith = Depends(get_toolsmith),
) -> dict[str, Any]:
    """Genera una proposta di tool Python dal candidato (codice+schema T1, test dai trace)."""
    try:
        return toolsmith.proponi(body.model_dump())
    except ToolsmithError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/proposte")
def elenco_proposte(
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    proposte = dal.list_proposte()
    proposte.sort(key=lambda p: p.get("creato") or "", reverse=True)
    return {"proposte": proposte}


@router.get("/proposte/{proposta_id}")
def dettaglio_proposta(
    proposta_id: str,
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    try:
        return dal.leggi_proposta(proposta_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="proposta non trovata") from exc
