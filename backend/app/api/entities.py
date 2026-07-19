"""Gestione manuale dei dati (M13): CRUD admin generico, guidato dagli schemi.

L'ufficio ha bisogno di inserire/aggiornare/eliminare i dati a mano — un nuovo
fornitore, il budget di un cantiere corretto, una fattura arrivata su carta, un
doppione da togliere. Tutto passa dal DAL (validazione schema + commit git), come
ogni altra scrittura. Nessun form scritto a mano per tipo: il frontend genera i
form dallo schema JSON di ogni entità, così "aggiungere un'entità = dati, non
codice" vale anche per la gestione manuale.

Riservato all'ufficio (admin). Le voci create a mano nascono già ``validato`` (chi
le inserisce è l'autorità, come il seed) e senza documento allegato.
"""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_dal, richiedi_admin
from app.core.auth import Utente
from app.core.dal import (
    DAL,
    ENTITY_TYPES,
    TIPI_INGRESSO,
    DalError,
    SchemaValidationError,
)
from app.models.envelope import Meta

router = APIRouter(tags=["entities"])

# Tipi gestibili a mano: tutti tranne il wrapper di sistema ``documento`` (che
# nasce e vive nel flusso di caricamento). L'ordine del registry è già "prima le
# anagrafiche, poi i documenti", comodo per la UI.
TIPI_GESTIBILI = [t for t in ENTITY_TYPES if t != "documento"]


# ------------------------------------------------------------------ interni


def _assicura_gestibile(tipo: str) -> None:
    if tipo not in TIPI_GESTIBILI:
        raise HTTPException(status_code=404, detail=f"tipo non gestibile a mano: {tipo}")


def _schema(dal: DAL, tipo: str) -> dict[str, Any]:
    percorso = dal.data_dir / "schemas" / f"{tipo}.schema.json"
    return json.loads(percorso.read_text(encoding="utf-8"))


def _campi_riferimento(schema: dict[str, Any]) -> dict[str, str]:
    """{campo: tipo} per i campi il cui ``pattern`` combacia con la regex id di un
    tipo entità (es. ``fornitore_id`` → ``fornitore``). Guarda anche dentro gli
    array (``righe``/``voci``); ``voce_computo_id`` non ha pattern e resta fuori,
    è il caso a parte del computo gestito da :func:`_referenti`."""
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
            if spec.get("type") == "array":
                scan((spec.get("items") or {}).get("properties"))

    scan(schema.get("properties"))
    return trovati


def _voci_computo(dal: DAL, computo_id: str) -> set[str]:
    try:
        computo = dal.read("computo", computo_id)
    except DalError:
        return set()
    return {v.get("id") for v in (computo.dati.get("voci") or []) if v.get("id")}


def _referenti(dal: DAL, tipo: str, entity_id: str) -> list[str]:
    """Gli id delle entità che referenziano ``entity_id`` (guardia di eliminazione).

    Scansione robusta via ``list_all`` (non le viste, che su un tipo vuoto non si
    devono nemmeno interrogare). Copre i riferimenti ``*_id`` derivati dagli schemi
    e, per il computo, i ``voce_computo_id`` delle righe che puntano alle sue voci.
    """
    voci = _voci_computo(dal, entity_id) if tipo == "computo" else set()
    referenti: list[str] = []
    for altro in TIPI_GESTIBILI:
        campi = [c for c, t in _campi_riferimento(_schema(dal, altro)).items() if t == tipo]
        controlla_voci = tipo == "computo" and altro in ("fattura", "ddt")
        if not campi and not controlla_voci:
            continue
        for entita in dal.list_all(altro):
            per_campo = any(entita.dati.get(c) == entity_id for c in campi)
            per_voce = controlla_voci and any(
                r.get("voce_computo_id") in voci for r in (entita.dati.get("righe") or [])
            )
            if per_campo or per_voce:
                referenti.append(entita.id)
    return referenti


def _verifica_riferimenti(dal: DAL, tipo: str, dati: dict[str, Any]) -> list[str]:
    """I riferimenti (``fornitore_id``/``cantiere_id``…) che puntano a entità
    inesistenti: lo schema valida il formato dell'id, non la sua esistenza."""
    mancanti = []
    for campo, target in _campi_riferimento(_schema(dal, tipo)).items():
        valore = dati.get(campo)
        if not valore:
            continue
        try:
            dal.read(target, str(valore))
        except DalError:
            mancanti.append(f"{ENTITY_TYPES[target]['etichetta']} {valore} non esiste")
    return mancanti


def _scollega_documento(dal: DAL, entity_id: str, attore: str) -> None:
    """Toglie il puntatore all'entità dal documento caricato che la generò, così
    l'eliminazione non lascia un riferimento pendente nel fascicolo dell'operatore."""
    for doc in dal.list_all("documento"):
        if doc.dati.get("entity_id") == entity_id:
            doc.dati["entity_id"] = None
            doc.dati["entity_tipo"] = None
            dal.update(doc, run_id=f"manual:{attore}")


def _titolo(tipo: str, dati: dict[str, Any]) -> str | None:
    """Etichetta breve di una voce, per liste e picker (nome, ragione sociale…)."""
    campo = {
        "cantiere": "nome",
        "fornitore": "ragione_sociale",
        "computo": "descrizione",
        "fattura": "numero",
        "ddt": "numero",
        "sal": "numero",
        "rapportino": "data",
    }.get(tipo)
    valore = dati.get(campo) if campo else None
    return str(valore) if valore not in (None, "") else None


def _msg_schema(exc: SchemaValidationError) -> str:
    return "Dati non validi: " + "; ".join(exc.errors)


# ------------------------------------------------------------------ endpoint


@router.get("/entities/meta")
def meta(
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Catalogo dei tipi gestibili con il loro schema: alimenta i form generici."""
    tipi = []
    for tipo in TIPI_GESTIBILI:
        schema = _schema(dal, tipo)
        tipi.append(
            {
                "tipo": tipo,
                "etichetta": ENTITY_TYPES[tipo]["etichetta"],
                "is_master": tipo not in TIPI_INGRESSO,
                "per_anno": ENTITY_TYPES[tipo]["per_anno"],
                "schema": schema,
                "riferimenti": _campi_riferimento(schema),
            }
        )
    return {"tipi": tipi}


@router.get("/entities/{tipo}")
def elenco(
    tipo: str,
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Elenco delle voci di un tipo (per le liste admin e i picker di riferimento)."""
    _assicura_gestibile(tipo)
    voci = [
        {"id": e.id, "stato": e.stato, "titolo": _titolo(tipo, e.dati), "dati": e.dati}
        for e in dal.list_all(tipo)
    ]
    voci.sort(key=lambda v: v["id"])
    return {"tipo": tipo, "etichetta": ENTITY_TYPES[tipo]["etichetta"], "voci": voci}


@router.get("/entities/{tipo}/{entity_id}")
def leggi(
    tipo: str,
    entity_id: str,
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    _assicura_gestibile(tipo)
    try:
        return dal.read(tipo, entity_id).model_dump()
    except DalError as exc:
        raise HTTPException(status_code=404, detail="entità non trovata") from exc


class DatiRichiesta(BaseModel):
    dati: dict[str, Any]


@router.post("/entities/{tipo}")
def crea(
    tipo: str,
    body: DatiRichiesta,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Crea una voce a mano: nasce ``validato`` (l'ufficio è l'autorità), niente blob."""
    _assicura_gestibile(tipo)
    mancanti = _verifica_riferimenti(dal, tipo, body.dati)
    if mancanti:
        raise HTTPException(status_code=422, detail="; ".join(mancanti))
    try:
        env = dal.crea_progressivo(
            tipo,
            body.dati,
            stato="validato",
            meta=Meta(validato_da=admin.username),
            tag=f"manual:{admin.username}",
        )
    except SchemaValidationError as exc:
        raise HTTPException(status_code=422, detail=_msg_schema(exc)) from exc
    except DalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": env.id, "stato": env.stato}


@router.put("/entities/{tipo}/{entity_id}")
def aggiorna(
    tipo: str,
    entity_id: str,
    body: DatiRichiesta,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Aggiorna i dati di una voce (conserva stato e meta; round-trip completo dei dati)."""
    _assicura_gestibile(tipo)
    try:
        esistente = dal.read(tipo, entity_id)
    except DalError as exc:
        raise HTTPException(status_code=404, detail="entità non trovata") from exc
    mancanti = _verifica_riferimenti(dal, tipo, body.dati)
    if mancanti:
        raise HTTPException(status_code=422, detail="; ".join(mancanti))
    env = esistente.model_copy(deep=True)
    env.dati = body.dati
    try:
        aggiornata = dal.update(env, run_id=f"manual:{admin.username}")
    except SchemaValidationError as exc:
        raise HTTPException(status_code=422, detail=_msg_schema(exc)) from exc
    except DalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": aggiornata.id, "stato": aggiornata.stato}


@router.delete("/entities/{tipo}/{entity_id}")
def elimina(
    tipo: str,
    entity_id: str,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Elimina una voce, bloccando se è ancora referenziata (mai cascade)."""
    _assicura_gestibile(tipo)
    try:
        dal.read(tipo, entity_id)
    except DalError as exc:
        raise HTTPException(status_code=404, detail="entità non trovata") from exc
    referenti = _referenti(dal, tipo, entity_id)
    if referenti:
        elenco = ", ".join(referenti[:8]) + ("…" if len(referenti) > 8 else "")
        raise HTTPException(
            status_code=409,
            detail=(
                f"{ENTITY_TYPES[tipo]['etichetta']} {entity_id} è ancora usato da "
                f"{len(referenti)} documenti ({elenco}): rimuovi o sposta prima i collegamenti."
            ),
        )
    if tipo in TIPI_INGRESSO:
        _scollega_documento(dal, entity_id, admin.username)
    dal.delete(tipo, entity_id, tag=f"manual:{admin.username}")
    return {"ok": True}
