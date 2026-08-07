"""API del nuovo agente dati conversazionale."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import (
    get_agente_dati,
    get_dal,
    get_evolutore_agente,
    richiedi_admin,
    utente_corrente,
)
from app.core.agente_dati import (
    AgenteDati,
    AgenteDatiError,
    CatalogoDatiError,
    EvolutoreAgente,
    aggiorna_configurazione,
    configurazione,
)
from app.core.auth import Utente
from app.core.dal import DAL
from app.core.logbook import ottieni_logger

router = APIRouter(prefix="/agent", tags=["agent"])


class MessaggioRichiesta(BaseModel):
    content: str = Field(min_length=1, max_length=2_000)


@router.get("/conversation")
def conversazione(
    utente: Utente = Depends(utente_corrente), agente: AgenteDati = Depends(get_agente_dati)
) -> dict[str, Any]:
    return agente.conversazione(utente.username)


@router.post("/messages")
def messaggio(
    body: MessaggioRichiesta,
    utente: Utente = Depends(utente_corrente),
    agente: AgenteDati = Depends(get_agente_dati),
) -> dict[str, Any]:
    try:
        return agente.rispondi(
            username=utente.username,
            ruolo="admin" if utente.is_admin else "op",
            cantieri=utente.cantieri,
            contenuto=body.content,
        )
    except CatalogoDatiError as exc:
        # L'installazione è incompleta: non è colpa della domanda, e riformularla
        # non serve. Il dettaglio (quale file, quale comando) va al log per chi
        # può agire; all'operatore va una frase che non contiene un percorso né
        # un comando di shell — leggerli non lo aiuterebbe.
        ottieni_logger("api").error("catalogo agente dati non disponibile: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Non riesco a rispondere in questo momento: ci pensa l'ufficio.",
        ) from exc
    except AgenteDatiError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/conversation/reset")
def reset(
    utente: Utente = Depends(utente_corrente), agente: AgenteDati = Depends(get_agente_dati)
) -> dict[str, Any]:
    return agente.reset(utente.username)


@router.get("/config")
def config(
    _admin: Utente = Depends(richiedi_admin), dal: DAL = Depends(get_dal)
) -> dict[str, int]:
    return configurazione(dal.data_dir)


class ConfigRichiesta(BaseModel):
    max_messages: int


@router.put("/config")
def aggiorna_config(
    body: ConfigRichiesta,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, int]:
    try:
        return aggiorna_configurazione(dal, body.max_messages, admin.username)
    except AgenteDatiError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/evolution")
def evoluzione(
    _admin: Utente = Depends(richiedi_admin),
    agente: AgenteDati = Depends(get_agente_dati),
    evolutore: EvolutoreAgente = Depends(get_evolutore_agente),
) -> dict[str, Any]:
    from app.core.agente_dati import RegistryToolDati

    try:
        tools = RegistryToolDati(agente.data_dir).elenco_admin()
    except AgenteDatiError as exc:
        # Catalogo assente o non valido: è un problema dell'installazione, non
        # della richiesta. Senza questo `except` la pagina Evoluzione rispondeva
        # 500 con un traceback e nessuna indicazione su cosa fare.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"tools": tools, "proposals": evolutore.elenco()}


class PropostaRichiesta(BaseModel):
    feedback: str = Field(min_length=3, max_length=4_000)


@router.post("/evolution/proposals")
def proponi(
    body: PropostaRichiesta,
    admin: Utente = Depends(richiedi_admin),
    evolutore: EvolutoreAgente = Depends(get_evolutore_agente),
) -> dict[str, Any]:
    try:
        return evolutore.proponi(body.feedback, admin.username)
    except AgenteDatiError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/evolution/proposals/{proposal_id}/approve")
def approva(
    proposal_id: str,
    admin: Utente = Depends(richiedi_admin),
    evolutore: EvolutoreAgente = Depends(get_evolutore_agente),
) -> dict[str, Any]:
    try:
        return evolutore.approva(proposal_id, admin.username)
    except AgenteDatiError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/evolution/proposals/{proposal_id}/reject")
def rifiuta(
    proposal_id: str,
    admin: Utente = Depends(richiedi_admin),
    evolutore: EvolutoreAgente = Depends(get_evolutore_agente),
) -> dict[str, Any]:
    try:
        return evolutore.rifiuta(proposal_id, admin.username)
    except AgenteDatiError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
