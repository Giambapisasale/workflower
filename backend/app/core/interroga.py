"""Query Agent di ``POST /ask`` (piano §3.4): domanda → SQL su viste → risposta.

Le istruzioni per il modello vivono in ``data/workflows/interroga/`` (sono
dato, non codice, e l'Improver potrà correggerle); il tier arriva dal
manifest. Guardrail non negoziabili, applicati QUI e non dal modello:
solo SELECT, solo viste ``v_*``, LIMIT forzato, timeout.

Per l'operatore il contratto è "mai un errore tecnico": qualunque cosa
vada storta, ``rispondi_operatore`` ritorna una frase di cortesia.

Ogni interrogazione è un **run tracciato** come quelle dei documenti
(``data/traces/AAAA/MM/<run_id>.jsonl``, workflow ``interroga``). Prima non lo
era, e la conseguenza è che il costo di ``/ask`` non compariva
nell'osservabilità e le domande non erano materia prima per niente: né per
l'Improver, né per misurare un tier locale sull'interrogazione. La copia
integrale della query resta in ``dataset/queries.jsonl``, registrata qui per
**entrambe** le modalità (prima solo per l'ufficio: le domande degli operatori,
che sono le più vere, non venivano contate).
"""

import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturoScaduto
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import yaml

from app.core.dal import DAL
from app.core.dataset import fingerprint, registra_query
from app.core.gateway import Gateway
from app.core.tracer import Tracer
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

# Funzioni standard SQL in cui ``FROM`` è un **separatore di argomenti**, non
# l'inizio di una clausola: ``EXTRACT(YEAR FROM data)``, ``TRIM(BOTH ' ' FROM s)``,
# ``SUBSTRING(s FROM 2 FOR 3)``, ``OVERLAY(s PLACING t FROM 2)``. Per :data:`TABELLE`
# quel ``FROM`` è indistinguibile da un riferimento a tabella, e la query veniva
# rifiutata («trovato: CURRENT_DATE») pur essendo lettura pura.
FUNZIONI_CON_FROM = frozenset({"extract", "substring", "trim", "overlay"})
_TOKEN = re.compile(r"'[^']*'|\w+|[()]|\S")


class InterrogaError(Exception):
    """Query rifiutata dai guardrail o non eseguibile."""


def estrai_sql(testo: str) -> str:
    """La query dalla risposta del modello, con o senza fence markdown."""
    match = FENCE_SQL.search(testo)
    sql = (match.group(1) if match else testo).strip()
    if not sql:
        raise InterrogaError("il modello non ha prodotto una query")
    return sql


def scheletro(sql: str) -> str:
    """La query ridotta a ciò in cui può comparire un **nome di tabella**.

    Sostituisce con spazi (mai rimuove: le posizioni degli altri token restano)
    le due cose che :data:`TABELLE` confonde con un riferimento a tabella:

    1. i **letterali stringa**, dove un nome di tabella non può stare per
       definizione. Senza questo, ``WHERE nome = 'da from a form'`` viene
       rifiutato citando una tabella ``a`` che non esiste da nessuna parte;
    2. i ``FROM`` usati dalle funzioni standard come **separatore di argomenti**
       (:data:`FUNZIONI_CON_FROM`).

    Il taglio del punto 2 è chirurgico: si cancella la sola parola ``FROM``, e
    solo alla profondità di parentesi della chiamata che la usa come separatore.
    Un ``FROM`` dentro una sottoquery annidata
    (``EXTRACT(YEAR FROM (SELECT max(d) FROM v_fatture))``) sta a profondità
    maggiore, resta visibile, e la sua tabella viene controllata come sempre: il
    guardrail non si indebolisce.

    Serve **solo** alla ricerca delle tabelle. I controlli su parole e funzioni
    vietate continuano a guardare il testo integrale: là un falso rifiuto (un
    fornitore che si chiamasse «Delete») costa una risposta mancata, mentre un
    falso permesso costerebbe una scrittura.
    """
    da_cancellare: list[tuple[int, int]] = []
    # per ogni parentesi aperta: [è una funzione con FROM, il separatore è passato]
    pila: list[list[bool]] = []
    precedente = ""
    for token in _TOKEN.finditer(sql):
        testo = token.group(0)
        minuscolo = testo.lower()
        if testo.startswith("'"):
            da_cancellare.append(token.span())
        elif testo == "(":
            pila.append([precedente in FUNZIONI_CON_FROM, False])
        elif testo == ")":
            if pila:
                pila.pop()
        elif minuscolo == "from" and pila and pila[-1][0] and not pila[-1][1]:
            pila[-1][1] = True
            da_cancellare.append(token.span())
        precedente = minuscolo if minuscolo.isalpha() else ""
    if not da_cancellare:
        return sql
    caratteri = list(sql)
    for inizio, fine in da_cancellare:
        caratteri[inizio:fine] = " " * (fine - inizio)
    return "".join(caratteri)


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
    for grezzo in TABELLE.findall(scheletro(pulito)):
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


def _fetch(conn: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cursore = conn.execute(sql)
    colonne = [c[0] for c in cursore.description]
    return [
        {colonna: _semplice(valore) for colonna, valore in zip(colonne, riga, strict=True)}
        for riga in cursore.fetchall()
    ]


def esegui_query(data_dir: Path | str, sql: str) -> list[dict[str, Any]]:
    """Esegue una query di sola lettura sulle viste, con timeout. Non valida nulla.

    Funzione di modulo e non metodo perché la usa anche chi *misura* (confrontare
    due query significa eseguirle entrambe) e chi consolida: dipende solo dal repo
    dati, non da un'istanza. Chi la chiama ha già passato :func:`applica_guardrail`.
    """
    conn = connect(data_dir)
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        futuro = pool.submit(_fetch, conn, sql)
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


class Interroga:
    def __init__(self, dal: DAL, gateway: Gateway) -> None:
        self.dal = dal
        self.data_dir = Path(dal.data_dir)
        self.gateway = gateway
        self.wf_dir = self.data_dir / "workflows" / "interroga"

    # ------------------------------------------------------------ pubblico

    def rispondi_operatore(self, domanda: str, cantieri: list[dict[str, str]] | None) -> str:
        """Risposta in italiano semplice; qualunque errore diventa cortesia."""
        tracer, _ = self._avvia(domanda)
        scritti: list[Path] = []
        try:
            esito = self._interroga(domanda, cantieri, tracer, scritti)
            frase = self._frase_operatore(domanda, esito["rows"], tracer)
        except Exception as exc:
            logger.exception("interroga fallita per la domanda: %s", domanda)
            tracer.run_end("errore", errore=str(exc))
            return RISPOSTA_FALLBACK
        else:
            tracer.run_end("ok", righe=len(esito["rows"]))
            return frase
        finally:
            self._committa(tracer, *scritti)

    def esegui(
        self, domanda: str, cantieri: list[dict[str, str]] | None = None
    ) -> dict[str, Any]:
        """Genera la query, applica i guardrail, la esegue: ``{sql, rows, run_id}``."""
        tracer, run_id = self._avvia(domanda)
        scritti: list[Path] = []
        try:
            esito = self._interroga(domanda, cantieri, tracer, scritti)
        except Exception as exc:
            tracer.run_end("errore", errore=str(exc))
            raise
        else:
            tracer.run_end("ok", righe=len(esito["rows"]))
            return {**esito, "run_id": run_id}
        finally:
            self._committa(tracer, *scritti)

    # --------------------------------------------------------------- il run

    def _avvia(self, domanda: str) -> tuple[Tracer, str]:
        """Apre il run dell'interrogazione: stesso formato di quelli sui documenti.

        L'``input`` del ``run_start`` è la domanda, dove per un documento c'è il
        blob: è ciò che il run ha elaborato, e rende ``/ask`` visibile in
        ``elenco_run`` e nelle statistiche di costo come qualunque altro workflow.
        """
        manifest = self._manifest()
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        tracer = Tracer(
            self.data_dir, run_id, manifest.get("name", "interroga"),
            str(manifest.get("version", "?")),
        )
        tracer.run_start(domanda)
        return tracer, run_id

    def _committa(self, tracer: Tracer, *percorsi: Path) -> None:
        """Un solo commit per interrogazione (mutazione = commit), mai fatale.

        Il trace e la riga nel dataset delle query sono lo stesso fatto: vanno
        nello stesso commit. Stessa scelta di ``runtime._commit_artefatti``: se il
        commit fallisce, la risposta all'utente è già valida e non va buttata.
        """
        try:
            self.dal.commit_paths(
                [tracer.trace_path, *percorsi], f"trace {tracer.run_id}: interrogazione [ask]"
            )
        except Exception as exc:
            logger.warning("commit del trace %s fallito: %s", tracer.run_id, exc)

    def genera_sql(
        self,
        domanda: str,
        cantieri: list[dict[str, str]] | None = None,
        *,
        tier: str | None = None,
        tracer: Tracer | None = None,
    ) -> str:
        """Il SQL per la domanda, già passato dai guardrail. Non esegue, non registra.

        È la sola parte che dipende dal modello, isolata di proposito: serve anche
        a **misurare** un tier candidato sulla stessa domanda senza aprire un run
        e senza scrivere niente nel repo dati (:mod:`app.core.eval_interroga`).

        ``tier`` sovrascrive quello del manifest: è il solo modo di far girare la
        stessa domanda su due tier e confrontarli.
        """
        manifest = self._manifest()
        skill = (self.wf_dir / manifest["skills"]["sql"]).read_text(encoding="utf-8")
        skill = skill.replace("{schema_viste}", self._schema_viste())
        skill = skill.replace("{schema_tool}", self._schema_tool())
        contesto = f"Domanda: {domanda}"
        if cantieri:
            elenco = ", ".join(f"{c['id']} ({c['nome']})" for c in cantieri)
            contesto += f"\nCantieri di chi chiede (filtra su questi se pertinente): {elenco}"
        risposta = self.gateway.complete(
            tier=tier or manifest.get("tier", "T2"),
            messages=[
                {"role": "system", "content": skill},
                {"role": "user", "content": contesto},
            ],
            tracer=tracer,
            step="genera_sql",
        )
        return applica_guardrail(estrai_sql(risposta.text or ""))

    def _interroga(
        self,
        domanda: str,
        cantieri: list[dict[str, str]] | None,
        tracer: Tracer,
        scritti: list[Path],
    ) -> dict[str, Any]:
        """Genera la query, la esegue, la registra nel dataset e sul trace.

        ``scritti`` raccoglie i file toccati oltre al trace, perché il commit lo
        fa il chiamante (uno solo, anche se qui si è fallito a metà).
        """
        sql = self.genera_sql(domanda, cantieri, tracer=tracer)
        rows = self._esegui_sql(sql)
        scritti.append(registra_query(self.dal, domanda, sql, committa=False))
        tracer.query(domanda, sql, len(rows), fingerprint(sql))
        return {"sql": sql, "rows": rows}

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
        return esegui_query(self.data_dir, sql)

    def _frase_operatore(
        self, domanda: str, rows: list[dict[str, Any]], tracer: Tracer | None = None
    ) -> str:
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
            tracer=tracer,
            step="risposta_operatore",
        )
        return (risposta.text or "").strip() or RISPOSTA_FALLBACK
