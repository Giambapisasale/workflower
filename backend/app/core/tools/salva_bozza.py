"""Tool ``salva_bozza``: crea l'envelope dell'entità estratta, via DAL.

Lo invoca il runtime nello step ``salva`` (action ``save_draft``): non è
esposto al modello, che non deve poter scrivere direttamente (ADR-4).
"""

from typing import Any

from app.core.dal import DAL, DalError
from app.core.tools.base import ToolError
from app.models.envelope import Meta

SCHEMA = {
    "type": "function",
    "function": {
        "name": "salva_bozza",
        "description": "Salva l'entità estratta come bozza nel repo dati (id progressivo).",
        "parameters": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "description": "Tipo entità, es. fattura"},
                "dati": {"type": "object", "description": "Dati conformi allo schema del tipo"},
            },
            "required": ["tipo", "dati"],
            "additionalProperties": True,
        },
    },
}


def esegui(
    dal: DAL,
    tipo: str,
    dati: dict[str, Any],
    stato: str = "bozza",
    confidence: dict[str, float] | None = None,
    origine: str | None = None,
    workflow: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    meta = Meta(origine=origine, workflow=workflow, run_id=run_id, confidence=confidence)
    try:
        envelope = dal.crea_progressivo(tipo, dati, stato=stato, meta=meta, tag=run_id)
    except DalError as exc:
        raise ToolError(str(exc)) from exc
    return {"id": envelope.id, "stato": envelope.stato}
