"""Riferimenti fra entità: chi punta a chi, e cosa impedisce di togliere di mezzo.

Lo schema JSON di un'entità dichiara i riferimenti come campi con il ``pattern``
dell'id di un altro tipo (``fornitore_id`` porta il pattern di ``fornitore``): la
mappa campo→tipo si **deduce**, non si cabla. È il motivo per cui aggiungere
un'entità resta un'operazione sui dati.

Vive in ``core`` perché serve a due chiamanti con lo stesso bisogno — non
cancellare né scartare qualcosa che altri documenti stanno ancora usando:
``api/entities.py`` (eliminazione) e ``api/scarti.py`` (scarto).
"""

import json
from pathlib import Path
from typing import Any

from app.core.dal import DAL, ENTITY_TYPES, DalError

# Tipi da scandire in cerca di riferimenti: tutti tranno il wrapper di sistema
# ``documento``, che collega l'entità estratta con ``entity_id`` (nessun pattern
# nello schema) e non è un riferimento di dominio.
TIPI_CON_RIFERIMENTI = [t for t in ENTITY_TYPES if t != "documento"]


def schema_entita(dal: DAL, tipo: str) -> dict[str, Any]:
    percorso = dal.data_dir / "schemas" / f"{tipo}.schema.json"
    return json.loads(Path(percorso).read_text(encoding="utf-8"))


def campi_riferimento(schema: dict[str, Any]) -> dict[str, str]:
    """``{campo: tipo}`` per i campi il cui ``pattern`` combacia con la regex id di un
    tipo entità (es. ``fornitore_id`` → ``fornitore``). Guarda anche dentro gli
    array (``righe``/``voci``); ``voce_computo_id`` non ha pattern e resta fuori,
    è il caso a parte del computo gestito da :func:`referenti`."""
    trovati: dict[str, str] = {}

    def scan(proprieta: dict[str, Any] | None) -> None:
        for nome, spec in (proprieta or {}).items():
            if not isinstance(spec, dict):
                continue
            pattern = spec.get("pattern")
            if pattern:
                for tipo, regola in ENTITY_TYPES.items():
                    if regola["id"].pattern == pattern:
                        trovati[nome] = tipo
            tipo_spec = spec.get("type")
            e_array = tipo_spec == "array" or (
                isinstance(tipo_spec, list) and "array" in tipo_spec
            )
            if e_array:
                scan((spec.get("items") or {}).get("properties"))

    scan(schema.get("properties"))
    return trovati


def _voci_computo(dal: DAL, computo_id: str) -> set[str]:
    try:
        computo = dal.read("computo", computo_id)
    except DalError:
        return set()
    return {v.get("id") for v in (computo.dati.get("voci") or []) if v.get("id")}


def referenti(dal: DAL, tipo: str, entity_id: str) -> list[str]:
    """Gli id delle entità che referenziano ``entity_id`` (guardia di rimozione).

    Scansione robusta via ``list_all`` (non le viste, che su un tipo vuoto non si
    devono nemmeno interrogare). Copre i riferimenti ``*_id`` derivati dagli schemi
    e, per il computo, i ``voce_computo_id`` delle righe che puntano alle sue voci.

    Gli scartati non contano: sono già fuori dai conti, e un loro riferimento non
    deve impedire di togliere un'anagrafica.
    """
    voci = _voci_computo(dal, entity_id) if tipo == "computo" else set()
    trovati: list[str] = []
    for altro in TIPI_CON_RIFERIMENTI:
        campi = [c for c, t in campi_riferimento(schema_entita(dal, altro)).items() if t == tipo]
        controlla_voci = tipo == "computo" and altro in ("fattura", "ddt")
        if not campi and not controlla_voci:
            continue
        for entita in dal.list_all(altro):
            righe = entita.dati.get("righe") or []
            per_campo = any(entita.dati.get(c) == entity_id for c in campi)
            # riferimento annidato nelle righe (es. ``mezzo_id`` su una riga fattura)
            per_riga = any(r.get(c) == entity_id for r in righe for c in campi)
            per_voce = controlla_voci and any(r.get("voce_computo_id") in voci for r in righe)
            if per_campo or per_riga or per_voce:
                trovati.append(entita.id)
    return trovati


def verifica_riferimenti(dal: DAL, tipo: str, dati: dict[str, Any]) -> list[str]:
    """I riferimenti (``fornitore_id``/``cantiere_id``…) che puntano a entità
    inesistenti: lo schema valida il formato dell'id, non la sua esistenza."""
    mancanti = []
    for campo, target in campi_riferimento(schema_entita(dal, tipo)).items():
        valore = dati.get(campo)
        if not valore:
            continue
        try:
            dal.read(target, str(valore))
        except DalError:
            mancanti.append(f"{ENTITY_TYPES[target]['etichetta']} {valore} non esiste")
    return mancanti


def messaggio_referenti(tipo: str, entity_id: str, trovati: list[str]) -> str:
    """La frase che spiega perché non si può togliere di mezzo (409)."""
    elenco = ", ".join(trovati[:8]) + ("…" if len(trovati) > 8 else "")
    return (
        f"{ENTITY_TYPES[tipo]['etichetta']} {entity_id} è ancora usato da "
        f"{len(trovati)} documenti ({elenco}): rimuovi o sposta prima i collegamenti."
    )
