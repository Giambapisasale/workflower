"""Golden set: run validati, usati come regressione (glossario §2, ciclo §3.5).

Un caso golden è un input accanto all'output già validato dall'ufficio. Quando
l'Improver propone una nuova versione di un workflow, la riesegue su questi casi
e confronta l'output con l'atteso (LLM-as-judge): se anche un solo caso non
regge, la patch non va promossa. È la rete che impedisce di "correggere un
errore introducendone tre" (§3.5).

Ci sono **due forme** di caso, perché il prodotto ha due compiti da misurare:

- **documento** — l'input è un blob (``doc``) e l'atteso è la trascrizione
  validata dell'entità. È la forma storica.
- **domanda** — l'input è una domanda in italiano (``domanda``) e l'atteso è la
  **query di riferimento** approvata dall'ufficio (``atteso["sql"]``), non le
  righe che restituisce. Le righe cambiano appena arriva una fattura in più: il
  confronto si fa eseguendo *adesso* la query di riferimento e quella del
  candidato sugli stessi dati (vedi :mod:`app.core.eval_interroga`). Due SQL
  diversi possono essere entrambi giusti — quello che deve coincidere è la
  risposta, non il testo.

Qui vivono solo le letture; i casi si scrivono via ``DAL.crea_golden`` /
``DAL.crea_golden_domanda`` perché ogni scrittura in ``data/`` è un commit (§3.1).
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

# Il workflow dei casi-domanda: è quello di ``/ask`` (data/workflows/interroga).
WORKFLOW_DOMANDA = "interroga"


class CasoGolden(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    workflow: str
    version: str
    # Caso "documento": il blob di input e il tipo di entità attesa.
    doc: str | None = None  # percorso relativo al repo dati
    entity_tipo: str | None = None
    # Caso "domanda": il testo posto a ``/ask``.
    domanda: str | None = None
    atteso: dict[str, Any]  # documento: i dati validati — domanda: ``{"sql": …}``
    run_id: str | None = None
    entity_id: str | None = None
    validato_da: str | None = None
    creato: str | None = None

    @property
    def tipo(self) -> str:
        """``legacy_sql`` o ``documento``: i casi legacy non guidano il runtime."""
        return "legacy_sql" if self.domanda else "documento"

    @property
    def sql_riferimento(self) -> str | None:
        """La query approvata dall'ufficio, per i soli casi-domanda."""
        return self.atteso.get("sql") if self.tipo == "legacy_sql" else None


def cartella_golden(data_dir: Path | str) -> Path:
    return Path(data_dir) / "golden"


def carica_golden(
    data_dir: Path | str, workflow: str | None = None, *, tipo: str | None = None
) -> list[CasoGolden]:
    """I casi golden, opzionalmente di un solo workflow e/o di una sola forma.

    Il filtro ``tipo`` serve a chi sa trattarne una sola: l'Improver rigioca
    documenti attraverso il runtime e su un caso-domanda non saprebbe cosa fare.
    """
    casi = []
    for percorso in sorted(cartella_golden(data_dir).glob("GOLD-*.json")):
        caso = CasoGolden.model_validate_json(percorso.read_text(encoding="utf-8"))
        if workflow is not None and caso.workflow != workflow:
            continue
        if tipo is not None and caso.tipo != tipo:
            continue
        casi.append(caso)
    return casi


def casi_domanda(data_dir: Path | str) -> list[CasoGolden]:
    """Archivio storico, non usato per decidere l'agente in produzione."""
    return carica_golden(data_dir, tipo="legacy_sql")
