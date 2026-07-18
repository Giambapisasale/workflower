"""Viste DuckDB in sola lettura sul repo dati.

Il catalogo vive in ``data/config/views.sql`` (è dato, non codice): le viste
rileggono i file JSON a ogni query — nessuna cache, dati sempre freschi.
Le query passano dalle viste, mai dai file grezzi (ADR-1).
"""

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
