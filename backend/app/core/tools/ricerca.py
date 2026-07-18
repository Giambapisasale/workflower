"""Tool ``cerca_fornitore`` / ``cerca_cantiere``: match fuzzy sulle anagrafiche.

Punteggio: rapporto di similarità (difflib) sul campo migliore, con boost se
una stringa contiene l'altra — "Scuola Manzoni" deve trovare "Ristrutturazione
Scuola Manzoni" anche se il rapporto puro è basso.
"""

from difflib import SequenceMatcher
from typing import Any

from app.core.dal import DAL

RISULTATI_MAX = 3
PUNTEGGIO_CONTENIMENTO = 0.9
LUNGHEZZA_MINIMA_CONTENIMENTO = 4

SCHEMA_FORNITORE = {
    "type": "function",
    "function": {
        "name": "cerca_fornitore",
        "description": (
            "Cerca un fornitore in anagrafica per ragione sociale o partita IVA "
            "(match approssimato). Restituisce i candidati migliori con punteggio."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Ragione sociale o partita IVA letta sul documento",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

SCHEMA_CANTIERE = {
    "type": "function",
    "function": {
        "name": "cerca_cantiere",
        "description": (
            "Cerca un cantiere in anagrafica per nome, indirizzo o comune "
            "(match approssimato). Restituisce i candidati migliori con punteggio."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Nome del cantiere / commessa / destinazione sul documento",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


def _punteggio(query: str, testo: str) -> float:
    a, b = query.lower().strip(), testo.lower().strip()
    if not a or not b:
        return 0.0
    rapporto = SequenceMatcher(None, a, b).ratio()
    lunghi = min(len(a), len(b)) >= LUNGHEZZA_MINIMA_CONTENIMENTO
    if lunghi and (a in b or b in a):
        rapporto = max(rapporto, PUNTEGGIO_CONTENIMENTO)
    return round(rapporto, 3)


def _cerca(dal: DAL, tipo: str, query: str, campi: list[str], riassunto: list[str]) -> dict:
    candidati: list[dict[str, Any]] = []
    for envelope in dal.list_all(tipo):
        migliore = max(
            _punteggio(query, str(envelope.dati.get(campo) or "")) for campo in campi
        )
        voce = {"id": envelope.id, "punteggio": migliore}
        voce.update({campo: envelope.dati.get(campo) for campo in riassunto})
        candidati.append(voce)
    candidati.sort(key=lambda v: v["punteggio"], reverse=True)
    return {"risultati": candidati[:RISULTATI_MAX]}


def cerca_fornitore(dal: DAL, query: str) -> dict:
    return _cerca(
        dal,
        "fornitore",
        query,
        campi=["ragione_sociale", "partita_iva"],
        riassunto=["ragione_sociale", "partita_iva", "comune"],
    )


def cerca_cantiere(dal: DAL, query: str) -> dict:
    return _cerca(
        dal,
        "cantiere",
        query,
        campi=["nome", "indirizzo", "comune", "committente"],
        riassunto=["nome", "comune", "committente"],
    )
