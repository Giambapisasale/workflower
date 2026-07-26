"""Endpoint admin per l'integrazione ERP (ciclo passivo).

La sincronizzazione WF→ERP dei documenti avviene alla validazione (api/review.py);
qui vivono le operazioni *pull* e di manutenzione. Per ora: la rilettura dello stato
di pagamento dall'ERP (M27), riservata all'ufficio (admin).
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_dal, get_erp, richiedi_admin
from app.core.auth import Utente
from app.core.dal import DAL, DalError, tipo_da_id
from app.core.erp import (
    ErpClient,
    applica_sincronizzazione,
    rileggi_pagamenti,
    risincronizza_mancanti,
    stato_sincronizzazione,
)

router = APIRouter(tags=["erp"])


@router.get("/erp/stato")
def stato(
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
    erp: ErpClient = Depends(get_erp),
) -> dict[str, Any]:
    """Stato di sincronizzazione ERP: contatori, documenti da sincronizzare, ultimi tentativi."""
    return stato_sincronizzazione(dal, erp)


@router.post("/erp/risincronizza")
def risincronizza(
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
    erp: ErpClient = Depends(get_erp),
) -> dict[str, Any]:
    """Ri-sincronizza le fatture/DDT validati rimasti senza backref ERP (recupero).

    Best-effort; si ferma se l'ERP appare irraggiungibile (fallimenti consecutivi).
    """
    return risincronizza_mancanti(dal, erp)


@router.post("/erp/risincronizza/{entity_id}")
def risincronizza_uno(
    entity_id: str,
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
    erp: ErpClient = Depends(get_erp),
) -> dict[str, Any]:
    """Ri-sincronizza un singolo documento (pulsante 'riprova' del pannello)."""
    tipo = tipo_da_id(entity_id)
    if tipo is None:
        raise HTTPException(status_code=404, detail="entità non trovata")
    try:
        entita = dal.read(tipo, entity_id)
    except DalError as exc:
        raise HTTPException(status_code=404, detail="entità non trovata") from exc
    esito = applica_sincronizzazione(dal, entita, erp)
    return esito or {"esito": "saltato", "motivo": "ERP non attivo o tipo non sincronizzabile"}


@router.post("/erp/rileggi-pagamenti")
def rileggi_pagamenti_endpoint(
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
    erp: ErpClient = Depends(get_erp),
) -> dict[str, Any]:
    """Rilegge da ERPNext lo stato di pagamento delle fatture sincronizzate.

    Crea/aggiorna un'entità ``pagamento`` per fattura (sola lettura ERP→WF).
    No-op se l'ERP non è configurato.
    """
    return rileggi_pagamenti(dal, erp)
