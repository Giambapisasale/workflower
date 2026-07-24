"""Consuntivo ore da interfaccia operaio (inserimento strutturato, non da file).

L'operaio collegato a un dipendente inserisce a mano le proprie ore su un cantiere
dove è allocato, con le attività svolte. Non c'è un file da leggere né estrazione
LLM: si costruisce direttamente un ``rapportino`` (una riga, il dipendente) come
``bozza``, così entra nella normale coda di revisione dell'ufficio. La tariffa NON
sta nel rapportino: arriva dal profilo del dipendente (vista ``v_rapportini_righe``).

È l'unico percorso di scrittura strutturata lato operatore: ``/documents`` vuole un
file e ``/entities/*`` è riservato all'ufficio. La guardia sui cantieri rispecchia
quella dell'upload (``documents.py``).
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_dal, utente_corrente
from app.core.auth import Utente
from app.core.dal import DAL, DalError, SchemaValidationError
from app.models.envelope import Meta

router = APIRouter(tags=["consuntivo"])


# ------------------------------------------------------------------ interni


def _dipendente_di(dal: DAL, username: str) -> Any | None:
    """L'anagrafica dipendente collegata all'utente di login (per ``username``)."""
    for dip in dal.list_all("dipendente"):
        if dip.dati.get("username") == username:
            return dip
    return None


def _cantieri_allocati(dip_dati: dict[str, Any], data: str) -> list[str]:
    """Gli id dei cantieri dove il dipendente è allocato alla data indicata.

    Le date ISO 8601 si confrontano come stringhe; ``a`` nullo = allocazione aperta.
    """
    allocati = []
    for alloc in dip_dati.get("allocazioni") or []:
        da = alloc.get("da")
        a = alloc.get("a")
        if da and da <= data and (a is None or data <= a):
            cantiere_id = alloc.get("cantiere_id")
            if cantiere_id and cantiere_id not in allocati:
                allocati.append(cantiere_id)
    return allocati


def _nomi_cantieri(dal: DAL, ids: list[str]) -> list[dict[str, str]]:
    voci = []
    for cid in ids:
        try:
            nome = str(dal.read("cantiere", cid).dati.get("nome") or cid)
        except DalError:
            nome = cid
        voci.append({"id": cid, "nome": nome})
    return voci


def _catalogo_attivita(dal: DAL) -> list[dict[str, str]]:
    voci = [
        {"id": e.id, "descrizione": str(e.dati.get("descrizione") or e.id)}
        for e in dal.list_all("lavorazione")
    ]
    voci.sort(key=lambda v: v["descrizione"].lower())
    return voci


def _pulisci_attivita(attivita: list["AttivitaIn"] | None) -> list[dict[str, Any]] | None:
    """Scarta le voci vuote; ritorna None se non resta nulla (campo omesso)."""
    pulite = []
    for a in attivita or []:
        lav = (a.lavorazione_id or "").strip() or None
        desc = (a.descrizione or "").strip() or None
        if lav or desc:
            pulite.append({"lavorazione_id": lav, "descrizione": desc})
    return pulite or None


# ------------------------------------------------------------------ modelli


class AttivitaIn(BaseModel):
    lavorazione_id: str | None = None
    descrizione: str | None = None


class ConsuntivoIn(BaseModel):
    cantiere_id: str
    data: str
    ore: float
    mansione: str | None = None
    attivita: list[AttivitaIn] | None = None


# ------------------------------------------------------------------ endpoint


@router.get("/consuntivo/contesto")
def contesto(
    data: str = Query(..., description="Giorno del consuntivo (ISO 8601, YYYY-MM-DD)"),
    utente: Utente = Depends(utente_corrente),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Chi sono, dove sono allocato quel giorno e quali attività posso scegliere."""
    dip = _dipendente_di(dal, utente.username)
    if dip is None:
        return {"dipendente": None, "cantieri": [], "attivita_disponibili": []}
    cantieri = _nomi_cantieri(dal, _cantieri_allocati(dip.dati, data))
    return {
        "dipendente": {
            "id": dip.id,
            "nome": dip.dati.get("nome"),
            "cognome": dip.dati.get("cognome"),
        },
        "cantieri": cantieri,
        "attivita_disponibili": _catalogo_attivita(dal),
    }


@router.post("/consuntivo")
def invia(
    body: ConsuntivoIn,
    utente: Utente = Depends(utente_corrente),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Registra le ore dell'operaio come rapportino ``bozza`` (va in revisione)."""
    dip = _dipendente_di(dal, utente.username)
    if dip is None:
        raise HTTPException(status_code=400, detail="nessun dipendente collegato all'utente")
    if body.ore <= 0:
        raise HTTPException(status_code=400, detail="le ore devono essere maggiori di zero")
    allocati = _cantieri_allocati(dip.dati, body.data)
    if body.cantiere_id not in allocati:
        raise HTTPException(
            status_code=403, detail="non risulti allocato a questo cantiere in questa data"
        )
    dati = {
        "cantiere_id": body.cantiere_id,
        "data": body.data,
        "righe": [
            {
                "dipendente_id": dip.id,
                "nominativo": None,
                "mansione": (body.mansione or "").strip() or None,
                "ore": body.ore,
                "costo_orario": None,
                "attivita": _pulisci_attivita(body.attivita),
            }
        ],
    }
    try:
        env = dal.crea_progressivo(
            "rapportino",
            dati,
            stato="bozza",
            meta=Meta(origine=f"consuntivo:{utente.username}"),
            tag=f"consuntivo:{utente.username}",
        )
    except SchemaValidationError as exc:
        raise HTTPException(status_code=422, detail="; ".join(exc.errors)) from exc
    except DalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": env.id}
