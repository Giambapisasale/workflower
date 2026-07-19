"""Viste DuckDB in sola lettura sul repo dati.

Il catalogo vive in ``data/config/views.sql`` (è dato, non codice): le viste
rileggono i file JSON a ogni query — nessuna cache, dati sempre freschi.
Le query passano dalle viste, mai dai file grezzi (ADR-1).
"""

import glob as globmod
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb


def _semplice(valore: Any) -> Any:
    if isinstance(valore, datetime | date):
        return valore.isoformat()
    if isinstance(valore, Decimal):
        return float(valore)
    return valore


def query(
    data_dir: Path | str, sql: str, parametri: list[Any] | None = None
) -> list[dict[str, Any]]:
    """Query di lettura interna (SQL scritto dal codice, non dal modello).

    Per i cruscotti e le statistiche: nessun guardrail perché la query è
    fidata. Le domande in linguaggio naturale passano invece da ``interroga``.
    """
    conn = connect(data_dir)
    try:
        cursore = conn.execute(sql, parametri or [])
        colonne = [c[0] for c in cursore.description]
        return [
            {c: _semplice(v) for c, v in zip(colonne, riga, strict=True)}
            for riga in cursore.fetchall()
        ]
    finally:
        conn.close()


def connect(data_dir: Path | str) -> duckdb.DuckDBPyConnection:
    """Connessione in-memory con il catalogo viste installato.

    Richiede un repo dati già seminato: le viste si legano ai file JSON
    esistenti al momento della creazione (glob vuoto = errore esplicito).
    Dopo le viste installa gli eventuali tool parametrici (macro), che le
    referenziano.
    """
    base = Path(data_dir).resolve()
    raw = (base / "config" / "views.sql").read_text(encoding="utf-8")
    sql = raw.replace("${DATA_DIR}", base.as_posix())
    sql = _tollera_insiemi_vuoti(sql, base)
    conn = duckdb.connect(":memory:")
    for statement in _statements(sql):
        conn.execute(statement)
    _installa_macro(conn, base)
    return conn


def _installa_macro(conn: duckdb.DuckDBPyConnection, base: Path) -> None:
    """Installa i tool parametrici da ``config/macros.sql`` (dato, come le viste).

    Sono macro tabellari DuckDB (``CREATE MACRO … AS TABLE (SELECT …)``) nate dal
    consolidamento di query ricorrenti parametriche (§3.6). Si caricano **dopo**
    le viste perché le referenziano (il binding non è ritardato). File opzionale:
    un repo senza tool resta valido e ``connect`` non cambia comportamento.
    """
    percorso = base / "config" / "macros.sql"
    if not percorso.is_file():
        return
    for statement in _statements(percorso.read_text(encoding="utf-8")):
        conn.execute(statement)


# Un ``read_json('<glob>', …)`` su un glob che non matcha alcun file solleva
# IOException già al CREATE VIEW: basta una cartella entità svuotata (dopo un
# delete) per far fallire l'intero catalogo — e con esso cruscotto, registro,
# scostamenti, report e "chiedi". Quando il glob è vuoto lo si sostituisce con
# un file sentinella ``[]``: con ``columns=`` la vista nasce con lo schema
# giusto e zero righe. I glob non vuoti restano intatti; ``views.sql`` non
# cambia (è dato) e la sentinella sta fuori dal glob delle entità (il DAL non
# la vede). Nel catalogo ogni ``read_json`` prende un unico glob tra apici.
_READ_JSON = re.compile(r"(read_json\(\s*)'([^']*)'")


def _tollera_insiemi_vuoti(sql: str, base: Path) -> str:
    sentinella = _sentinella_vuota(base)

    def sostituisci(m: re.Match[str]) -> str:
        percorso = m.group(2)
        if "*" in percorso and not globmod.glob(percorso):
            return f"{m.group(1)}'{sentinella}'"
        return m.group(0)

    return _READ_JSON.sub(sostituisci, sql)


def _sentinella_vuota(base: Path) -> str:
    """Percorso del file ``[]`` per le viste vuote (creato se manca).

    File d'infrastruttura del layer query, non stato applicativo: sempre
    ``[]`` e rigenerabile, vive in ``config/`` come ``views.sql``/``utenti.json``.
    Il seed lo crea e lo committa; qui lo si ripristina per i repo più vecchi.
    """
    percorso = base / "config" / "vuoto.json"
    if not percorso.is_file():
        percorso.parent.mkdir(parents=True, exist_ok=True)
        percorso.write_text("[]", encoding="utf-8")
    return percorso.as_posix()


def _statements(sql: str) -> list[str]:
    """Divide il catalogo in statement: via i commenti, split sul punto e virgola.

    Convenzione del catalogo: niente punto e virgola dentro i literal e
    niente commenti in coda alle righe SQL.
    """
    righe = [r for r in sql.splitlines() if not r.lstrip().startswith("--")]
    return [s.strip() for s in "\n".join(righe).split(";") if s.strip()]
