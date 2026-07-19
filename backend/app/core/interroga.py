"""Query Agent di ``POST /ask`` (piano §3.4): domanda → SQL su viste → risposta.

Le istruzioni per il modello vivono in ``data/workflows/interroga/`` (sono
dato, non codice, e l'Improver potrà correggerle); il tier arriva dal
manifest. Guardrail non negoziabili, applicati QUI e non dal modello:
solo SELECT, solo viste ``v_*``, LIMIT forzato, timeout.

Per l'operatore il contratto è "mai un errore tecnico": qualunque cosa
vada storta, ``rispondi_operatore`` ritorna una frase di cortesia.
"""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturoScaduto
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import yaml

from app.core.gateway import Gateway
from app.core.views import connect

logger = logging.getLogger("workflower.interroga")

MAX_RIGHE = 1000  # LIMIT forzato (piano §3.4)
MAX_RIGHE_PER_RISPOSTA = 50  # righe passate al modello per formulare la frase
TIMEOUT_SECONDI = 10

RISPOSTA_FALLBACK = (
    "Non sono riuscito a trovare la risposta. "
    "Prova a chiedere in un altro modo, oppure chiama l'ufficio."
)

PAROLE_VIETATE = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|detach|copy|export|import"
    r"|pragma|install|load|call|set|reset|vacuum|checkpoint|begin|transaction|grant)\b",
    re.IGNORECASE,
)
# niente funzioni che leggono file o ambiente: le viste bastano
FUNZIONI_VIETATE = re.compile(
    r"\b(read_\w+|glob|getenv|sniff_csv|scan_\w+|parquet_\w+|from_file)\s*\(",
    re.IGNORECASE,
)
TABELLE = re.compile(r"\b(?:from|join)\s+([a-zA-Z_\"][\w.\"]*)", re.IGNORECASE)
NOMI_CTE = re.compile(r"\b(\w+)\s+as\s*\(", re.IGNORECASE)
FENCE_SQL = re.compile(r"```(?:sql)?\s*(.+?)```", re.DOTALL | re.IGNORECASE)


class InterrogaError(Exception):
    """Query rifiutata dai guardrail o non eseguibile."""


def estrai_sql(testo: str) -> str:
    """La query dalla risposta del modello, con o senza fence markdown."""
    match = FENCE_SQL.search(testo)
    sql = (match.group(1) if match else testo).strip()
    if not sql:
        raise InterrogaError("il modello non ha prodotto una query")
    return sql


def valida_lettura(sql: str) -> str:
    """Valida che ``sql`` sia una singola query di sola lettura sulle viste ``v_*``.

    Ritorna la query ripulita (senza ``;`` finale) o solleva ``InterrogaError``.
    Non aggiunge il LIMIT: è il pezzo di guardrail condiviso fra l'esecuzione di
    ``/ask`` (:func:`applica_guardrail`) e il consolidamento in vista.
    """
    pulito = sql.strip().rstrip(";").strip()
    if not pulito or ";" in pulito:
        raise InterrogaError("è ammessa una sola query per volta")
    primo = pulito.split(None, 1)[0].lower()
    if primo not in {"select", "with"}:
        raise InterrogaError("sono ammesse solo query di lettura (SELECT)")
    if match := PAROLE_VIETATE.search(pulito):
        raise InterrogaError(f"parola non ammessa: {match.group(0)}")
    if match := FUNZIONI_VIETATE.search(pulito):
        raise InterrogaError(f"funzione non ammessa: {match.group(0)}")
    consentiti = {nome.lower() for nome in NOMI_CTE.findall(pulito)}  # alias delle CTE
    for grezzo in TABELLE.findall(pulito):
        nome = grezzo.strip('"').lower()
        # viste ``v_*`` e tool parametrici ``t_*`` (macro tabellari): entrambi
        # sono di sola lettura e vivono nel catalogo (config/views.sql, macros.sql).
        if not nome.startswith(("v_", "t_")) and nome not in consentiti:
            raise InterrogaError(
                f"si interrogano solo le viste v_* e i tool t_* (trovato: {grezzo})"
            )
    return pulito


def applica_guardrail(sql: str) -> str:
    """Valida la query e la ritorna con il LIMIT garantito. Non negoziabile."""
    pulito = valida_lettura(sql)
    limite = re.search(r"\blimit\s+(\d+)", pulito, re.IGNORECASE)
    if limite is None:
        return f"SELECT * FROM ({pulito}) AS interroga LIMIT {MAX_RIGHE}"
    if int(limite.group(1)) > MAX_RIGHE:
        return f"{pulito[: limite.start()]}LIMIT {MAX_RIGHE}{pulito[limite.end():]}"
    return pulito


def _semplice(valore: Any) -> Any:
    if isinstance(valore, datetime | date):
        return valore.isoformat()
    if isinstance(valore, Decimal):
        return float(valore)
    return valore


class Interroga:
    def __init__(self, data_dir: Path | str, gateway: Gateway) -> None:
        self.data_dir = Path(data_dir)
        self.gateway = gateway
        self.wf_dir = self.data_dir / "workflows" / "interroga"

    # ------------------------------------------------------------ pubblico

    def rispondi_operatore(self, domanda: str, cantieri: list[dict[str, str]] | None) -> str:
        """Risposta in italiano semplice; qualunque errore diventa cortesia."""
        try:
            esito = self.esegui(domanda, cantieri)
            return self._frase_operatore(domanda, esito["rows"])
        except Exception:
            logger.exception("interroga fallita per la domanda: %s", domanda)
            return RISPOSTA_FALLBACK

    def esegui(
        self, domanda: str, cantieri: list[dict[str, str]] | None = None
    ) -> dict[str, Any]:
        """Genera la query, applica i guardrail, la esegue: ``{sql, rows}``."""
        manifest = self._manifest()
        skill = (self.wf_dir / manifest["skills"]["sql"]).read_text(encoding="utf-8")
        skill = skill.replace("{schema_viste}", self._schema_viste())
        skill = skill.replace("{schema_tool}", self._schema_tool())
        contesto = f"Domanda: {domanda}"
        if cantieri:
            elenco = ", ".join(f"{c['id']} ({c['nome']})" for c in cantieri)
            contesto += f"\nCantieri di chi chiede (filtra su questi se pertinente): {elenco}"
        risposta = self.gateway.complete(
            tier=manifest.get("tier", "T2"),
            messages=[
                {"role": "system", "content": skill},
                {"role": "user", "content": contesto},
            ],
        )
        sql = applica_guardrail(estrai_sql(risposta.text or ""))
        return {"sql": sql, "rows": self._esegui_sql(sql)}

    # ------------------------------------------------------------- interni

    def _manifest(self) -> dict[str, Any]:
        return yaml.safe_load((self.wf_dir / "manifest.yaml").read_text(encoding="utf-8"))

    def _schema_viste(self) -> str:
        """Il catalogo per il prompt: nome vista e colonne con i tipi."""
        conn = connect(self.data_dir)
        try:
            viste = [
                r[0]
                for r in conn.execute(
                    "SELECT view_name FROM duckdb_views() WHERE NOT internal ORDER BY 1"
                ).fetchall()
            ]
            righe = []
            for vista in viste:
                colonne = conn.execute(f"DESCRIBE {vista}").fetchall()
                elenco = ", ".join(f"{nome} {tipo}" for nome, tipo, *_ in colonne)
                righe.append(f"- {vista}({elenco})")
            return "\n".join(righe)
        finally:
            conn.close()

    def _schema_tool(self) -> str:
        """Il catalogo dei tool parametrici per il prompt: nome e parametri.

        Letto dal registro ``dataset/tools.jsonl`` (fonte di verità dei tool,
        allineata a ``macros.sql`` dal DAL) — evita di dipendere da ``consolida``
        e dall'introspezione DuckDB, che non elenca le macro utente.
        """
        ledger = self.data_dir / "dataset" / "tools.jsonl"
        if not ledger.is_file():
            return "(nessuno)"
        per_macro: dict[str, list[str]] = {}
        for riga in ledger.read_text(encoding="utf-8").splitlines():
            if not riga.strip():
                continue
            try:
                voce = json.loads(riga)
            except json.JSONDecodeError:
                continue
            if voce.get("macro"):
                per_macro[voce["macro"]] = voce.get("parametri", [])
        if not per_macro:
            return "(nessuno)"
        return "\n".join(f"- {m}({', '.join(p)})" for m, p in sorted(per_macro.items()))

    def _esegui_sql(self, sql: str) -> list[dict[str, Any]]:
        conn = connect(self.data_dir)
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            futuro = pool.submit(self._fetch, conn, sql)
            try:
                return futuro.result(timeout=TIMEOUT_SECONDI)
            except FuturoScaduto:
                conn.interrupt()
                raise InterrogaError(f"query interrotta dopo {TIMEOUT_SECONDI}s") from None
            except duckdb.Error as exc:
                raise InterrogaError(f"query non eseguibile: {exc}") from exc
        finally:
            pool.shutdown(wait=False)
            conn.close()

    @staticmethod
    def _fetch(conn: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
        cursore = conn.execute(sql)
        colonne = [c[0] for c in cursore.description]
        return [
            {colonna: _semplice(valore) for colonna, valore in zip(colonne, riga, strict=True)}
            for riga in cursore.fetchall()
        ]

    def _frase_operatore(self, domanda: str, rows: list[dict[str, Any]]) -> str:
        manifest = self._manifest()
        skill = (self.wf_dir / manifest["skills"]["risposta_operatore"]).read_text(
            encoding="utf-8"
        )
        dati = json.dumps(rows[:MAX_RIGHE_PER_RISPOSTA], ensure_ascii=False)
        risposta = self.gateway.complete(
            tier=manifest.get("tier", "T2"),
            messages=[
                {"role": "system", "content": skill},
                {
                    "role": "user",
                    "content": (
                        f"Domanda dell'operatore: {domanda}\n\n"
                        f"Numeri trovati ({len(rows)} righe):\n{dati}"
                    ),
                },
            ],
        )
        return (risposta.text or "").strip() or RISPOSTA_FALLBACK
