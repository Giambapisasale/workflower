"""Log & Dataset (piano §M6): conteggi, costo per documento, fingerprint query.

Materia prima per l'osservabilità e per il futuro fine-tuning (§3.7). Le tool
call dei run sono già in ``dataset/toolcalls.jsonl``; qui si aggregano i trace
(costi, conteggi) e si tiene un contatore delle query generate da ``/ask``
raggruppate per *fingerprint* — solo conteggio dei duplicati simili, nessun
Toolsmith automatico in v1 (non-goal §5).
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.core.dal import DAL
from app.models.envelope import now_iso

FILE_QUERY = "queries.jsonl"


def fingerprint(sql: str) -> str:
    """Normalizza una query per riconoscere quelle "strutturalmente uguali".

    Minuscolo, spazi compattati, letterali stringa e numeri sostituiti da ``?``:
    due query che differiscono solo per i valori hanno lo stesso fingerprint.
    """
    testo = sql.strip().lower()
    testo = re.sub(r"'[^']*'", "?", testo)
    testo = re.sub(r"\b\d+(\.\d+)?\b", "?", testo)
    return re.sub(r"\s+", " ", testo).strip()


def registra_query(dal: DAL, domanda: str, sql: str) -> None:
    """Appende la query generata al log del dataset e committa (mutazione = commit)."""
    percorso = dal.data_dir / "dataset" / FILE_QUERY
    percorso.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": now_iso(),
        "domanda": domanda,
        "sql": sql,
        "fingerprint": fingerprint(sql),
    }
    with percorso.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
    dal.commit_paths([percorso], "dataset: registra query di interroga [ask]")


def conteggio_fingerprint(data_dir: Path | str) -> list[dict[str, Any]]:
    """Le query generate raggruppate per fingerprint (candidati al consolidamento)."""
    percorso = Path(data_dir) / "dataset" / FILE_QUERY
    if not percorso.is_file():
        return []
    conteggi: Counter[str] = Counter()
    esempio: dict[str, str] = {}
    for riga in percorso.read_text(encoding="utf-8").splitlines():
        if not riga.strip():
            continue
        try:
            record = json.loads(riga)
        except json.JSONDecodeError:
            continue
        fp = record.get("fingerprint", "")
        conteggi[fp] += 1
        esempio.setdefault(fp, record.get("sql", ""))
    gruppi = [
        {"fingerprint": fp, "conteggio": n, "esempio": esempio.get(fp, "")}
        for fp, n in conteggi.most_common()
    ]
    return gruppi


def statistiche(data_dir: Path | str) -> dict[str, Any]:
    """Aggregati dai trace: run, tool call, costo LLM, costo per documento."""
    base = Path(data_dir)
    n_run = n_ok = n_errore = n_llm = n_tool = 0
    costo = 0.0
    per_workflow: Counter[str] = Counter()
    for trace in (base / "traces").glob("*/*/*.jsonl"):
        avviato = False
        outcome = workflow = None
        for riga in trace.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(riga)
            except json.JSONDecodeError:
                continue
            match ev.get("evento"):
                case "run_start":
                    avviato = True
                    workflow = ev.get("workflow")
                case "run_end":
                    outcome = ev.get("outcome")
                case "llm_call":
                    n_llm += 1
                    costo += float(ev.get("cost_usd") or 0)
                case "tool_call":
                    n_tool += 1
        if not avviato:
            continue
        n_run += 1
        per_workflow[workflow or "?"] += 1
        if outcome == "ok":
            n_ok += 1
        elif outcome == "errore":
            n_errore += 1

    # i documenti sono partizionati per anno (entities/documenti/AAAA/DOC-…): rglob
    n_documenti = len(list((base / "entities" / "documenti").rglob("DOC-*.json")))
    n_toolcalls = _conta_righe(base / "dataset" / "toolcalls.jsonl")
    return {
        "run": {"totale": n_run, "ok": n_ok, "errore": n_errore},
        "llm_call": n_llm,
        "tool_call": n_tool,
        "toolcalls_dataset": n_toolcalls,
        "costo_totale_usd": round(costo, 6),
        "documenti": n_documenti,
        "costo_per_documento_usd": round(costo / n_documenti, 6) if n_documenti else 0.0,
        "run_per_workflow": dict(per_workflow),
    }


def _conta_righe(percorso: Path) -> int:
    if not percorso.is_file():
        return 0
    return sum(1 for riga in percorso.read_text(encoding="utf-8").splitlines() if riga.strip())
