"""Valutatore delle regole di validazione dei manifest (piano §3.2 e §7).

Niente eval libero: mini-parser sull'AST Python che ammette solo ciò che
serve alle regole — costanti, aritmetica, confronti, ``dati.campo`` e le
funzioni in whitelist (``abs``, ``today``). Nessun accesso ai builtins.
"""

import ast
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel


class RegolaNonValutabile(Exception):
    """Espressione fuori dal sottoinsieme ammesso, o non valutabile sui dati."""


def _today() -> str:
    """Data odierna ISO: confrontabile come stringa con i campi data."""
    return datetime.now(UTC).date().isoformat()


_FUNZIONI: dict[str, Any] = {"abs": abs, "today": _today}

_OPERATORI_BINARI = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}

_CONFRONTI = {
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
}


class EsitoRegola(BaseModel):
    regola: str
    ok: bool
    errore: str | None = None  # valorizzato se la regola non era valutabile


def valuta_regola(espressione: str, dati: dict[str, Any]) -> bool:
    """Valuta una regola sul dizionario ``dati``. Solleva RegolaNonValutabile."""
    try:
        albero = ast.parse(espressione, mode="eval")
    except SyntaxError as exc:
        raise RegolaNonValutabile(f"sintassi non valida: {espressione!r}") from exc
    try:
        return bool(_valuta(albero.body, {"dati": dati}))
    except RegolaNonValutabile:
        raise
    except Exception as exc:  # es. confronto con None per campo mancante
        raise RegolaNonValutabile(f"non valutabile sui dati: {exc}") from exc


def valuta_regole(regole: list[str], dati: dict[str, Any]) -> list[EsitoRegola]:
    """Valuta tutte le regole; una regola non valutabile conta come fallita."""
    esiti = []
    for regola in regole:
        try:
            esiti.append(EsitoRegola(regola=regola, ok=valuta_regola(regola, dati)))
        except RegolaNonValutabile as exc:
            esiti.append(EsitoRegola(regola=regola, ok=False, errore=str(exc)))
    return esiti


def _valuta(nodo: ast.expr, nomi: dict[str, Any]) -> Any:
    match nodo:
        case ast.Constant(value=valore) if isinstance(valore, bool | int | float | str):
            return valore
        case ast.Name(id=nome):
            if nome in nomi:
                return nomi[nome]
            raise RegolaNonValutabile(f"nome non ammesso: {nome}")
        case ast.Attribute(value=base, attr=attributo):
            contenitore = _valuta(base, nomi)
            if isinstance(contenitore, dict):
                return contenitore.get(attributo)
            raise RegolaNonValutabile(f"attributo su un non-oggetto: {attributo}")
        case ast.Call(func=ast.Name(id=nome), args=argomenti, keywords=[]):
            if nome not in _FUNZIONI:
                raise RegolaNonValutabile(f"funzione non ammessa: {nome}")
            return _FUNZIONI[nome](*(_valuta(a, nomi) for a in argomenti))
        case ast.UnaryOp(op=ast.USub(), operand=operando):
            return -_valuta(operando, nomi)
        case ast.UnaryOp(op=ast.Not(), operand=operando):
            return not _valuta(operando, nomi)
        case ast.BinOp(left=sinistra, op=op, right=destra) if type(op) in _OPERATORI_BINARI:
            return _OPERATORI_BINARI[type(op)](_valuta(sinistra, nomi), _valuta(destra, nomi))
        case ast.Compare(left=sinistra, ops=ops, comparators=confrontati):
            corrente = _valuta(sinistra, nomi)
            for op, destra_nodo in zip(ops, confrontati, strict=True):
                if type(op) not in _CONFRONTI:
                    raise RegolaNonValutabile(f"confronto non ammesso: {type(op).__name__}")
                destra = _valuta(destra_nodo, nomi)
                if not _CONFRONTI[type(op)](corrente, destra):
                    return False
                corrente = destra
            return True
        case ast.BoolOp(op=op, values=valori):
            risultati = (_valuta(v, nomi) for v in valori)
            return all(risultati) if isinstance(op, ast.And) else any(risultati)
        case _:
            raise RegolaNonValutabile(f"costrutto non ammesso: {type(nodo).__name__}")
