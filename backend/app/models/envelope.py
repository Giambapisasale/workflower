"""Envelope standard per le entità in data/entities (contratto §3.1 del piano)."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Stato = Literal["bozza", "validato", "errore"]


def now_iso() -> str:
    """Timestamp ISO 8601 UTC al secondo (leggibile nei diff git)."""
    return datetime.now(UTC).isoformat(timespec="seconds")


class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origine: str | None = None
    workflow: str | None = None
    run_id: str | None = None
    confidence: dict[str, float] | None = None
    created: str | None = None
    updated: str | None = None
    validato_da: str | None = None


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    tipo: str
    schema_version: str = "1.0"
    stato: Stato = "bozza"
    dati: dict[str, Any]
    meta: Meta = Field(default_factory=Meta)
