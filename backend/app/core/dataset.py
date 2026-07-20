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
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.core.dal import DAL, TIPI_INGRESSO
from app.models.envelope import now_iso

FILE_QUERY = "queries.jsonl"
FILE_TOOLCALLS = "toolcalls.jsonl"
# Delta fra la bozza estratta e il dato validato dall'ufficio (§3.6 / M16): la
# base minabile da cui il Toolsmith individua i calcoli/normalizzazioni ricorrenti.
FILE_DERIVAZIONI = "derivazioni.jsonl"


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


def _righe_toolcalls(data_dir: Path | str) -> Iterator[dict[str, Any]]:
    percorso = Path(data_dir) / "dataset" / FILE_TOOLCALLS
    if not percorso.is_file():
        return
    for riga in percorso.read_text(encoding="utf-8").splitlines():
        if not riga.strip():
            continue
        try:
            yield json.loads(riga)
        except json.JSONDecodeError:
            continue


def conteggio_tool(data_dir: Path | str) -> dict[str, int]:
    """Quante volte è stato invocato ogni tool (dai log delle tool call)."""
    conteggi: Counter[str] = Counter()
    for record in _righe_toolcalls(data_dir):
        nome = (record.get("tool_call") or {}).get("name")
        if nome:
            conteggi[nome] += 1
    return dict(conteggi)


def run_id_validati(dal: DAL) -> set[str]:
    """I run che hanno prodotto un'entità poi validata dall'ufficio (§3.7)."""
    validi: set[str] = set()
    for tipo in TIPI_INGRESSO:
        for envelope in dal.list_all(tipo):
            if envelope.stato == "validato" and envelope.meta.run_id:
                validi.add(envelope.meta.run_id)
    return validi


def esempi_finetuning(dal: DAL) -> Iterator[dict[str, Any]]:
    """Le tool call dei run validati, riformattate come esempi per il fine-tuning.

    ADR-5 (log-everything): solo i run la cui bozza è stata validata da un umano
    diventano esempi (``validated_by_user``), per non insegnare al modello gli errori.
    """
    validi = run_id_validati(dal)
    for record in _righe_toolcalls(dal.data_dir):
        if record.get("outcome") != "success" or record.get("run_id") not in validi:
            continue
        yield {
            "workflow": record.get("workflow"),
            "tools": record.get("tools"),
            "messages": record.get("messages"),
            "tool_call": record.get("tool_call"),
        }


def estratto_del_run(data_dir: Path | str, run_id: str, tipo: str) -> dict[str, Any] | None:
    """La bozza che il run aveva estratto: gli argomenti di ``salva_bozza`` dal trace.

    È il "prima" del delta estratto→validato: il dato grezzo prodotto dal modello,
    da confrontare con ciò che l'ufficio ha poi validato. ``None`` se il run non ha
    salvato una bozza di quel tipo (es. entità del seed, senza trace).
    """
    for record in _righe_toolcalls(data_dir):
        if record.get("run_id") != run_id:
            continue
        chiamata = record.get("tool_call") or {}
        if chiamata.get("name") != "salva_bozza":
            continue
        args = chiamata.get("args") or {}
        if args.get("tipo") == tipo and isinstance(args.get("dati"), dict):
            return args["dati"]
    return None


def registra_derivazione(
    dal: DAL,
    *,
    run_id: str,
    workflow: str | None,
    tipo: str,
    entity_id: str,
    estratto: dict[str, Any] | None,
    validato: dict[str, Any],
    validato_da: str | None,
) -> None:
    """Marca nel dataset il delta estratto→validato di un'entità validata (M16).

    Instrumentazione minima, **fuori da runtime.py**: la chiama la revisione al
    momento della validazione. Registra la coppia grezzo→validato (con i campi
    che l'ufficio ha corretto) come materia prima per il Toolsmith, che da queste
    coppie storiche mina i calcoli deterministici ricorrenti e ne ricava i test.
    """
    percorso = dal.data_dir / "dataset" / FILE_DERIVAZIONI
    percorso.parent.mkdir(parents=True, exist_ok=True)
    corretti = (
        sorted(k for k in validato if (estratto or {}).get(k) != validato.get(k))
        if estratto is not None
        else []
    )
    record = {
        "ts": now_iso(),
        "run_id": run_id,
        "workflow": workflow,
        "tipo": tipo,
        "entity_id": entity_id,
        "estratto": estratto,
        "validato": validato,
        "corretti": corretti,
        "validato_da": validato_da,
    }
    with percorso.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    dal.commit_paths([percorso], f"dataset: derivazione {entity_id} [{run_id}]")


def leggi_derivazioni(data_dir: Path | str) -> list[dict[str, Any]]:
    """Le coppie estratto→validato registrate (base minabile del Toolsmith)."""
    percorso = Path(data_dir) / "dataset" / FILE_DERIVAZIONI
    if not percorso.is_file():
        return []
    voci: list[dict[str, Any]] = []
    for riga in percorso.read_text(encoding="utf-8").splitlines():
        if not riga.strip():
            continue
        try:
            voci.append(json.loads(riga))
        except json.JSONDecodeError:
            continue
    return voci


def statistiche(data_dir: Path | str) -> dict[str, Any]:
    """Aggregati dai trace: run, tool call, costo LLM, costo per documento."""
    base = Path(data_dir)
    n_run = n_ok = n_errore = n_llm = n_tool = 0
    costo = 0.0
    per_workflow: Counter[str] = Counter()
    escalation_wf: Counter[str] = Counter()
    for trace in (base / "traces").glob("*/*/*.jsonl"):
        avviato = False
        outcome = workflow = None
        escalato = False
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
                case "escalation":
                    escalato = True
        if not avviato:
            continue
        n_run += 1
        per_workflow[workflow or "?"] += 1
        if escalato:
            escalation_wf[workflow or "?"] += 1
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
        "escalation": {
            "totale": sum(escalation_wf.values()),
            "per_workflow": {
                wf: {
                    "run": per_workflow[wf],
                    "escalation": escalation_wf[wf],
                    "percentuale": round(100 * escalation_wf[wf] / per_workflow[wf], 1)
                    if per_workflow[wf]
                    else 0.0,
                }
                for wf in escalation_wf
            },
        },
    }


def _conta_righe(percorso: Path) -> int:
    if not percorso.is_file():
        return 0
    return sum(1 for riga in percorso.read_text(encoding="utf-8").splitlines() if riga.strip())
