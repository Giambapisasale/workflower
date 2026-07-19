"""Consolidamento di una query ricorrente di ``/ask`` in una vista ``v_*``.

È la branca "vista SQL" del §3.6 (consolidamento skill→tool): quando l'ufficio
riconosce un fingerprint ricorrente fra i "candidati", lo promuove a **vista**
permanente. La vista vive in ``data/config/views.sql`` — che in questo sistema è
**dato, non codice** (vedi ``app/core/views.py``) — quindi consolidare è una
mutazione di dati con commit git, non generazione di codice: nessun Toolsmith
automatico (non-goal §5), l'umano conferma sempre il nome.

Qui stanno la preparazione e le garanzie (deriva il corpo, valida con gli stessi
guardrail di ``/ask``, e soprattutto **compila davvero** la vista su DuckDB prima
di scriverla). La scrittura del file + commit è del DAL (single-writer).
"""

import json
import re
from pathlib import Path
from typing import Any

import duckdb

from app.core.interroga import InterrogaError, valida_lettura
from app.core.views import connect

LEDGER = "consolidamenti.jsonl"

# Il nome scelto dall'ufficio: la vista sarà ``v_<nome>``. Minuscole, cifre e
# underscore, iniziale alfabetica; 3–41 caratteri per un identificatore sano.
NOME_VISTA = re.compile(r"^[a-z][a-z0-9_]{2,40}$")

# La query registrata è quella già passata dai guardrail: se il modello non
# aveva messo un LIMIT, ``applica_guardrail`` l'ha avvolta così. Per la vista
# vogliamo il SELECT interno, non l'involucro.
_INVOLUCRO = re.compile(
    r"^\s*select\s+\*\s+from\s*\(\s*(?P<inner>.+?)\s*\)\s+as\s+interroga\s+limit\s+\d+\s*$",
    re.IGNORECASE | re.DOTALL,
)
# Un LIMIT/OFFSET in coda serviva alla domanda puntuale: una vista riusabile
# espone tutte le righe e lascia il limite a chi la interroga.
_LIMIT_CODA = re.compile(r"\s+limit\s+\d+\s*(offset\s+\d+\s*)?$", re.IGNORECASE)


class ConsolidaError(Exception):
    """Consolidamento rifiutato: nome, query o compilazione della vista non validi."""


def corpo_vista(esempio_sql: str) -> str:
    """Il corpo SELECT per la vista, ripulito dall'involucro e dal LIMIT di coda."""
    testo = esempio_sql.strip()
    if match := _INVOLUCRO.match(testo):
        testo = match.group("inner").strip()
    return _LIMIT_CODA.sub("", testo).strip()


def viste_esistenti(data_dir: Path | str) -> set[str]:
    """I nomi delle viste attualmente nel catalogo (per evitare collisioni)."""
    conn = connect(data_dir)
    try:
        righe = conn.execute(
            "SELECT view_name FROM duckdb_views() WHERE NOT internal"
        ).fetchall()
    finally:
        conn.close()
    return {r[0] for r in righe}


def prova_vista(data_dir: Path | str, vista: str, corpo: str) -> int:
    """Compila la vista su una connessione usa-e-getta e ne conta le righe.

    È la rete di sicurezza: se il corpo non è valido o cita una vista
    inesistente, DuckDB solleva qui e non scriviamo nulla su ``views.sql``.
    """
    conn = connect(data_dir)
    try:
        conn.execute(f"CREATE OR REPLACE VIEW {vista} AS {corpo}")
        return int(conn.execute(f"SELECT count(*) FROM {vista}").fetchone()[0])
    except duckdb.Error as exc:
        raise ConsolidaError(f"la vista non è eseguibile: {exc}") from exc
    finally:
        conn.close()


def leggi_consolidamenti(data_dir: Path | str) -> list[dict[str, Any]]:
    """Il registro delle viste consolidate (``data/dataset/consolidamenti.jsonl``)."""
    percorso = Path(data_dir) / "dataset" / LEDGER
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


def consolidati_per_fingerprint(data_dir: Path | str) -> dict[str, str]:
    """Mappa fingerprint → nome vista, per marcare i candidati già consolidati."""
    return {
        c["fingerprint"]: c["vista"]
        for c in leggi_consolidamenti(data_dir)
        if c.get("fingerprint") and c.get("vista")
    }


def prepara(data_dir: Path | str, nome: str, esempio_sql: str) -> dict[str, Any]:
    """Valida nome e query e compila la vista; ritorna ``{vista, corpo, righe}``.

    Non scrive nulla: la persistenza (ledger + ``views.sql`` + commit) è del DAL.
    """
    if not NOME_VISTA.match(nome or ""):
        raise ConsolidaError(
            "nome non valido: usa lettere minuscole, numeri e underscore "
            "(3–41 caratteri, iniziale alfabetica)"
        )
    vista = f"v_{nome}"
    corpo = corpo_vista(esempio_sql)
    if not corpo:
        raise ConsolidaError("query vuota: niente da consolidare")
    try:
        valida_lettura(corpo)  # stessi guardrail di /ask: solo SELECT sulle viste v_*
    except InterrogaError as exc:
        raise ConsolidaError(str(exc)) from exc

    gia_consolidate = {c["vista"] for c in leggi_consolidamenti(data_dir)}
    riservate = viste_esistenti(data_dir) - gia_consolidate
    if vista in riservate:
        raise ConsolidaError(
            f"«{vista}» è una vista di sistema: scegli un altro nome"
        )

    righe = prova_vista(data_dir, vista, corpo)
    return {"vista": vista, "corpo": corpo, "righe": righe}
