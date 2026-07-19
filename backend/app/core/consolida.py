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
LEDGER_TOOL = "tools.jsonl"

# Il nome scelto dall'ufficio: la vista sarà ``v_<nome>`` (il tool ``t_<nome>``).
# Minuscole, cifre e underscore, iniziale alfabetica; 3–41 caratteri.
NOME_VISTA = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
# Nome di un parametro di un tool: identificatore SQL sano, anche breve.
NOME_PARAMETRO = re.compile(r"^[a-z][a-z0-9_]{0,30}$")

# Letterali "candidati a parametro" in un corpo SELECT: stringhe fra apici e
# numeri. L'ufficio ne sceglie uno o più e li nomina; il resto resta costante.
_STRINGA = re.compile(r"'[^']*'")
_NUMERO = re.compile(r"(?<![\w.'])\d+(?:\.\d+)?(?![\w.'])")

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


def _voci_ledger(percorso: Path) -> list[dict[str, Any]]:
    """Le righe di un registro JSONL come dict (righe vuote/corrotte ignorate)."""
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


def leggi_consolidamenti(data_dir: Path | str) -> list[dict[str, Any]]:
    """Il registro delle viste consolidate (``data/dataset/consolidamenti.jsonl``)."""
    return _voci_ledger(Path(data_dir) / "dataset" / LEDGER)


def leggi_tool(data_dir: Path | str) -> list[dict[str, Any]]:
    """Il registro dei tool parametrici consolidati (``data/dataset/tools.jsonl``)."""
    return _voci_ledger(Path(data_dir) / "dataset" / LEDGER_TOOL)


def consolidati_per_fingerprint(data_dir: Path | str) -> dict[str, str]:
    """Mappa fingerprint → nome artefatto (vista ``v_*`` o tool ``t_*``).

    Marca i candidati già consolidati, in una delle due forme del §3.6.
    """
    esiti: dict[str, str] = {}
    for c in leggi_consolidamenti(data_dir):
        if c.get("fingerprint") and c.get("vista"):
            esiti[c["fingerprint"]] = c["vista"]
    for c in leggi_tool(data_dir):
        if c.get("fingerprint") and c.get("macro"):
            esiti[c["fingerprint"]] = c["macro"]
    return esiti


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


# --------------------------------------------------------- tool parametrici


def letterali(corpo: str) -> list[str]:
    """I letterali di un corpo SELECT (stringhe fra apici, poi numeri), distinti.

    Sono i candidati a diventare parametri di un tool: l'ufficio ne sceglie uno
    o più e li nomina. I numeri dentro le stringhe non contano (es. ``'CNT-001'``).
    """
    trovati: list[str] = []
    visti: set[str] = set()
    for match in _STRINGA.finditer(corpo):
        testo = match.group(0)
        if testo not in visti:
            visti.add(testo)
            trovati.append(testo)
    senza_stringhe = _STRINGA.sub(lambda m: " " * len(m.group(0)), corpo)
    for match in _NUMERO.finditer(senza_stringhe):
        testo = match.group(0)
        if testo not in visti:
            visti.add(testo)
            trovati.append(testo)
    return trovati


def _identificatore(testo: str) -> re.Pattern[str]:
    """Cerca ``testo`` come token isolato (non dentro un identificatore più lungo).

    Vale sia per un nome di parametro sia per un letterale: il confine ``[\\w.]``
    evita che ``cantiere`` matchi dentro ``cantiere_id`` o ``0`` dentro ``100``.
    """
    return re.compile(r"(?<![\w.])" + re.escape(testo) + r"(?![\w.])")


def prova_tool(
    data_dir: Path | str, macro: str, parametri: list[str], corpo: str, argomenti: list[str]
) -> int:
    """Compila la macro su una connessione usa-e-getta e la chiama davvero.

    Rete di sicurezza gemella di :func:`prova_vista`: se il corpo o una vista
    referenziata non vanno, DuckDB solleva qui e non scriviamo su ``macros.sql``.
    La chiamata coi valori originali dell'esempio verifica che il tool sia
    davvero invocabile (non solo compilabile).
    """
    conn = connect(data_dir)
    try:
        firma = ", ".join(parametri)
        conn.execute(f"CREATE OR REPLACE MACRO {macro}({firma}) AS TABLE ({corpo})")
        chiamata = ", ".join(argomenti)
        return int(conn.execute(f"SELECT count(*) FROM {macro}({chiamata})").fetchone()[0])
    except duckdb.Error as exc:
        raise ConsolidaError(f"il tool non è eseguibile: {exc}") from exc
    finally:
        conn.close()


def prepara_tool(
    data_dir: Path | str, nome: str, esempio_sql: str, parametri: list[dict[str, str]]
) -> dict[str, Any]:
    """Valida e compila un tool parametrico (macro ``t_<nome>``) da un candidato.

    ``parametri`` è ``[{valore, nome}, …]``: ogni ``valore`` (un letterale
    dell'esempio) diventa il parametro ``nome`` della macro. Ritorna
    ``{macro, corpo, parametri, righe}``; non scrive nulla (persistenza al DAL).
    """
    if not NOME_VISTA.match(nome or ""):
        raise ConsolidaError(
            "nome non valido: usa lettere minuscole, numeri e underscore "
            "(3–41 caratteri, iniziale alfabetica)"
        )
    if not parametri:
        raise ConsolidaError(
            "un tool ha bisogno di almeno un parametro: se la query non ne ha, "
            "consolidala come vista"
        )
    macro = f"t_{nome}"
    corpo = corpo_vista(esempio_sql)
    if not corpo:
        raise ConsolidaError("query vuota: niente da consolidare")

    nomi = [p.get("nome", "").strip() for p in parametri]
    valori = [p.get("valore", "") for p in parametri]
    if len(set(nomi)) != len(nomi):
        raise ConsolidaError("nomi dei parametri duplicati")
    if len(set(valori)) != len(valori):
        raise ConsolidaError("valori duplicati: scegli letterali distinti da parametrizzare")
    for pnome in nomi:
        if not NOME_PARAMETRO.match(pnome):
            raise ConsolidaError(f"nome di parametro non valido: «{pnome}»")
        # Niente ombra su colonne/alias: un parametro che compare già come
        # identificatore non qualificato nel corpo verrebbe risolto al posto
        # della colonna, restituendo risultati sbagliati senza errore.
        if _identificatore(pnome).search(corpo):
            raise ConsolidaError(
                f"«{pnome}» compare già nella query: scegli un altro nome per il parametro"
            )

    parametrico = corpo
    for valore, pnome in zip(valori, nomi, strict=True):
        parametrico, sostituzioni = _identificatore(valore).subn(pnome, parametrico)
        if sostituzioni == 0:
            raise ConsolidaError(f"il valore {valore} non compare nell'esempio")

    try:
        valida_lettura(parametrico)  # stessi guardrail di /ask: solo SELECT sulle viste
    except InterrogaError as exc:
        raise ConsolidaError(str(exc)) from exc

    righe = prova_tool(data_dir, macro, nomi, parametrico, valori)
    return {"macro": macro, "corpo": parametrico, "parametri": nomi, "righe": righe}
