"""Endpoint admin per l'integrazione ERP (ciclo passivo).

La sincronizzazione WF→ERP dei documenti avviene alla validazione (api/review.py);
qui vivono le operazioni *pull* e di manutenzione. Per ora: la rilettura dello stato
di pagamento dall'ERP (M27), riservata all'ufficio (admin).
"""

from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import get_dal, get_erp, richiedi_admin
from app.core.auth import Utente
from app.core.dal import DAL
from app.core.erp import ErpClient, rileggi_pagamenti

router = APIRouter(tags=["erp"])


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
