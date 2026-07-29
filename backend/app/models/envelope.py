"""Envelope standard per le entità in data/entities (contratto §3.1 del piano)."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ``scartato``: l'ufficio ha ripudiato l'inserimento. L'entità non viene
# cancellata — esce dai conti spostandosi in ``data/scartati/`` (fuori dal glob
# delle viste) e resta ripristinabile. Vedi DAL.scarta / DAL.ripristina.
Stato = Literal["bozza", "validato", "errore", "scartato"]


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
    # Scarto (stato ``scartato``): chi, quando e soprattutto *perché*. Il motivo è
    # obbligatorio lato API: uno scarto senza spiegazione è indistinguibile da un
    # errore di manovra quando lo si ritrova sei mesi dopo.
    scartato_da: str | None = None
    scartato_il: str | None = None
    motivo_scarto: str | None = None
    # Integrazione ERP (ciclo passivo): backref al documento contabile a valle e
    # timestamp della sincronizzazione. Valorizzati solo dopo un push riuscito
    # verso ERPNext (Meta è extra="forbid": vanno dichiarati qui, non ad-hoc).
    erp_id: str | None = None
    erp_synced: str | None = None


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    tipo: str
    schema_version: str = "1.0"
    stato: Stato = "bozza"
    dati: dict[str, Any]
    meta: Meta = Field(default_factory=Meta)
