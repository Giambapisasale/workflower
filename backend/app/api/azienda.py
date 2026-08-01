"""L'azienda corrente: leggerla e modificarla dalla UI dell'ufficio.

Riservata all'admin: è il riferimento con cui si stabilisce se una fattura è
intestata a noi, quindi non è un dato che l'operatore debba poter cambiare.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_dal, richiedi_admin
from app.core.auth import Utente
from app.core.azienda import AziendaNonValida, leggi, scrivi, valida
from app.core.dal import DAL

router = APIRouter(tags=["azienda"])


class AziendaCorpo(BaseModel):
    denominazione: str = ""
    indirizzo: str = ""
    partita_iva: str = ""


class AziendaRisposta(AziendaCorpo):
    configurata: bool


def _risposta(data_dir) -> AziendaRisposta:  # type: ignore[no-untyped-def]
    azienda = leggi(data_dir)
    return AziendaRisposta(**azienda.come_dizionario(), configurata=azienda.configurata())


@router.get("/config/azienda", response_model=AziendaRisposta)
def azienda_corrente(
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> AziendaRisposta:
    return _risposta(dal.data_dir)


@router.put("/config/azienda", response_model=AziendaRisposta)
def aggiorna_azienda(
    corpo: AziendaCorpo,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> AziendaRisposta:
    try:
        azienda = valida(corpo.model_dump())
    except AziendaNonValida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    percorso = scrivi(dal.data_dir, azienda)
    dal.commit_paths([percorso], f"azienda: aggiornata da {admin.username}")
    return _risposta(dal.data_dir)
