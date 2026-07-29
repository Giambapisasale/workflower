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
from app.core.riferimenti import (
    campi_riferimento,
    messaggio_referenti,
    referenti,
    schema_entita,
    verifica_riferimenti,
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
        "dipendente": "cognome",
        "mezzo": "descrizione",
        "manutenzione": "descrizione",
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
        schema = schema_entita(dal, tipo)
        tipi.append(
            {
                "tipo": tipo,
                "etichetta": ENTITY_TYPES[tipo]["etichetta"],
                "is_master": tipo not in TIPI_INGRESSO,
                "per_anno": ENTITY_TYPES[tipo]["per_anno"],
                "schema": schema,
                "riferimenti": campi_riferimento(schema),
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
    mancanti = verifica_riferimenti(dal, tipo, body.dati)
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
    mancanti = verifica_riferimenti(dal, tipo, body.dati)
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
    usato_da = referenti(dal, tipo, entity_id)
    if usato_da:
        raise HTTPException(
            status_code=409, detail=messaggio_referenti(tipo, entity_id, usato_da)
        )
    if tipo in TIPI_INGRESSO:
        _scollega_documento(dal, entity_id, admin.username)
    dal.delete(tipo, entity_id, tag=f"manual:{admin.username}")
    return {"ok": True}
