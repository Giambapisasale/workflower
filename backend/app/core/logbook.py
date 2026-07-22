"""Logbook: log strutturato di tutte le fasi del processo (osservabilità §3.7).

Un unico registro append-only in ``data/logs/AAAA/MM/GG.jsonl`` — dentro la
fonte di verità, ma *diagnostico*, non stato applicativo: è gitignorato nel repo
dati (vedi ``app/seed.py``), quindi non produce commit. A differenza del trace
(che è per-run), il logbook è trasversale: raccoglie in un solo posto gli
eventi di avvio, API, DAL, gateway LLM, runtime, tool, sandbox e Improver — con
gli **errori** in primo piano.

Il livello è facilmente configurabile: default da ``LOG_LEVEL`` (env), override
a runtime dall'interfaccia (``PUT /api/logs/config``), persistito accanto ai log
così sopravvive ai riavvii. Nessun modello o segreto finisce nei log: le
stringhe lunghe sono troncate come nel trace.
"""

import json
import logging
import os
import threading
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RADICE = "workflower"

# Le fasi del processo che il logbook copre: alimentano il filtro dell'interfaccia
# e sono il suffisso del logger (``workflower.<fase>``). Aggiungere una fase =
# aggiungere qui la voce e usare ``ottieni_logger("<fase>")``.
FASI: tuple[str, ...] = (
    "avvio",
    "api",
    "dal",
    "gateway",
    "runtime",
    "tool",
    "sandbox",
    "toolsmith",
    "interroga",
    "dataset",
    "improver",
    "auth",
    "seed",
)

LIVELLI: tuple[str, ...] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LIVELLO_DEFAULT = "INFO"

# Oltre questa soglia una stringa nei log diventa un segnaposto con lunghezza:
# tiene fuori i base64 delle immagini e i prompt integrali, come fa il trace.
MAX_STRINGA_LOG = 400

# Chiavi di contesto che estraiamo dai record (passate via ``extra=``). Il resto
# degli attributi standard di LogRecord è ignorato.
_CAMPI_CONTESTO = ("run_id", "workflow", "step", "documento", "utente", "fase", "dettagli")

_lock = threading.Lock()
# Directory dati corrente del processo: la fissa ``configura_logging`` (una per
# app). L'handler la legge a ogni emit, così i test che ricreano l'app puntano
# sempre al loro repo temporaneo senza dover ricreare l'handler.
_data_dir: Path | None = None


def _adesso() -> datetime:
    return datetime.now(UTC)


def _tronca(valore: Any, limite: int = MAX_STRINGA_LOG) -> Any:
    """Copia del valore con le stringhe lunghe ridotte a un segnaposto."""
    if isinstance(valore, str) and len(valore) > limite:
        return f"<{len(valore)} caratteri troncati>"
    if isinstance(valore, dict):
        return {k: _tronca(v, limite) for k, v in valore.items()}
    if isinstance(valore, list):
        return [_tronca(v, limite) for v in valore]
    return valore


def _fase_da_nome(nome: str) -> str:
    """``workflower.gateway`` → ``gateway``; il logger radice resta ``workflower``."""
    if nome == RADICE:
        return RADICE
    return nome.split(".", 1)[1] if nome.startswith(RADICE + ".") else nome


def _file_del_giorno(data_dir: Path, quando: datetime) -> Path:
    return data_dir / "logs" / f"{quando:%Y}" / f"{quando:%m}" / f"{quando:%d}.jsonl"


class _JsonlHandler(logging.Handler):
    """Scrive ogni record come una riga JSON nel file del giorno.

    Robusto per costruzione: un logger non deve mai far cadere l'app, quindi
    qualunque errore di I/O viene assorbito (``handleError``) e non propagato.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            data_dir = _data_dir
            if data_dir is None:
                return
            quando = datetime.fromtimestamp(record.created, tz=UTC)
            riga = json.dumps(_record_a_dict(record, quando), ensure_ascii=False, default=str)
            percorso = _file_del_giorno(data_dir, quando)
            with _lock:
                percorso.parent.mkdir(parents=True, exist_ok=True)
                with percorso.open("a", encoding="utf-8") as file:
                    file.write(riga + "\n")
        except Exception:  # pragma: no cover - il logger non deve mai rompere il flusso
            self.handleError(record)


def _record_a_dict(record: logging.LogRecord, quando: datetime) -> dict[str, Any]:
    voce: dict[str, Any] = {
        "ts": quando.isoformat(timespec="milliseconds"),
        "livello": record.levelname,
        "fase": getattr(record, "fase", None) or _fase_da_nome(record.name),
        "logger": record.name,
        "messaggio": record.getMessage(),
    }
    for campo in _CAMPI_CONTESTO:
        if campo == "fase":
            continue
        valore = getattr(record, campo, None)
        if valore is not None:
            voce[campo] = _tronca(valore)
    if record.exc_info:
        voce["eccezione"] = "".join(traceback.format_exception(*record.exc_info)).rstrip()
    return voce


def ottieni_logger(fase: str) -> logging.Logger:
    """Il logger di una fase (``workflower.<fase>``); eredita handler e livello."""
    return logging.getLogger(f"{RADICE}.{fase}")


def _livello_persistito(data_dir: Path) -> str | None:
    percorso = data_dir / "logs" / "livello"
    try:
        valore = percorso.read_text(encoding="utf-8").strip().upper()
    except OSError:
        return None
    return valore if valore in LIVELLI else None


def _livello_iniziale(data_dir: Path) -> str:
    """Priorità: scelta persistita dall'ufficio → env ``LOG_LEVEL`` → default."""
    persistito = _livello_persistito(data_dir)
    if persistito:
        return persistito
    da_env = os.environ.get("LOG_LEVEL", "").strip().upper()
    return da_env if da_env in LIVELLI else LIVELLO_DEFAULT


def configura_logging(data_dir: Path | str, livello: str | None = None) -> str:
    """Prepara il logger radice ``workflower`` per questa app. Ritorna il livello attivo.

    Idempotente: rimonta i propri handler (file JSONL + console) a ogni chiamata,
    così ricreare l'app nei test non accumula handler né sporca lo stdout.
    """
    global _data_dir
    _data_dir = Path(data_dir).resolve()
    scelto = (livello or _livello_iniziale(_data_dir)).upper()
    if scelto not in LIVELLI:
        scelto = LIVELLO_DEFAULT

    logger = logging.getLogger(RADICE)
    logger.setLevel(scelto)
    logger.propagate = False  # evita doppioni sul root logger
    for handler in list(logger.handlers):
        if getattr(handler, "_workflower", False):
            logger.removeHandler(handler)

    file_handler = _JsonlHandler()
    file_handler._workflower = True  # type: ignore[attr-defined]
    logger.addHandler(file_handler)

    console = logging.StreamHandler()
    console._workflower = True  # type: ignore[attr-defined]
    console.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s — %(message)s")
    )
    logger.addHandler(console)
    return scelto


def imposta_livello(data_dir: Path | str, livello: str) -> str:
    """Cambia il livello a runtime e lo persiste. Solleva ``ValueError`` se ignoto."""
    scelto = livello.strip().upper()
    if scelto not in LIVELLI:
        raise ValueError(f"livello non valido: {livello!r} (attesi: {', '.join(LIVELLI)})")
    logging.getLogger(RADICE).setLevel(scelto)
    percorso = Path(data_dir) / "logs" / "livello"
    with _lock:
        percorso.parent.mkdir(parents=True, exist_ok=True)
        percorso.write_text(scelto + "\n", encoding="utf-8")
    ottieni_logger("api").info("livello di log impostato su %s", scelto)
    return scelto


def livello_corrente() -> str:
    return logging.getLevelName(logging.getLogger(RADICE).level)


# --------------------------------------------------------------------- lettura


def _file_recenti(data_dir: Path, giorni: int) -> list[Path]:
    """I file di log, dal più recente, limitati agli ultimi ``giorni``."""
    cartella = data_dir / "logs"
    file = sorted(cartella.glob("*/*/*.jsonl"), reverse=True)
    return file[: max(giorni, 1)]


def leggi_log(
    data_dir: Path | str,
    livello_min: str = "DEBUG",
    fase: str | None = None,
    testo: str | None = None,
    giorni: int = 7,
    limite: int = 500,
) -> list[dict[str, Any]]:
    """Voci di log più recenti, filtrate. Ordine: dalla più nuova alla più vecchia."""
    data_dir = Path(data_dir)
    soglia = logging.getLevelName(livello_min.upper())
    if not isinstance(soglia, int):
        soglia = logging.DEBUG
    ago = testo.lower() if testo else None
    voci: list[dict[str, Any]] = []
    for percorso in _file_recenti(data_dir, giorni):
        try:
            righe = percorso.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for riga in reversed(righe):  # dentro il giorno: cronologico → invertiamo
            if not riga.strip():
                continue
            try:
                voce = json.loads(riga)
            except json.JSONDecodeError:
                continue
            livello_voce = logging.getLevelName(str(voce.get("livello", "INFO")))
            if isinstance(livello_voce, int) and livello_voce < soglia:
                continue
            if fase and voce.get("fase") != fase:
                continue
            if ago and ago not in json.dumps(voce, ensure_ascii=False).lower():
                continue
            voci.append(voce)
            if len(voci) >= limite:
                return voci
    return voci


def statistiche_log(data_dir: Path | str, giorni: int = 7) -> dict[str, Any]:
    """Conteggi per livello e per fase sulla finestra, più il totale."""
    per_livello = dict.fromkeys(LIVELLI, 0)
    per_fase: dict[str, int] = {}
    totale = 0
    for voce in leggi_log(data_dir, giorni=giorni, limite=1_000_000):
        totale += 1
        livello = str(voce.get("livello", "INFO"))
        if livello in per_livello:
            per_livello[livello] += 1
        fase = str(voce.get("fase", "?"))
        per_fase[fase] = per_fase.get(fase, 0) + 1
    return {
        "totale": totale,
        "per_livello": per_livello,
        "per_fase": per_fase,
        "errori": per_livello["ERROR"] + per_livello["CRITICAL"],
        "giorni": giorni,
    }


def file_log_odierno(data_dir: Path | str) -> Path:
    """Percorso del file di log di oggi (per l'export/scarico)."""
    return _file_del_giorno(Path(data_dir), _adesso())
