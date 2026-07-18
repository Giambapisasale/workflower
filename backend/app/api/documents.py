"""Documenti (piano §3.4): upload → workflow in background, elenco a semaforo.

Contratto con l'operatore: MAI un errore bloccante. Il caricamento accetta
qualsiasi file; ciò che non si può elaborare diventa comunque un documento
con esito ``errore`` e una issue per l'ufficio ("ci pensiamo noi"). La
risposta dell'API parla la lingua dell'operatore: niente termini tecnici.
"""

import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import get_dal, get_runtime, utente_corrente
from app.core.auth import Utente
from app.core.classificatore import Classificatore
from app.core.dal import DAL, DalError, tipo_da_id
from app.core.runtime import WorkflowRuntime
from app.core.tools import salva_bozza
from app.core.tracer import appendi_feedback_operatore
from app.models.envelope import Envelope, now_iso

logger = logging.getLogger("workflower.documents")
router = APIRouter(tags=["documents"])

# Il workflow d'ingresso non è più fisso (Fase 2, M7): un classificatore T2
# instrada l'upload al workflow giusto (carica-fattura, carica-ddt, …). Aggiungere
# un tipo documento = aggiungere un manifest con blocco `ingest`, zero codice qui.
ESTENSIONI_LEGGIBILI = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_BYTES = 15 * 1024 * 1024
ETICHETTE_TIPO = {"fattura": "Fattura", "ddt": "DDT", "documento": "Documento"}

MSG_RIPROVA = "Non riesco a riceverlo adesso. Riprova tra qualche minuto."
MSG_TROPPO_GRANDE = "Il file è troppo pesante. Prova con una foto del documento."
MSG_VUOTO = "Il file sembra vuoto. Riprova a fotografare il documento."


class EsitoUpload(BaseModel):
    doc_id: str | None = None
    run_id: str | None = None
    messaggio: str | None = None  # solo quando il caricamento non è partito


# ------------------------------------------------------------------ upload


@router.post("/documents", response_model=EsitoUpload, response_model_exclude_none=True)
async def carica_documento(
    background: BackgroundTasks,
    file: UploadFile,
    cantiere_id: str | None = Form(default=None),
    utente: Utente = Depends(utente_corrente),
    dal: DAL = Depends(get_dal),
    runtime: WorkflowRuntime = Depends(get_runtime),
) -> EsitoUpload:
    if cantiere_id and not utente.is_admin and cantiere_id not in utente.cantieri:
        raise HTTPException(status_code=403, detail="cantiere non assegnato all'utente")
    if not cantiere_id and len(utente.cantieri) == 1:
        cantiere_id = utente.cantieri[0]

    contenuto = await file.read(MAX_BYTES + 1)
    if len(contenuto) > MAX_BYTES:
        return EsitoUpload(messaggio=MSG_TROPPO_GRANDE)
    if not contenuto:
        return EsitoUpload(messaggio=MSG_VUOTO)

    try:
        return _accetta(background, dal, runtime, utente, file.filename, cantiere_id, contenuto)
    except Exception:
        logger.exception("caricamento fallito per %s", utente.username)
        return EsitoUpload(messaggio=MSG_RIPROVA)


def _accetta(
    background: BackgroundTasks,
    dal: DAL,
    runtime: WorkflowRuntime,
    utente: Utente,
    nome_originale: str | None,
    cantiere_id: str | None,
    contenuto: bytes,
) -> EsitoUpload:
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    nome = _nome_sicuro(nome_originale)
    leggibile = Path(nome).suffix.lower() in ESTENSIONI_LEGGIBILI
    blob_rel = f"blobs/caricati/{datetime.now(UTC).year}/{uuid.uuid4().hex[:8]}-{nome}"
    percorso = dal.data_dir / blob_rel
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_bytes(contenuto)

    issue_id = None
    if not leggibile:
        issue = dal.crea_issue(
            "auto",
            f"Documento {blob_rel} in un formato che non so leggere: serve l'ufficio.",
            run_id=run_id,
            doc=blob_rel,
        )
        issue_id = issue.id

    dati: dict[str, Any] = {
        "file": blob_rel,
        "nome_originale": nome_originale or nome,
        "caricato_da": utente.username,
        "cantiere_id": cantiere_id,
        "workflow": None,  # deciso dal classificatore in _elabora
        "run_id": run_id,
        "esito": "in_corso" if leggibile else "errore",
        "entity_tipo": None,
        "entity_id": None,
        "richiede_revisione": None,
        "issue_id": issue_id,
        "conferma": None,
        "segnalazione": None,
    }
    creato = salva_bozza.esegui(
        dal,
        "documento",
        dati,
        stato="bozza" if leggibile else "errore",
        origine=f"upload:{utente.username}",
        run_id=run_id,
    )
    dal.commit_paths([percorso], f"documento {creato['id']}: allega blob [{run_id}]")

    if leggibile:
        background.add_task(_elabora, dal, runtime, creato["id"], blob_rel, run_id)
    return EsitoUpload(doc_id=creato["id"], run_id=run_id)


def _elabora(dal: DAL, runtime: WorkflowRuntime, doc_id: str, blob_rel: str, run_id: str) -> None:
    """Task in background: classifica il documento, esegue il workflow, aggiorna."""
    workflow = Classificatore(dal, runtime.gateway).workflow_per(blob_rel)  # non solleva mai
    esito = runtime.esegui(workflow, blob_rel, run_id=run_id)  # non solleva mai
    try:
        envelope = dal.read("documento", doc_id)
        envelope.dati.update(
            {
                "workflow": workflow,
                "esito": esito.esito,
                "entity_id": esito.entity_id,
                "entity_tipo": tipo_da_id(esito.entity_id),
                "richiede_revisione": esito.richiede_revisione,
                "issue_id": esito.issue_id,
            }
        )
        if esito.esito == "errore":
            envelope.stato = "errore"
        dal.update(envelope, run_id=run_id)
    except Exception:
        logger.exception("aggiornamento documento %s fallito dopo il run %s", doc_id, run_id)


def _nome_sicuro(nome: str | None) -> str:
    """Nome file senza spazi né percorsi, con l'estensione originale."""
    originale = Path(nome or "documento")
    radice = re.sub(r"[^\w-]+", "-", originale.stem).strip("-")[:40] or "documento"
    suffisso = re.sub(r"[^\w.]+", "", originale.suffix.lower())[:8]
    return f"{radice}{suffisso}"


# ------------------------------------------------------------ elenco e viste


@router.get("/documents")
def elenco_documenti(
    mine: int = 0,
    utente: Utente = Depends(utente_corrente),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Elenco a semaforo. L'operatore vede solo i propri caricamenti."""
    documenti = dal.list_all("documento")
    if not utente.is_admin or mine:
        documenti = [d for d in documenti if d.dati.get("caricato_da") == utente.username]
    documenti.sort(key=lambda d: d.meta.created or "", reverse=True)
    return {"documenti": [_vista_operatore(dal, doc) for doc in documenti]}


@router.get("/documents/{doc_id}")
def dettaglio_documento(
    doc_id: str,
    utente: Utente = Depends(utente_corrente),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    doc = _documento_di(dal, doc_id, utente)
    if utente.is_admin:
        entita = _entita_collegata(dal, doc)
        return {
            "documento": doc.model_dump(),
            "entita": entita.model_dump() if entita else None,
        }
    return _vista_operatore(dal, doc)


class ConfermaRisposta(BaseModel):
    ok: bool = True
    issue_id: str | None = None


@router.post("/documents/{doc_id}/confirm", response_model=ConfermaRisposta)
def conferma_documento(
    doc_id: str,
    utente: Utente = Depends(utente_corrente),
    dal: DAL = Depends(get_dal),
) -> ConfermaRisposta:
    """"È tutto giusto" dell'operatore: nota sul run, NON validazione (§3.4)."""
    doc = _documento_di(dal, doc_id, utente)
    if doc.dati.get("conferma"):
        return ConfermaRisposta()
    doc.dati["conferma"] = {"da": utente.username, "quando": now_iso()}
    dal.update(doc, run_id=doc.dati.get("run_id"))
    _nota_sul_trace(dal, doc, "conferma", utente)
    return ConfermaRisposta()


class SegnalazioneRichiesta(BaseModel):
    testo: str


@router.post("/documents/{doc_id}/issue", response_model=ConfermaRisposta)
def segnala_documento(
    doc_id: str,
    body: SegnalazioneRichiesta,
    utente: Utente = Depends(utente_corrente),
    dal: DAL = Depends(get_dal),
) -> ConfermaRisposta:
    """"Qualcosa non torna": issue in data/issues/ agganciata al trace."""
    testo = body.testo.strip()
    if not testo:
        raise HTTPException(status_code=422, detail="scrivi due parole su cosa non torna")
    doc = _documento_di(dal, doc_id, utente)
    esistente = doc.dati.get("segnalazione")
    if esistente:
        return ConfermaRisposta(issue_id=esistente.get("issue_id"))
    issue = dal.crea_issue(
        "operatore",
        testo,
        run_id=doc.dati.get("run_id"),
        doc=doc.dati.get("file"),
        entity_id=doc.dati.get("entity_id"),
    )
    doc.dati["segnalazione"] = {"issue_id": issue.id, "da": utente.username, "quando": now_iso()}
    dal.update(doc, run_id=doc.dati.get("run_id"))
    _nota_sul_trace(dal, doc, "segnalazione", utente, testo=testo, issue_id=issue.id)
    return ConfermaRisposta(issue_id=issue.id)


# ------------------------------------------------------------------ interni


def _documento_di(dal: DAL, doc_id: str, utente: Utente) -> Envelope:
    """Il documento, se l'utente può vederlo; altrimenti 404 (mai 'esiste ma no')."""
    try:
        doc = dal.read("documento", doc_id)
    except DalError as exc:
        raise HTTPException(status_code=404, detail="documento non trovato") from exc
    if not utente.is_admin and doc.dati.get("caricato_da") != utente.username:
        raise HTTPException(status_code=404, detail="documento non trovato")
    return doc


def _entita_collegata(dal: DAL, doc: Envelope) -> Envelope | None:
    tipo, entity_id = doc.dati.get("entity_tipo"), doc.dati.get("entity_id")
    if not tipo or not entity_id:
        return None
    try:
        return dal.read(tipo, entity_id)
    except DalError:
        return None


def _vista_operatore(dal: DAL, doc: Envelope) -> dict[str, Any]:
    """Vista semplificata: quello che l'operatore può capire, niente di più."""
    entita = _entita_collegata(dal, doc)
    semaforo, messaggio = _semaforo(doc.dati, entita)
    return {
        "id": doc.id,
        "quando": doc.meta.created,
        "in_corso": doc.dati.get("esito") == "in_corso",
        "chiuso": bool(doc.dati.get("conferma") or doc.dati.get("segnalazione")),
        "semaforo": semaforo,
        "messaggio": messaggio,
        "titolo": _titolo(dal, doc, entita),
        "riepilogo": _riepilogo(dal, entita),
    }


def _semaforo(dati: dict[str, Any], entita: Envelope | None) -> tuple[str, str]:
    if dati.get("esito") == "in_corso":
        return "giallo", "Lo sto ancora leggendo…"
    if dati.get("esito") == "errore" or (entita and entita.stato == "errore"):
        return "rosso", "Serve una mano: se ne occupa l'ufficio, ti avvisiamo noi."
    if dati.get("segnalazione"):
        return "giallo", "Segnalazione inviata: ci pensa l'ufficio."
    if entita and entita.stato == "validato":
        return "verde", "Tutto a posto."
    return "giallo", "In lavorazione: la controlla l'ufficio."


def _titolo(dal: DAL, doc: Envelope, entita: Envelope | None) -> str:
    if entita is None:
        return str(doc.dati.get("nome_originale") or "Documento")
    etichetta = ETICHETTE_TIPO.get(entita.tipo, "Documento")
    ditta = _nome_fornitore(dal, entita.dati.get("fornitore_id"))
    return f"{etichetta} {ditta}" if ditta else etichetta


def _riepilogo(dal: DAL, entita: Envelope | None) -> dict[str, Any] | None:
    """Le tre righe del mockup: ditta, importo, cantiere (più numero e data)."""
    if entita is None:
        return None
    return {
        "tipo": ETICHETTE_TIPO.get(entita.tipo, "Documento"),
        "ditta": _nome_fornitore(dal, entita.dati.get("fornitore_id")),
        "importo": entita.dati.get("totale"),
        "cantiere": nome_cantiere(dal, entita.dati.get("cantiere_id")),
        "numero": entita.dati.get("numero"),
        "data": entita.dati.get("data"),
    }


def _nome_fornitore(dal: DAL, fornitore_id: Any) -> str | None:
    if not fornitore_id:
        return None
    try:
        return str(dal.read("fornitore", str(fornitore_id)).dati.get("ragione_sociale"))
    except DalError:
        return None


def nome_cantiere(dal: DAL, cantiere_id: Any) -> str | None:
    if not cantiere_id:
        return None
    try:
        return str(dal.read("cantiere", str(cantiere_id)).dati.get("nome"))
    except DalError:
        return None


def _nota_sul_trace(dal: DAL, doc: Envelope, tipo: str, utente: Utente, **campi: Any) -> None:
    run_id = doc.dati.get("run_id")
    if not run_id:
        return
    percorso = appendi_feedback_operatore(
        dal.data_dir, run_id, tipo, utente.username, doc_id=doc.id, **campi
    )
    if percorso is not None:
        dal.commit_paths([percorso], f"trace {run_id}: feedback operatore [{run_id}]")
