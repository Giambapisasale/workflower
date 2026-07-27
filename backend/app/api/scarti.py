"""Scarto di un inserimento sbagliato, e suo ripristino (solo ufficio).

Il bisogno è banale e mancava: una fattura letta male, un doppione, un documento
caricato per errore. Finora l'unica via era ``DELETE /api/entities/…`` — una
cancellazione secca, senza il perché e senza ritorno.

Scartare **non cancella**: l'entità si sposta in ``data/scartati/`` con motivo,
autore e data (``DAL.scarta``). Sparisce da conti, viste, coda di revisione e
report perché le viste globbano solo ``entities/``; resta dato versionato e
ripristinabile. Ogni passo è un commit git, come ogni mutazione.

Due guardie, in quest'ordine:

1. **nessuno la sta usando** — la stessa di :func:`api.entities.elimina`;
2. **non è già in contabilità** — se la fattura è arrivata in ERPNext va prima
   annullata *là*. Workflower lo **verifica in lettura** (``docstatus``) e blocca:
   scrivere annullamenti a valle resta fuori dai patti (ADR-4, sincronizzazione
   mono-direzionale che parte dalla validazione).
"""

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_dal, get_erp, richiedi_admin
from app.core.auth import Utente
from app.core.dal import DAL, ENTITY_TYPES, TIPI_INGRESSO, DalError, tipo_da_id
from app.core.erp import ErpClient, ErpError
from app.core.golden import carica_golden
from app.core.logbook import ottieni_logger
from app.core.riferimenti import messaggio_referenti, referenti
from app.models.envelope import Envelope

router = APIRouter(tags=["scarti"])

logger = ottieni_logger("revisione")

# Frappe: 0 = bozza (nessuna scrittura contabile, si elimina), 1 = confermato
# (è nei conti, si annulla), 2 = annullato.
DOCSTATUS_BOZZA = 0
DOCSTATUS_CONFERMATO = 1
DOCSTATUS_ANNULLATO = 2

# Cosa deve fare l'ufficio a valle, per stato del documento. Una bozza Frappe
# **non si annulla**: dire "annullala" manderebbe a cercare un pulsante che non
# c'è. Workflower crea i documenti come bozza, quindi è il caso normale.
ISTRUZIONE = {
    DOCSTATUS_BOZZA: "è ancora una bozza: eliminala in ERPNext",
    DOCSTATUS_CONFERMATO: "è confermata e sta nei conti: annullala in ERPNext (Cancel)",
}

# Il doctype a valle da controllare, per tipo di entità sincronizzabile.
DOCTYPE_ERP = {"fattura": "Purchase Invoice", "ddt": "Purchase Receipt"}


# ------------------------------------------------------------------ interni


def _entita(dal: DAL, entity_id: str) -> tuple[str, Envelope]:
    tipo = tipo_da_id(entity_id)
    if tipo is None:
        raise HTTPException(status_code=404, detail="entità non trovata")
    try:
        return tipo, dal.read(tipo, entity_id)
    except DalError as exc:
        raise HTTPException(status_code=404, detail="entità non trovata") from exc


def _blocco_contabilita(tipo: str, entita: Envelope, erp: ErpClient) -> str | None:
    """La ragione per cui questo documento non si può scartare adesso, o ``None``.

    Se non è mai arrivato a valle non c'è nulla da controllare. Se è arrivato,
    l'unica risposta accettabile è "là è già annullato": scartarlo qui e lasciarlo
    vivo in contabilità significherebbe due verità in disaccordo, e il disaccordo
    lo scoprirebbe il commercialista.
    """
    erp_id = entita.meta.erp_id
    if not erp_id:
        return None
    doctype = DOCTYPE_ERP.get(tipo)
    if doctype is None:
        return None
    if not erp.attivo():
        return (
            f"Questo documento è già arrivato in contabilità come {erp_id}, ma "
            "l'integrazione contabile adesso è spenta: non posso verificare se è "
            "stato annullato. Riattivala e riprova."
        )
    try:
        corpo = erp.richiesta("GET", f"/api/resource/{doctype}/{quote(erp_id)}")
    except ErpError as exc:
        if exc.stato == 404:
            return None  # a valle non c'è più: niente da annullare
        return (
            f"Non riesco a verificare la contabilità adesso ({exc}). Il documento è "
            f"già arrivato a valle come {erp_id}: riprova quando l'ERP risponde."
        )
    documento = corpo.get("data", corpo) if isinstance(corpo, dict) else {}
    docstatus = int(documento.get("docstatus") or 0)
    if docstatus == DOCSTATUS_ANNULLATO:
        return None
    cosa_fare = ISTRUZIONE.get(docstatus, "sistemala prima in ERPNext")
    return (
        f"Questo documento è già arrivato in contabilità come {erp_id} ({doctype}): "
        f"{cosa_fare}, poi torna qui a scartarlo. Finché esiste a valle, scartarlo qui "
        "lascerebbe due verità in disaccordo."
    )


def _scollega_documento(dal: DAL, entity_id: str, attore: str) -> None:
    """Il documento dell'operatore deve dire la verità: quell'inserimento non c'è più.

    Senza questo, il fascicolo continuerebbe a mostrare il semaforo verde e
    "Tutto a posto" per una fattura che l'ufficio ha ripudiato.
    """
    for doc in dal.list_all("documento"):
        if doc.dati.get("entity_id") != entity_id:
            continue
        doc.dati["entity_id"] = None
        doc.dati["entity_tipo"] = None
        doc.dati["esito"] = "scartato"
        doc.dati["richiede_revisione"] = False
        doc.stato = "errore" if doc.stato == "errore" else "bozza"
        dal.update(doc, run_id=f"manual:{attore}")


def _togli_dal_golden(dal: DAL, entity_id: str, attore: str) -> list[str]:
    """Toglie i casi golden nati da quell'entità: l'ufficio ne ha ripudiato il dato.

    Lasciarli significherebbe misurare ogni nuova versione del workflow contro una
    risposta considerata sbagliata — il replay direbbe "regressione" a un
    miglioramento vero.
    """
    rimossi = []
    for caso in carica_golden(dal.data_dir):
        if caso.entity_id == entity_id and dal.elimina_golden(
            caso.id, eliminato_da=f"manual:{attore}"
        ):
            rimossi.append(caso.id)
    return rimossi


def _chiudi_segnalazioni(dal: DAL, entity_id: str, run_id: str | None) -> list[str]:
    """Chiude le segnalazioni aperte sul documento scartato: non c'è più cosa fare."""
    chiuse = []
    for issue in dal.list_issues():
        if issue.stato != "aperta":
            continue
        if issue.entity_id == entity_id or (run_id and issue.run_id == run_id):
            try:
                dal.chiudi_issue(issue.id, run_id=run_id)
            except DalError:
                continue
            chiuse.append(issue.id)
    return chiuse


def _vista_scartato(entita: Envelope) -> dict[str, Any]:
    return {
        "id": entita.id,
        "tipo": entita.tipo,
        "etichetta": ENTITY_TYPES[entita.tipo]["etichetta"],
        "titolo": entita.dati.get("numero") or entita.dati.get("data"),
        "motivo": entita.meta.motivo_scarto,
        "scartato_da": entita.meta.scartato_da,
        "scartato_il": entita.meta.scartato_il,
        "era_validato": bool(entita.meta.validato_da),
        "erp_id": entita.meta.erp_id,
    }


# ------------------------------------------------------------------ endpoint


class ScartoRichiesta(BaseModel):
    motivo: str = Field(min_length=1)


@router.post("/review/{entity_id}/scarta")
def scarta(
    entity_id: str,
    body: ScartoRichiesta,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
    erp: ErpClient = Depends(get_erp),
) -> dict[str, Any]:
    """Ripudia un inserimento: esce dai conti, resta ripristinabile."""
    motivo = body.motivo.strip()
    if not motivo:
        raise HTTPException(status_code=422, detail="serve un motivo per lo scarto")
    tipo, entita = _entita(dal, entity_id)
    if tipo not in TIPI_INGRESSO:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{ENTITY_TYPES[tipo]['etichetta']} non è un documento in arrivo: "
                "le anagrafiche si correggono o si eliminano da Dati."
            ),
        )
    usato_da = referenti(dal, tipo, entity_id)
    if usato_da:
        raise HTTPException(status_code=409, detail=messaggio_referenti(tipo, entity_id, usato_da))
    blocco = _blocco_contabilita(tipo, entita, erp)
    if blocco:
        raise HTTPException(status_code=409, detail=blocco)

    run_id = entita.meta.run_id
    golden = _togli_dal_golden(dal, entity_id, admin.username)
    _scollega_documento(dal, entity_id, admin.username)
    issue_chiuse = _chiudi_segnalazioni(dal, entity_id, run_id)
    dal.scarta(tipo, entity_id, motivo=motivo, scartato_da=admin.username)
    logger.info(
        "%s %s scartato da %s: %s",
        tipo,
        entity_id,
        admin.username,
        motivo,
        extra={"entity_id": entity_id, "run_id": run_id},
    )
    return {
        "id": entity_id,
        "stato": "scartato",
        "golden_rimossi": golden,
        "segnalazioni_chiuse": issue_chiuse,
    }


@router.get("/scartati")
def elenco_scartati(
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Gli inserimenti scartati, dal più recente: l'archivio da cui si ripristina."""
    scartati = dal.list_scartati()
    scartati.sort(key=lambda e: e.meta.scartato_il or "", reverse=True)
    return {"scartati": [_vista_scartato(e) for e in scartati]}


@router.post("/scartati/{entity_id}/ripristina")
def ripristina(
    entity_id: str,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Rimette un inserimento al suo posto, come era prima dello scarto.

    Non ricrea il caso golden né riapre le segnalazioni: il primo si rifà
    validando, le seconde erano state chiuse con una decisione umana.
    """
    tipo = tipo_da_id(entity_id)
    if tipo is None:
        raise HTTPException(status_code=404, detail="entità non trovata")
    try:
        entita = dal.ripristina(tipo, entity_id, ripristinato_da=admin.username)
    except DalError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    logger.info(
        "%s %s ripristinato da %s",
        tipo,
        entity_id,
        admin.username,
        extra={"entity_id": entity_id},
    )
    return {"id": entita.id, "stato": entita.stato}
