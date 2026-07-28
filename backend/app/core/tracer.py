"""Trace JSONL per run (contratto §3.3) + log tool call nel dataset (§3.7).

Un tracer per run: appende eventi a ``data/traces/AAAA/MM/<run_id>.jsonl``
e duplica ogni tool call in ``data/dataset/toolcalls.jsonl`` con il contesto
completo (materia prima per Improver e fine-tuning: non risparmiare campi).
I file si accumulano durante il run; il commit git è unico, a fine run.
"""

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Oltre questa soglia una stringa nei log diventa un segnaposto con digest:
# tiene fuori dai trace i base64 delle immagini, senza perderne l'identità.
MAX_STRINGA_LOG = 400


def _adesso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def sanitizza(valore: Any, limite: int = MAX_STRINGA_LOG) -> Any:
    """Copia del valore con le stringhe lunghe sostituite da segnaposto."""
    if isinstance(valore, str) and len(valore) > limite:
        digest = hashlib.sha256(valore.encode("utf-8")).hexdigest()[:12]
        return f"<{len(valore)} caratteri, sha256:{digest}>"
    if isinstance(valore, dict):
        return {chiave: sanitizza(v, limite) for chiave, v in valore.items()}
    if isinstance(valore, list):
        return [sanitizza(v, limite) for v in valore]
    return valore


def digest_messaggi(messages: list[dict[str, Any]]) -> str:
    serializzati = json.dumps(messages, ensure_ascii=False, default=str)
    return hashlib.sha256(serializzati.encode("utf-8")).hexdigest()[:16]


def trova_trace(data_dir: Path | str, run_id: str) -> Path | None:
    """Percorso del trace di un run, in qualunque mese sia stato scritto."""
    for percorso in (Path(data_dir) / "traces").glob(f"*/*/{run_id}.jsonl"):
        return percorso
    return None


def _appendi_riga(percorso: Path, record: dict[str, Any]) -> None:
    with percorso.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def appendi_feedback_operatore(
    data_dir: Path | str, run_id: str, tipo: str, utente: str, **campi: Any
) -> Path | None:
    """Nota post-run sul trace (conferma o segnalazione dell'operatore).

    Il feedback è materia prima dell'Improver (§3.5): vive accanto agli
    eventi del run. Ritorna il percorso del trace, o ``None`` se non esiste.
    """
    percorso = trova_trace(data_dir, run_id)
    if percorso is None:
        return None
    _appendi_riga(
        percorso,
        {
            "ts": _adesso(),
            "run_id": run_id,
            "evento": "operator_feedback",
            "tipo": tipo,
            "utente": utente,
            **sanitizza(campi),
        },
    )
    return percorso


def appendi_feedback_campo(
    data_dir: Path | str, run_id: str, campo: str, nota: str, utente: str
) -> Path | None:
    """Feedback puntuale dell'admin su un campo estratto (revisione, §3.4)."""
    percorso = trova_trace(data_dir, run_id)
    if percorso is None:
        return None
    _appendi_riga(
        percorso,
        {
            "ts": _adesso(),
            "run_id": run_id,
            "evento": "field_feedback",
            "campo": campo,
            "nota": sanitizza(nota),
            "utente": utente,
        },
    )
    return percorso


def leggi_eventi(
    data_dir: Path | str, run_id: str, tipi: set[str] | None = None
) -> list[dict[str, Any]]:
    """Eventi del trace di un run, in ordine, opzionalmente filtrati per tipo."""
    percorso = trova_trace(data_dir, run_id)
    if percorso is None:
        return []
    eventi = []
    for riga in percorso.read_text(encoding="utf-8").splitlines():
        if not riga.strip():
            continue
        try:
            record = json.loads(riga)
        except json.JSONDecodeError:
            continue
        if tipi is None or record.get("evento") in tipi:
            eventi.append(record)
    return eventi


def _eventi_di(percorso: Path) -> list[dict[str, Any]]:
    """Gli eventi di un file di trace, righe corrotte ignorate."""
    eventi = []
    for riga in percorso.read_text(encoding="utf-8").splitlines():
        if not riga.strip():
            continue
        try:
            eventi.append(json.loads(riga))
        except json.JSONDecodeError:
            continue
    return eventi


def _riassunto(percorso: Path) -> dict[str, Any] | None:
    """Un run in una riga: cosa ha elaborato, com'è finito, quanto è costato.

    ``None`` se il file non contiene un ``run_start``: senza quello non è un run
    ma un frammento, e in elenco confonderebbe più di quanto informi.
    """
    eventi = _eventi_di(percorso)
    inizio = next((e for e in eventi if e.get("evento") == "run_start"), None)
    if inizio is None:
        return None
    fine = next((e for e in eventi if e.get("evento") == "run_end"), None)
    chiamate = [e for e in eventi if e.get("evento") == "llm_call"]
    return {
        "run_id": percorso.stem,
        "workflow": inizio.get("workflow"),
        "version": inizio.get("version"),
        "input": inizio.get("input"),
        "ts": inizio.get("ts"),
        "esito": (fine or {}).get("outcome") or "in_corso",
        "entity_id": (fine or {}).get("entity_id"),
        "errore": (fine or {}).get("errore"),
        "costo_usd": round(sum(float(e.get("cost_usd") or 0) for e in chiamate), 6),
        "tokens": sum(
            int(e.get("tokens_in") or 0) + int(e.get("tokens_out") or 0) for e in chiamate
        ),
        "durata_ms": sum(int(e.get("latency_ms") or 0) for e in chiamate),
        "n_llm": len(chiamate),
        "n_tool": sum(1 for e in eventi if e.get("evento") == "tool_call"),
        "escalation": sum(1 for e in eventi if e.get("evento") == "escalation"),
    }


def elenco_run(
    data_dir: Path | str,
    *,
    workflow: str | None = None,
    esito: str | None = None,
    limite: int = 100,
) -> list[dict[str, Any]]:
    """I run più recenti, riassunti per l'elenco admin (dal più nuovo).

    Scandisce i trace come :func:`statistiche_run`: la fonte di verità è sempre
    ``data/traces/``, non un indice da tenere in sincronia.
    """
    riassunti = []
    for percorso in (Path(data_dir) / "traces").glob("*/*/*.jsonl"):
        riga = _riassunto(percorso)
        if riga is None:
            continue
        if workflow and riga["workflow"] != workflow:
            continue
        if esito and riga["esito"] != esito:
            continue
        riassunti.append(riga)
    riassunti.sort(key=lambda r: r.get("ts") or "", reverse=True)
    return riassunti[: max(1, limite)]


def statistiche_run(data_dir: Path | str) -> dict[str, dict[str, int]]:
    """Conteggio run per workflow (totale, ok, errore) scandendo i trace."""
    stats: dict[str, dict[str, int]] = {}
    for percorso in (Path(data_dir) / "traces").glob("*/*/*.jsonl"):
        workflow, outcome = None, None
        for record in _eventi_di(percorso):
            if record.get("evento") == "run_start":
                workflow = record.get("workflow")
            elif record.get("evento") == "run_end":
                outcome = record.get("outcome")
        if not workflow:
            continue
        conteggi = stats.setdefault(workflow, {"totale": 0, "ok": 0, "errore": 0})
        conteggi["totale"] += 1
        if outcome in ("ok", "errore"):
            conteggi[outcome] += 1
    return stats


class Tracer:
    def __init__(self, data_dir: Path | str, run_id: str, workflow: str, version: str) -> None:
        self.data_dir = Path(data_dir)
        self.run_id = run_id
        self.workflow = workflow
        self.version = version
        adesso = datetime.now(UTC)
        cartella_mese = self.data_dir / "traces" / f"{adesso:%Y}" / f"{adesso:%m}"
        self.trace_path = cartella_mese / f"{run_id}.jsonl"
        self.dataset_path = self.data_dir / "dataset" / "toolcalls.jsonl"
        self._lock = threading.Lock()

    # ------------------------------------------------------------- eventi

    def evento(self, tipo: str, **campi: Any) -> None:
        record = {"ts": _adesso(), "run_id": self.run_id, "evento": tipo, **sanitizza(campi)}
        self._appendi(self.trace_path, record)

    def run_start(self, input_doc: str) -> None:
        self.evento("run_start", workflow=self.workflow, version=self.version, input=input_doc)

    def llm_call(
        self,
        step: str,
        tier: str,
        model: str,
        messages: list[dict[str, Any]],
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        latency_ms: int,
    ) -> None:
        self.evento(
            "llm_call",
            step=step,
            tier=tier,
            model=model,
            messages_digest=digest_messaggi(messages),
            n_messages=len(messages),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )

    def tool_call(
        self,
        step: str,
        name: str,
        args: dict[str, Any],
        result: Any,
        ok: bool,
        messages: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        self.evento("tool_call", step=step, name=name, args=args, result=result, ok=ok)
        riga_dataset = sanitizza(
            {
                "ts": _adesso(),
                "run_id": self.run_id,
                "workflow": f"{self.workflow}@{self.version}",
                "step": step,
                "tools": tools or [],
                "messages": messages or [],
                "tool_call": {"name": name, "args": args},
                "result": result,
                "outcome": "success" if ok else "error",
                "validated_by_user": None,  # riempito a posteriori dal dataset builder
            }
        )
        self._appendi(self.dataset_path, riga_dataset)

    def query(self, domanda: str, sql: str, righe: int, fingerprint: str) -> None:
        """Una domanda tradotta in SQL ed eseguita (``/ask``, workflow ``interroga``).

        Non è una ``tool_call``: il modello non *sceglie* un tool, scrive SQL. Per
        questo non finisce in ``toolcalls.jsonl``, che è il dataset delle decisioni
        di function calling e non va inquinato con chiamate mai avvenute.

        Attenzione: qui il SQL passa da :func:`sanitizza`, quindi oltre i 400
        caratteri resta solo l'impronta. La copia **integrale** vive in
        ``dataset/queries.jsonl`` (``dataset.registra_query``), che è la fonte per
        il consolidamento (§3.6) e per il dataset delle interrogazioni.
        """
        self.evento("query", domanda=domanda, sql=sql, righe=righe, fingerprint=fingerprint)

    def validation(self, step: str, esito: str, dettagli: Any = None) -> None:
        self.evento("validation", step=step, esito=esito, dettagli=dettagli)

    def escalation(self, step: str, da: str, a: str, motivo: str) -> None:
        """Uno step instradato su ``da`` (es. T3) è stato rifatto su ``a`` (es. T1).

        L'osservabilità aggrega la "% escalation" per workflow: è il segnale che il
        modello locale del tier ``da`` va riaddestrato (§3.1 / §3.7).
        """
        self.evento("escalation", step=step, da=da, a=a, motivo=motivo)

    def run_end(self, outcome: str, **campi: Any) -> None:
        self.evento("run_end", outcome=outcome, **campi)

    # ------------------------------------------------------------- interni

    def _appendi(self, path: Path, record: dict[str, Any]) -> None:
        riga = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as file:
                file.write(riga + "\n")
