"""Revisione admin (piano §3.4): bozza estratta ↔ originale, feedback, validazione.

L'admin confronta i campi estratti (con confidence) con il documento originale,
lascia feedback puntuale per campo (materia prima dell'Improver, §3.5) e — quando
la bozza è corretta — la valida. Validare aggiunge il run al golden set: da quel
momento è un caso di regressione contro cui si misurano le nuove versioni.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import get_dal, richiedi_admin
from app.core.auth import Utente
from app.core.collega import Collega
from app.core.dal import DAL, TIPI_INGRESSO, DalError, tipo_da_id
from app.core.dataset import estratto_del_run, registra_derivazione
from app.core.tracer import appendi_feedback_campo, leggi_eventi
from app.models.envelope import Envelope

# Le bozze che passano dalla revisione sono le entità estratte dai workflow.
TIPI_REVISIONABILI = TIPI_INGRESSO
# Entità con righe collegabili alle voci di computo (hanno voce_computo_id).
TIPI_COLLEGABILI = ("fattura", "ddt")

router = APIRouter(tags=["review"])

# Entità prodotte dai workflow d'ingresso che passano dalla revisione umana.
# Nuovo tipo documento = una voce qui (le anagrafiche cantiere/fornitore no).
TIPI_REVISIONABILI = ("fattura", "ddt", "sal", "rapportino")


# ------------------------------------------------------------------ interni


def _entita(dal: DAL, entity_id: str) -> tuple[str, Envelope]:
    tipo = tipo_da_id(entity_id)
    if tipo is None:
        raise HTTPException(status_code=404, detail="entità non trovata")
    try:
        return tipo, dal.read(tipo, entity_id)
    except DalError as exc:
        raise HTTPException(status_code=404, detail="entità non trovata") from exc


def _nome(dal: DAL, tipo: str, entity_id: Any, campo: str) -> str | None:
    if not entity_id:
        return None
    try:
        return str(dal.read(tipo, str(entity_id)).dati.get(campo))
    except DalError:
        return None


def _documento_collegato(dal: DAL, entity_id: str) -> Envelope | None:
    for doc in dal.list_all("documento"):
        if doc.dati.get("entity_id") == entity_id:
            return doc
    return None


def _issue_collegata(dal: DAL, entity_id: str, run_id: str | None) -> dict[str, Any] | None:
    for issue in dal.list_issues():
        if issue.stato != "aperta":
            continue
        if issue.entity_id == entity_id or (run_id and issue.run_id == run_id):
            return issue.model_dump(mode="json")
    return None


def _forse_golden(dal: DAL, tipo: str, entita: Envelope) -> str | None:
    """Aggiunge la bozza validata al golden set, se ha un originale rieseguibile."""
    origine = entita.meta.origine
    if not origine or not (dal.data_dir / origine).is_file():
        return None  # es. fatture del seed: nessun blob da rieseguire
    workflow, _, versione = (entita.meta.workflow or "").partition("@")
    if not workflow:
        return None
    caso = dal.crea_golden(
        workflow=workflow,
        version=versione or "?",
        doc=origine,
        entity_tipo=tipo,
        atteso=entita.dati,
        run_id=entita.meta.run_id,
        entity_id=entita.id,
        validato_da=entita.meta.validato_da,
    )
    return caso["id"]


# ------------------------------------------------------------------ endpoint


@router.get("/review")
def coda_revisione(
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Le bozze in attesa di validazione (la coda del pannello Revisione)."""
    da_rivedere = []
    for tipo in TIPI_REVISIONABILI:
        for entita in dal.list_all(tipo):
            if entita.stato != "bozza":
                continue
            confidence = entita.meta.confidence or {}
            forn_id = entita.dati.get("fornitore_id")
            da_rivedere.append(
                {
                    "id": entita.id,
                    "tipo": tipo,
                    "fornitore": _nome(dal, "fornitore", forn_id, "ragione_sociale"),
                    "cantiere": _nome(dal, "cantiere", entita.dati.get("cantiere_id"), "nome"),
                    "totale": entita.dati.get("totale"),
                    "data": entita.dati.get("data"),
                    "confidence_min": min(confidence.values()) if confidence else None,
                    "creato": entita.meta.created,
                }
            )
    da_rivedere.sort(key=lambda d: d.get("creato") or "", reverse=True)
    return {"da_rivedere": da_rivedere}


@router.get("/review/{entity_id}")
def dettaglio_revisione(
    entity_id: str,
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    tipo, entita = _entita(dal, entity_id)
    documento = _documento_collegato(dal, entity_id)
    run_id = entita.meta.run_id
    feedback = leggi_eventi(dal.data_dir, run_id, {"field_feedback"}) if run_id else []
    return {
        "entita": entita.model_dump(),
        "tipo": tipo,
        "confidence": entita.meta.confidence or {},
        "blob": entita.meta.origine,
        "run_id": run_id,
        "documento_id": documento.id if documento else None,
        "feedback": feedback,
        "issue": _issue_collegata(dal, entity_id, run_id),
        "validato": entita.stato == "validato",
    }


@router.get("/review/{entity_id}/originale")
def originale(
    entity_id: str,
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> FileResponse:
    """Il blob originale (PDF/immagine), da mostrare a fianco dei campi estratti."""
    _tipo, entita = _entita(dal, entity_id)
    origine = entita.meta.origine
    percorso = (dal.data_dir / origine).resolve() if origine else None
    base = (dal.data_dir / "blobs").resolve()
    if percorso is None or base not in percorso.parents or not percorso.is_file():
        raise HTTPException(status_code=404, detail="originale non trovato")
    return FileResponse(percorso)


class FeedbackRichiesta(BaseModel):
    campo: str
    nota: str


@router.post("/review/{entity_id}/feedback")
def feedback_campo(
    entity_id: str,
    body: FeedbackRichiesta,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Feedback puntuale su un campo: annotato sul trace, alimenta l'Improver."""
    _tipo, entita = _entita(dal, entity_id)
    run_id = entita.meta.run_id
    campo, nota = body.campo.strip(), body.nota.strip()
    if not campo or not nota:
        raise HTTPException(status_code=422, detail="servono il campo e la nota")
    if not run_id:
        raise HTTPException(status_code=400, detail="questa entità non ha un run da annotare")
    percorso = appendi_feedback_campo(dal.data_dir, run_id, campo, nota, admin.username)
    if percorso is None:
        raise HTTPException(status_code=404, detail="trace del run non trovato")
    dal.commit_paths([percorso], f"trace {run_id}: feedback revisione [{run_id}]")
    return {"ok": True}


@router.post("/review/{entity_id}/collega")
def collega_voci(
    entity_id: str,
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Abbina le righe della bozza alle voci di computo del cantiere (M9)."""
    tipo, _entita_env = _entita(dal, entity_id)
    if tipo not in TIPI_COLLEGABILI:
        raise HTTPException(
            status_code=422, detail="il collegamento al computo vale solo per fatture e DDT"
        )
    return Collega(dal).abbina(tipo, entity_id)


@router.post("/review/{entity_id}/validate")
def valida(
    entity_id: str,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Bozza → validato + copia del run nel golden set (piano §3.4)."""
    tipo, entita = _entita(dal, entity_id)
    if entita.stato == "validato":
        return {"stato": "validato", "golden_id": None, "gia_validato": True}
    aggiornata = dal.set_validato(
        tipo, entity_id, validato_da=admin.username, run_id=entita.meta.run_id
    )
    run_id = aggiornata.meta.run_id
    if run_id:
        # Instrumentazione M16: marca il delta estratto→validato come base minabile
        # per il Toolsmith. Vive qui (revisione), non in runtime.py.
        registra_derivazione(
            dal,
            run_id=run_id,
            workflow=aggiornata.meta.workflow,
            tipo=tipo,
            entity_id=aggiornata.id,
            estratto=estratto_del_run(dal.data_dir, run_id, tipo),
            validato=aggiornata.dati,
            validato_da=admin.username,
        )
    return {
        "stato": aggiornata.stato,
        "validato_da": admin.username,
        "golden_id": _forse_golden(dal, tipo, aggiornata),
    }
