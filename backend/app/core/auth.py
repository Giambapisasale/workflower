"""Autenticazione: utenti su file, PIN con PBKDF2, sessioni JWT (piano §3.4).

RBAC minimale (``operatore`` | ``admin``) con i cantieri dell'utente nel
token; il mapping verso SSO Entra ID è un'evoluzione prevista, non v1.
Gli utenti vivono in ``data/config/utenti.json`` (la fonte di verità è il
repo dati), creati dal seed con PIN dimostrativi.
"""

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import jwt
from pydantic import BaseModel, ConfigDict

ALGORITMO = "HS256"
DURATA_TOKEN = timedelta(hours=12)
ITERAZIONI_PBKDF2 = 60_000


class AuthError(Exception):
    """Credenziali o token non validi."""


class Utente(BaseModel):
    model_config = ConfigDict(extra="ignore")

    username: str
    nome: str
    ruolo: Literal["operatore", "admin"]
    cantieri: list[str] = []  # id dei cantieri assegnati (vuoto per gli admin)

    @property
    def is_admin(self) -> bool:
        return self.ruolo == "admin"


def _secret() -> str:
    # il default è solo per lo sviluppo; ≥32 byte per l'HMAC-SHA256
    return os.environ.get("JWT_SECRET", "workflower-dev-secret-non-usare-in-produzione")


def hash_pin(username: str, pin: str) -> str:
    """PBKDF2-SHA256 con salt derivato dall'username (PoC: PIN dimostrativi)."""
    salt = f"workflower:{username}".encode()
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, ITERAZIONI_PBKDF2).hex()


def carica_utenti(data_dir: Path | str) -> list[dict[str, Any]]:
    percorso = Path(data_dir) / "config" / "utenti.json"
    if not percorso.is_file():
        return []
    return json.loads(percorso.read_text(encoding="utf-8"))


def verifica_credenziali(data_dir: Path | str, username: str, pin: str) -> Utente:
    """Ritorna l'utente se username+PIN combaciano, altrimenti ``AuthError``."""
    for record in carica_utenti(data_dir):
        if record.get("username") == username:
            atteso = record.get("pin_pbkdf2", "")
            if atteso and hmac.compare_digest(atteso, hash_pin(username, pin)):
                return Utente.model_validate(record)
            break
    raise AuthError("nome utente o codice non validi")


def crea_token(utente: Utente) -> str:
    scadenza = datetime.now(UTC) + DURATA_TOKEN
    payload = {
        "sub": utente.username,
        "nome": utente.nome,
        "ruolo": utente.ruolo,
        "cantieri": utente.cantieri,
        "exp": scadenza,
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITMO)


def decodifica_token(token: str) -> Utente:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITMO])
    except jwt.PyJWTError as exc:
        raise AuthError(f"token non valido: {exc}") from exc
    return Utente(
        username=payload["sub"],
        nome=payload.get("nome", payload["sub"]),
        ruolo=payload.get("ruolo", "operatore"),
        cantieri=list(payload.get("cantieri") or []),
    )
