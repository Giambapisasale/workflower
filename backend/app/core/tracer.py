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
    record = {
        "ts": _adesso(),
        "run_id": run_id,
        "evento": "operator_feedback",
        "tipo": tipo,
        "utente": utente,
        **sanitizza(campi),
    }
    with percorso.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return percorso


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

    def validation(self, step: str, esito: str, dettagli: Any = None) -> None:
        self.evento("validation", step=step, esito=esito, dettagli=dettagli)

    def run_end(self, outcome: str, **campi: Any) -> None:
        self.evento("run_end", outcome=outcome, **campi)

    # ------------------------------------------------------------- interni

    def _appendi(self, path: Path, record: dict[str, Any]) -> None:
        riga = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as file:
                file.write(riga + "\n")
