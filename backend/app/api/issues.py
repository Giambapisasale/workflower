"""Coda segnalazioni admin (piano §3.4): i "qualcosa non torna" e gli errori auto.

Ogni segnalazione porta con sé i riferimenti per intervenire: il run (trace),
il documento e l'entità estratta. Da qui l'admin apre la revisione o avvia
l'Improver (§3.5).
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_dal, richiedi_admin
from app.core.auth import Utente
from app.core.dal import DAL, DalError, tipo_da_id

router = APIRouter(tags=["issues"])


def _riepilogo_entita(dal: DAL, entity_id: str | None) -> dict[str, Any] | None:
    tipo = tipo_da_id(entity_id)
    if tipo is None or entity_id is None:
        return None
    try:
        entita = dal.read(tipo, entity_id)
    except DalError:
        return None
    riepilogo: dict[str, Any] = {"tipo": tipo, "id": entita.id, "stato": entita.stato}
    if tipo == "fattura":
        riepilogo["totale"] = entita.dati.get("totale")
        forn = entita.dati.get("fornitore_id")
        if forn:
            try:
                anagrafica = dal.read("fornitore", str(forn))
                riepilogo["fornitore"] = anagrafica.dati.get("ragione_sociale")
            except DalError:
                riepilogo["fornitore"] = None
    return riepilogo


def _vista(dal: DAL, issue: Any) -> dict[str, Any]:
    dati = issue.model_dump(mode="json")
    dati["entita"] = _riepilogo_entita(dal, issue.entity_id)
    return dati


@router.get("/issues")
def elenco_issues(
    stato: str | None = Query(default=None),
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Segnalazioni ordinate: aperte prima, più recenti in cima."""
    issues = dal.list_issues()
    if stato in ("aperta", "chiusa"):
        issues = [i for i in issues if i.stato == stato]
    issues.sort(key=lambda i: i.created or "", reverse=True)
    issues.sort(key=lambda i: i.stato == "chiusa")  # ordinamento stabile: aperte prima
    return {"issues": [_vista(dal, i) for i in issues]}


@router.post("/issues/{issue_id}/close")
def chiudi(
    issue_id: str,
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    try:
        issue = dal.chiudi_issue(issue_id)
    except DalError as exc:
        raise HTTPException(status_code=404, detail="segnalazione non trovata") from exc
    return {"id": issue.id, "stato": issue.stato}
