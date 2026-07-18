"""Golden set: run validati, usati come regressione (glossario §2, ciclo §3.5).

Un caso golden è un input (blob originale) accanto all'output già validato
dall'ufficio. Quando l'Improver propone una nuova versione di un workflow,
la riesegue su questi casi e confronta l'output con l'atteso (LLM-as-judge):
se anche un solo caso non regge, la patch non va promossa. È la rete che
impedisce di "correggere un errore introducendone tre" (§3.5).

Qui vivono solo le letture; i casi si scrivono via ``DAL.crea_golden`` perché
ogni scrittura in ``data/`` è un commit (contratto §3.1).
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class CasoGolden(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    workflow: str
    version: str
    doc: str  # blob di input, percorso relativo al repo dati
    entity_tipo: str
    atteso: dict[str, Any]  # trascrizione corretta (output validato)
    run_id: str | None = None
    entity_id: str | None = None
    validato_da: str | None = None
    creato: str | None = None


def cartella_golden(data_dir: Path | str) -> Path:
    return Path(data_dir) / "golden"


def carica_golden(data_dir: Path | str, workflow: str | None = None) -> list[CasoGolden]:
    """Tutti i casi golden (opzionalmente di un solo workflow), ordinati per id."""
    casi = []
    for percorso in sorted(cartella_golden(data_dir).glob("GOLD-*.json")):
        caso = CasoGolden.model_validate_json(percorso.read_text(encoding="utf-8"))
        if workflow is None or caso.workflow == workflow:
            casi.append(caso)
    return casi
