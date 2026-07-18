"""Dipendenze FastAPI (DI, niente singleton globali — piano §6).

Il DAL è uno per applicazione e nasce pigro: l'app parte anche senza repo
dati (health check), ma il primo endpoint che ne ha bisogno pretende il
seed. Un solo DAL = un solo lock di scrittura, anche per i task in
background.
"""

import threading
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.auth import AuthError, Utente, decodifica_token
from app.core.dal import DAL, DalError
from app.core.gateway import Gateway
from app.core.improver import Improver
from app.core.interroga import Interroga
from app.core.runtime import WorkflowRuntime

_bearer = HTTPBearer(auto_error=False)
_dal_lock = threading.Lock()


def get_data_dir(request: Request) -> Path:
    return request.app.state.data_dir


def get_dal(request: Request) -> DAL:
    with _dal_lock:
        dal = getattr(request.app.state, "dal", None)
        if dal is None:
            try:
                dal = DAL(request.app.state.data_dir)
            except DalError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            request.app.state.dal = dal
    return dal


def get_gateway(request: Request) -> Gateway:
    return request.app.state.gateway


def get_runtime(
    dal: DAL = Depends(get_dal), gateway: Gateway = Depends(get_gateway)
) -> WorkflowRuntime:
    return WorkflowRuntime(dal, gateway)


def get_interroga(
    dal: DAL = Depends(get_dal), gateway: Gateway = Depends(get_gateway)
) -> Interroga:
    return Interroga(dal.data_dir, gateway)


def get_improver(
    dal: DAL = Depends(get_dal), gateway: Gateway = Depends(get_gateway)
) -> Improver:
    return Improver(dal, gateway)


def utente_corrente(
    credenziali: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Utente:
    if credenziali is None:
        raise HTTPException(status_code=401, detail="accesso richiesto")
    try:
        return decodifica_token(credenziali.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def richiedi_admin(utente: Utente = Depends(utente_corrente)) -> Utente:
    if not utente.is_admin:
        raise HTTPException(status_code=403, detail="operazione riservata all'ufficio (admin)")
    return utente
