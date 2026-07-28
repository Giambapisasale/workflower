"""Vocabolari dei valori per il prompt di ``/ask``: non i nomi delle colonne, i valori.

Il catalogo delle viste (``Interroga._schema_viste``) dice come si chiamano le
colonne e di che tipo sono. Non dice **quali valori** ci stanno dentro, e il modello
quel buco lo colmava inventando: ``provincia = 'catania'`` dove il dato è ``'CT'``,
``proprieta = 'proprietà'`` dove l'elenco ammette ``proprio``, ``stato = 'aperto'``
dove ``stato`` è lo stato del record. Quattro dei sette errori veri delle 120 domande
di :file:`scripts/testbook_domande.json` sono di questa specie: non il modello che
ragiona male, il prompt che non gli ha detto il dominio.

I valori **non** si campionano dal dato (``SELECT DISTINCT``): sarebbe un prompt che
cambia col volume del repo, e un vocabolario che si accorcia quando i dati crescono.
Si leggono dove sono *dichiarati* — gli ``enum`` e i ``pattern`` negli schemi delle
entità, che sono il contratto. Aggiungere un'entità con un elenco chiuso lo fa
comparire nel prompt da sé: dato, non codice.

Il solo pezzo che gli schemi non sanno è il nome che la colonna ha **nella vista**,
perché :file:`data/config/views.sql` rinomina i campi che collidono con lo ``stato``
del record (``dati.stato AS stato_pagamento``). Si ricava dallo stesso ``views.sql``,
e da lì si propaga alle viste derivate che riespongono la colonna
(``v_mezzi_tco.proprieta``: era proprio quella dell'errore).
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, NamedTuple

from app.core.dal import ENTITY_TYPES
from app.core.views import connect
from app.models.envelope import Stato

logger = logging.getLogger("workflower.vocabolari")

# ``CREATE OR REPLACE VIEW v_x AS`` — segna l'inizio del corpo di una vista.
INIZIO_VISTA = re.compile(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(\w+)\s+AS", re.IGNORECASE)
# ``dati.campo AS colonna`` — la sola forma con cui views.sql espone un campo JSON.
ALIAS_CAMPO = re.compile(r"dati\.(\w+)\s+AS\s+(\w+)", re.IGNORECASE)
# ``entities/<cartella>/`` dentro la read_json: dice di che entità è la vista.
CARTELLA_ENTITA = re.compile(r"entities/(\w+)/")
# ``unnest(dati.righe, recursive := true)`` — le viste "righe" srotolano un array di
# struct e le colonne prendono il nome delle proprietà dell'elemento, senza alias.
CAMPO_SROTOLATO = re.compile(r"unnest\s*\(\s*dati\.(\w+)", re.IGNORECASE)

STATI_RECORD = tuple(Stato.__args__)  # type: ignore[attr-defined]


class Origine(NamedTuple):
    """Da dove una vista prende i dati: il tipo di entità e come ne espone i campi."""

    tipo: str
    campi: dict[str, str]  # campo dello schema → colonna della vista
    srotolati: frozenset[str]  # array di struct passati da ``unnest``


class Vocabolario(NamedTuple):
    """Ciò che una colonna accetta: un elenco chiuso di valori, oppure un formato."""

    colonna: str
    viste: tuple[str, ...]
    valori: tuple[str, ...] = ()
    formato: str = ""

    @property
    def chiuso(self) -> bool:
        return bool(self.valori)


def _e_identificatore(campo: str) -> bool:
    """``id``, ``cantiere_id``, ``fornitore_id``… — esclusi di proposito.

    Il loro ``pattern`` è dichiarato come tutti gli altri, ma metterlo nel prompt
    invita il modello a *indovinare* un id (``cantiere_id = 'CNT-001'``) invece di
    partire dal nome e fare la join su ``v_cantieri``. Un formato senza l'elenco dei
    valori non aiuta a filtrare: aiuta a sbagliare con più sicurezza.
    """
    return campo == "id" or campo.endswith("_id")


def _schema(data_dir: Path, tipo: str) -> dict[str, Any]:
    percorso = data_dir / "schemas" / f"{tipo}.schema.json"
    if not percorso.is_file():
        return {}
    try:
        return json.loads(percorso.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("schema %s non leggibile: vocabolari incompleti", percorso.name)
        return {}


def viste_per_entita(views_sql: str) -> dict[str, Origine]:
    """Per ogni vista di registro: da che entità legge e come ne espone i campi.

    Le viste derivate (quelle che leggono altre viste, non ``entities/``) non
    compaiono: il loro vocabolario si propaga per nome, in :func:`vocabolari`.
    """
    per_cartella = {spec["dir"]: tipo for tipo, spec in ENTITY_TYPES.items()}
    tagli = [(m.group(1), m.start()) for m in INIZIO_VISTA.finditer(views_sql)]
    trovate: dict[str, Origine] = {}
    for i, (vista, inizio) in enumerate(tagli):
        fine = tagli[i + 1][1] if i + 1 < len(tagli) else len(views_sql)
        corpo = views_sql[inizio:fine]
        cartelle = {m.group(1) for m in CARTELLA_ENTITA.finditer(corpo)}
        tipi = {per_cartella[c] for c in cartelle if c in per_cartella}
        if len(tipi) != 1:  # nessuna entità, o una vista che ne unisce due: si salta
            continue
        trovate[vista] = Origine(
            tipo=tipi.pop(),
            campi=dict(ALIAS_CAMPO.findall(corpo)),
            srotolati=frozenset(CAMPO_SROTOLATO.findall(corpo)),
        )
    return trovate


def _colonne(schema: dict[str, Any], origine: Origine) -> list[tuple[str, dict[str, Any]]]:
    """Le colonne che una vista espone, accoppiate alla loro definizione nello schema.

    Due casi. I campi semplici prendono il nome dall'alias di ``views.sql``. I campi
    che sono **array di struct** (le righe di una fattura, di un DDT, di un
    rapportino) vengono srotolati da ``unnest(dati.righe, recursive := true)``, e
    allora le colonne prendono il nome delle proprietà dell'elemento, senza passare
    da un alias: è così che ``tipo_costo`` finisce in ``v_fatture_righe``.

    Quel secondo caso è il più insidioso proprio perché non si vede: l'enum di
    ``tipo_costo`` (``noleggio | carburante | manutenzione | assicurazione | bollo``)
    è dichiarato dentro ``righe.items``, e senza guardarci il modello scriveva
    ``tipo_costo = 'materiale'``. Query legittima, esito zero, nessun errore: la
    somma tornava a zero e sembrava un dato.
    """
    trovate: list[tuple[str, dict[str, Any]]] = []
    for campo, definizione in schema.get("properties", {}).items():
        if _e_identificatore(campo):
            continue
        if campo in origine.srotolati:
            elemento = definizione.get("items", {}).get("properties", {})
            trovate += [
                (nome, d) for nome, d in elemento.items() if not _e_identificatore(nome)
            ]
        elif colonna := origine.campi.get(campo):
            trovate.append((colonna, definizione))
    return trovate


def vocabolari(data_dir: Path | str) -> list[Vocabolario]:
    """I vocabolari dichiarati, con l'elenco delle viste in cui la colonna compare.

    Due passaggi. Prima gli schemi delle entità danno il vocabolario e ``views.sql``
    il nome della colonna nella vista di registro. Poi, per le colonne il cui nome
    porta **un solo** vocabolario, si aggiungono le viste derivate che riespongono
    quel nome: ``proprieta`` in ``v_mezzi_tco`` significa ciò che significa in
    ``v_mezzi``. Dove il nome è ambiguo (``tipo`` è un elenco diverso per dipendenti,
    mezzi e manutenzioni) non si propaga niente: si resta alle viste in cui il campo
    è dichiarato, perché un vocabolario attribuito alla vista sbagliata è peggio di
    un vocabolario mancante.
    """
    data_dir = Path(data_dir)
    views_sql = (data_dir / "config" / "views.sql").read_text(encoding="utf-8")
    schemi: dict[str, dict[str, Any]] = {}
    # (colonna, valori, formato) → viste che la espongono
    raccolta: dict[tuple[str, tuple[str, ...], str], set[str]] = {}
    for vista, origine in viste_per_entita(views_sql).items():
        schema = schemi.setdefault(origine.tipo, _schema(data_dir, origine.tipo))
        for colonna, definizione in _colonne(schema, origine):
            valori = tuple(v for v in definizione.get("enum", []) if isinstance(v, str))
            formato = definizione.get("pattern", "") if not valori else ""
            if valori or formato:
                raccolta.setdefault((colonna, valori, formato), set()).add(vista)

    per_colonna: dict[str, int] = {}
    for colonna, _, _ in raccolta:
        per_colonna[colonna] = per_colonna.get(colonna, 0) + 1
    ambigue = {colonna for colonna, quante in per_colonna.items() if quante > 1}

    derivate = _viste_derivate(data_dir, {c for c, _, _ in raccolta} - ambigue)
    trovati = [
        Vocabolario(
            colonna=colonna,
            viste=tuple(sorted(viste | derivate.get(colonna, set()))),
            valori=valori,
            formato=formato,
        )
        for (colonna, valori, formato), viste in raccolta.items()
    ]
    # prima gli elenchi chiusi, poi i formati; a parità, ordine alfabetico
    return sorted(trovati, key=lambda v: (not v.chiuso, v.colonna))


def _viste_derivate(data_dir: Path, colonne: set[str]) -> dict[str, set[str]]:
    """Per ogni colonna non ambigua, le viste che la espongono secondo DuckDB.

    Si interroga il catalogo e non ``views.sql`` perché una vista derivata può
    prendere la colonna da un'altra vista, o rinominarla: l'unica fonte che sa
    davvero quali colonne ha una vista è il motore. Se il catalogo non si apre il
    prompt resta ai vocabolari delle viste di registro: meno informazione, non
    informazione sbagliata.
    """
    if not colonne:
        return {}
    try:
        conn = connect(data_dir)
    except Exception as exc:
        logger.warning("catalogo viste non disponibile: %s", exc)
        return {}
    try:
        righe = conn.execute(
            "SELECT table_name, column_name FROM duckdb_columns() "
            "WHERE table_name LIKE 'v\\_%' ESCAPE '\\'"
        ).fetchall()
    except Exception as exc:
        logger.warning("colonne delle viste non leggibili: %s", exc)
        return {}
    finally:
        conn.close()
    per_colonna: dict[str, set[str]] = {}
    for vista, colonna in righe:
        if colonna in colonne:
            per_colonna.setdefault(colonna, set()).add(vista)
    return per_colonna


def blocco(data_dir: Path | str) -> str:
    """Il testo da mettere nel prompt al posto di ``{vocabolari}``."""
    trovati = vocabolari(data_dir)
    righe = [
        f"Lo `stato` presente in molte viste è lo stato del **record** nel registro "
        f"({' | '.join(STATI_RECORD)}): non è un avanzamento di lavori né di pagamenti. "
        "Gli avanzamenti hanno una colonna con un nome esplicito, elencata qui sotto.",
    ]
    chiusi = [v for v in trovati if v.chiuso]
    formati = [v for v in trovati if not v.chiuso]
    if chiusi:
        righe.append(
            "\nElenchi chiusi. Usa **esattamente** uno di questi valori, mai la "
            "parafrasi italiana né il plurale:"
        )
        righe += [
            f"- `{v.colonna}` ({', '.join(v.viste)}): {' | '.join(v.valori)}" for v in chiusi
        ]
    if formati:
        righe.append("\nFormati fissi (espressione regolare):")
        righe += [f"- `{v.colonna}` ({', '.join(v.viste)}): {v.formato}" for v in formati]
    return "\n".join(righe)
