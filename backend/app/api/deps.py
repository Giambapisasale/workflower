"""Dipendenze FastAPI (DI, niente singleton globali — piano §6).

Il DAL è uno per applicazione e nasce pigro: l'app parte anche senza repo
dati (health check), ma il primo endpoint che ne ha bisogno pretende il
seed. Un solo DAL = un solo lock di scrittura, anche per i task in
background.
"""

import threading
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.agente_dati import AgenteDati, EvolutoreAgente
from app.core.auth import AuthError, Utente, decodifica_token
from app.core.dal import DAL, DalError
from app.core.diagnostico import Diagnostico
from app.core.docling import DoclingClient
from app.core.erp import ErpClient
from app.core.eval_agente import EvalAgente
from app.core.eval_t3 import EvalT3
from app.core.gateway import Gateway
from app.core.improver import Improver
from app.core.interroga import Interroga
from app.core.runtime import WorkflowRuntime
from app.core.toolsmith import Toolsmith

_bearer = HTTPBearer(auto_error=False)
_dal_lock = threading.Lock()


def get_data_dir(request: Request) -> Path:
    return request.app.state.data_dir


def dal_da_app(app: Any) -> DAL:
    """Il DAL condiviso dell'app (uno solo → un solo lock di scrittura).

    Usato dai request handler (via :func:`get_dal`) e dai task fuori richiesta
    (il trigger di diagnostica), così tutte le scritture passano dallo stesso
    lock single-writer. Solleva ``DalError`` se il repo dati non è pronto.
    """
    with _dal_lock:
        dal = getattr(app.state, "dal", None)
        if dal is None:
            dal = DAL(app.state.data_dir)
            app.state.dal = dal
    return dal


def get_dal(request: Request) -> DAL:
    try:
        return dal_da_app(request.app)
    except DalError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def get_gateway(request: Request) -> Gateway:
    return request.app.state.gateway


def get_erp(request: Request) -> ErpClient:
    """Il client ERP condiviso dell'app (uno solo, iniettabile nei test).

    Sempre presente: se l'ERP non è configurato via env, il client è inattivo
    (:meth:`ErpClient.attivo` falso) e la sincronizzazione a valle è no-op.
    """
    return request.app.state.erp


def get_docling(request: Request) -> DoclingClient:
    """Il client Docling condiviso dell'app (uno solo, iniettabile nei test).

    Sempre presente: se ``DOCLING_URL`` non è configurata il client è inattivo e
    il tool ``leggi_documento`` non viene registrato nel ``Toolset``.
    """
    return request.app.state.docling


def get_runtime(
    dal: DAL = Depends(get_dal),
    gateway: Gateway = Depends(get_gateway),
    docling: DoclingClient = Depends(get_docling),
) -> WorkflowRuntime:
    return WorkflowRuntime(dal, gateway, docling=docling)


def get_interroga(
    dal: DAL = Depends(get_dal), gateway: Gateway = Depends(get_gateway)
) -> Interroga:
    return Interroga(dal, gateway)


def get_agente_dati(
    dal: DAL = Depends(get_dal), gateway: Gateway = Depends(get_gateway)
) -> AgenteDati:
    """Agente conversazionale read-only, separato dal vecchio text-to-SQL."""
    return AgenteDati(dal, gateway)


def get_evolutore_agente(
    dal: DAL = Depends(get_dal), gateway: Gateway = Depends(get_gateway)
) -> EvolutoreAgente:
    return EvolutoreAgente(dal, gateway)


def get_improver(
    dal: DAL = Depends(get_dal), gateway: Gateway = Depends(get_gateway)
) -> Improver:
    return Improver(dal, gateway)


def get_toolsmith(
    dal: DAL = Depends(get_dal), gateway: Gateway = Depends(get_gateway)
) -> Toolsmith:
    return Toolsmith(dal, gateway)


def get_eval_t3(
    dal: DAL = Depends(get_dal), gateway: Gateway = Depends(get_gateway)
) -> EvalT3:
    return EvalT3(dal, gateway)


def get_eval_interroga(
    dal: DAL = Depends(get_dal), gateway: Gateway = Depends(get_gateway)
) -> EvalAgente:
    """Nome storico della dipendenza, ora collegato al valutatore tool-first."""
    return EvalAgente(dal, gateway)


def get_diagnostico(
    dal: DAL = Depends(get_dal), gateway: Gateway = Depends(get_gateway)
) -> Diagnostico:
    return Diagnostico(dal, gateway)


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
