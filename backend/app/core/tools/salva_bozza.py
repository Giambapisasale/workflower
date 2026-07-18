"""Tool ``salva_bozza``: crea l'envelope dell'entità estratta, via DAL.

Lo invoca il runtime nello step ``salva`` (action ``save_draft``): non è
esposto al modello, che non deve poter scrivere direttamente (ADR-4).
"""

from datetime import UTC, datetime
from typing import Any

from app.core.dal import DAL, ENTITY_TYPES, AlreadyExistsError
from app.core.tools.base import ToolError
from app.models.envelope import Envelope, Meta

TENTATIVI_ID = 5

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


def _anno(tipo: str, dati: dict[str, Any]) -> int | None:
    if not ENTITY_TYPES.get(tipo, {}).get("per_anno"):
        return None
    data = str(dati.get("data") or "")
    if len(data) >= 4 and data[:4].isdigit():
        return int(data[:4])
    return datetime.now(UTC).year


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
    anno = _anno(tipo, dati)
    ultimo: Exception | None = None
    for _ in range(TENTATIVI_ID):
        entity_id = dal.prossimo_id(tipo, anno)
        envelope = Envelope(
            id=entity_id,
            tipo=tipo,
            stato=stato,  # type: ignore[arg-type]
            dati=dati,
            meta=Meta(origine=origine, workflow=workflow, run_id=run_id, confidence=confidence),
        )
        try:
            dal.create(envelope, run_id=run_id)
            return {"id": entity_id, "stato": stato}
        except AlreadyExistsError as exc:
            # id assegnato da un run concorrente tra prossimo_id e create: si riprova
            ultimo = exc
    raise ToolError(f"nessun id libero dopo {TENTATIVI_ID} tentativi: {ultimo}")
