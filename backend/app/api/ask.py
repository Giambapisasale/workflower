"""``POST /ask`` (piano §3.4): op → risposta in italiano; admin → {sql, rows}."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_dal, get_interroga, utente_corrente
from app.api.documents import nome_cantiere
from app.core.auth import Utente
from app.core.dal import DAL
from app.core.dataset import registra_query
from app.core.interroga import Interroga, InterrogaError

router = APIRouter(tags=["ask"])


class AskRichiesta(BaseModel):
    question: str
    mode: Literal["op", "admin"] = "op"


@router.post("/ask")
def ask(
    body: AskRichiesta,
    utente: Utente = Depends(utente_corrente),
    interroga: Interroga = Depends(get_interroga),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    if body.mode == "admin":
        if not utente.is_admin:
            raise HTTPException(status_code=403, detail="modalità riservata all'ufficio (admin)")
        try:
            esito = interroga.esegui(body.question)
        except InterrogaError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        registra_query(dal, body.question, esito["sql"])  # contatore fingerprint (§3.6)
        return esito
    cantieri = [
        {"id": cid, "nome": nome_cantiere(dal, cid) or cid} for cid in utente.cantieri
    ]
    return {"risposta": interroga.rispondi_operatore(body.question, cantieri)}
