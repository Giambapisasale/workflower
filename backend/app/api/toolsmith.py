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

from app.api.deps import get_dal, get_improver, get_toolsmith, richiedi_admin
from app.core.auth import Utente
from app.core.dal import DAL, CatalogoNonValido, NotFoundError
from app.core.improver import Improver
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


def _proposta_da_decidere(dal: DAL, proposta_id: str) -> dict[str, Any]:
    try:
        proposta = dal.leggi_proposta(proposta_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="proposta non trovata") from exc
    if proposta.get("stato") != "proposta":
        raise HTTPException(status_code=409, detail=f"proposta già {proposta.get('stato')}")
    return proposta


@router.post("/proposte/{proposta_id}/approve")
def approva_proposta(
    proposta_id: str,
    admin: Utente = Depends(richiedi_admin),
    toolsmith: Toolsmith = Depends(get_toolsmith),
    improver: Improver = Depends(get_improver),
) -> dict[str, Any]:
    """Approva: registra il tool (M15) e propone la patch di skill (replay golden)."""
    proposta = _proposta_da_decidere(toolsmith.dal, proposta_id)
    try:
        esito = toolsmith.approva(proposta, admin.username, improver)
    except CatalogoNonValido as exc:
        raise HTTPException(status_code=409, detail=f"tool non registrabile: {exc}") from exc
    except ToolsmithError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    patch = esito["patch"]
    return {
        "proposta": esito["proposta"]["id"],
        "stato": esito["proposta"]["stato"],
        "pytool": esito["pytool"]["nome"],
        "patch_skill": {
            "id": patch["id"],
            "replay": patch["replay"],
            "diff_skill": patch["diff_skill"],
        }
        if patch
        else None,
    }


@router.post("/proposte/{proposta_id}/reject")
def rifiuta_proposta(
    proposta_id: str,
    admin: Utente = Depends(richiedi_admin),
    toolsmith: Toolsmith = Depends(get_toolsmith),
) -> dict[str, str]:
    proposta = _proposta_da_decidere(toolsmith.dal, proposta_id)
    aggiornata = toolsmith.rifiuta(proposta, admin.username)
    return {"id": aggiornata["id"], "stato": aggiornata["stato"]}
