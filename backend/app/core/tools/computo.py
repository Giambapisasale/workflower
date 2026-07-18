"""Tool ``cerca_voce_computo`` + abbinamento righe→voci (Fase 2, M9).

Il collegamento di una riga di fattura/DDT alla voce di computo è un'operazione
ricorrente e ben definita: la consolidiamo in un tool deterministico (fuzzy match
sulla descrizione), come previsto da §3.6 (skill → tool). Nessun LLM: latenza e
costo costanti, esito riproducibile. Il tool resta a disposizione dei workflow.
"""

from difflib import SequenceMatcher
from typing import Any

from app.core.dal import DAL

RISULTATI_MAX = 3
PUNTEGGIO_CONTENIMENTO = 0.9
LUNGHEZZA_MINIMA_CONTENIMENTO = 4

SCHEMA = {
    "type": "function",
    "function": {
        "name": "cerca_voce_computo",
        "description": (
            "Cerca nel computo di un cantiere la voce che meglio corrisponde alla "
            "descrizione di una riga di fattura o DDT. Restituisce i candidati con punteggio."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cantiere_id": {
                    "type": "string",
                    "description": "Cantiere di riferimento, es. CNT-001",
                },
                "query": {"type": "string", "description": "Descrizione della riga da abbinare"},
            },
            "required": ["cantiere_id", "query"],
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


def voci_cantiere(dal: DAL, cantiere_id: str | None) -> list[dict[str, Any]]:
    """Le voci del computo del cantiere (una sola entità computo per cantiere)."""
    if not cantiere_id:
        return []
    for computo in dal.list_all("computo"):
        if computo.dati.get("cantiere_id") == cantiere_id:
            return list(computo.dati.get("voci") or [])
    return []


def cerca_voce_computo(dal: DAL, cantiere_id: str, query: str) -> dict[str, Any]:
    candidati = [
        {
            "voce_id": voce.get("id"),
            "codice": voce.get("codice"),
            "descrizione": voce.get("descrizione"),
            "categoria": voce.get("categoria"),
            "punteggio": _punteggio(query, str(voce.get("descrizione") or "")),
        }
        for voce in voci_cantiere(dal, cantiere_id)
    ]
    candidati.sort(key=lambda v: v["punteggio"], reverse=True)
    return {"risultati": candidati[:RISULTATI_MAX]}
