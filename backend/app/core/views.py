"""Viste DuckDB in sola lettura sul repo dati.

Il catalogo vive in ``data/config/views.sql`` (è dato, non codice): le viste
rileggono i file JSON a ogni query — nessuna cache, dati sempre freschi.
Le query passano dalle viste, mai dai file grezzi (ADR-1).
"""

from pathlib import Path

import duckdb


def connect(data_dir: Path | str) -> duckdb.DuckDBPyConnection:
    """Connessione in-memory con il catalogo viste installato.

    Richiede un repo dati già seminato: le viste si legano ai file JSON
    esistenti al momento della creazione (glob vuoto = errore esplicito).
    """
    base = Path(data_dir).resolve()
    raw = (base / "config" / "views.sql").read_text(encoding="utf-8")
    sql = raw.replace("${DATA_DIR}", base.as_posix())
    conn = duckdb.connect(":memory:")
    for statement in _statements(sql):
        conn.execute(statement)
    return conn


def _statements(sql: str) -> list[str]:
    """Divide il catalogo in statement: via i commenti, split sul punto e virgola.

    Convenzione del catalogo: niente punto e virgola dentro i literal e
    niente commenti in coda alle righe SQL.
    """
    righe = [r for r in sql.splitlines() if not r.lstrip().startswith("--")]
    return [s.strip() for s in "\n".join(righe).split(";") if s.strip()]
