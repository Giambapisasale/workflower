"""Segnalazioni in ``data/issues/`` (aperte dagli operatori o dal runtime)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.envelope import now_iso


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    origine: Literal["auto", "operatore"]
    testo: str
    run_id: str | None = None
    doc: str | None = None  # percorso del blob interessato
    entity_id: str | None = None
    stato: Literal["aperta", "chiusa"] = "aperta"
    created: str = Field(default_factory=now_iso)
