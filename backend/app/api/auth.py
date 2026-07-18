"""Login (piano §3.4): ``POST /auth/login`` → JWT con ruolo e cantieri."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_dal, get_data_dir
from app.core.auth import AuthError, Utente, crea_token, verifica_credenziali
from app.core.dal import DAL, DalError

router = APIRouter(tags=["auth"])


class LoginRichiesta(BaseModel):
    username: str
    pin: str


def cantieri_di(dal: DAL, utente: Utente) -> list[dict[str, str]]:
    """I cantieri dell'utente come ``{id, nome}`` (tutti, per gli admin)."""
    if utente.is_admin:
        return [
            {"id": c.id, "nome": str(c.dati.get("nome", c.id))}
            for c in dal.list_all("cantiere")
        ]
    cantieri = []
    for cantiere_id in utente.cantieri:
        try:
            envelope = dal.read("cantiere", cantiere_id)
            nome = str(envelope.dati.get("nome", cantiere_id))
        except DalError:
            nome = cantiere_id
        cantieri.append({"id": cantiere_id, "nome": nome})
    return cantieri


@router.post("/auth/login")
def login(
    body: LoginRichiesta,
    data_dir: Path = Depends(get_data_dir),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    try:
        utente = verifica_credenziali(data_dir, body.username.strip().lower(), body.pin.strip())
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="nome utente o codice non validi") from exc
    return {
        "token": crea_token(utente),
        "utente": {
            "username": utente.username,
            "nome": utente.nome,
            "ruolo": utente.ruolo,
            "cantieri": cantieri_di(dal, utente),
        },
    }
