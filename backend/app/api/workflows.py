"""Workflows admin (piano §3.4): manifest, versioni, statistiche, trace, Improver.

Ciclo di §3.5: ``/improve`` genera una patch (con replay sul golden set),
``/patches/{id}/approve`` la applica (bump di versione + commit) e riesegue il
documento d'origine con la nuova skill; ``/reject`` la archivia.
"""

import contextlib
import uuid
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_dal, get_data_dir, get_improver, richiedi_admin
from app.core.auth import Utente
from app.core.dal import DAL, DalError, tipo_da_id
from app.core.golden import carica_golden
from app.core.improver import Improver, ImproverError
from app.core.runtime import RunResult, WorkflowRuntime
from app.core.tracer import leggi_eventi, statistiche_run

router = APIRouter(tags=["workflows"])


@router.get("/workflows")
def elenco_workflows(
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> dict[str, Any]:
    """Elenco dei workflow con versione, tier, passi e statistiche dei run."""
    stats = statistiche_run(data_dir)
    workflows = []
    for manifest_path in sorted((Path(data_dir) / "workflows").glob("*/manifest.yaml")):
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        nome = manifest.get("name", manifest_path.parent.name)
        passi = [s.get("id") for s in manifest.get("steps", []) if isinstance(s, dict)]
        workflows.append(
            {
                "name": nome,
                "version": str(manifest.get("version", "?")),
                "tier": manifest.get("tier"),
                "steps": passi,
                "confidence_threshold": manifest.get("confidence_threshold"),
                "stats": stats.get(nome, {"totale": 0, "ok": 0, "errore": 0}),
                "golden": len(carica_golden(data_dir, nome)),
            }
        )
    return {"workflows": workflows}


@router.get("/runs/{run_id}/trace")
def trace_run(
    run_id: str,
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> dict[str, Any]:
    """Il trace completo di un run (solo admin, §3.4)."""
    eventi = leggi_eventi(data_dir, run_id)
    if not eventi:
        raise HTTPException(status_code=404, detail="trace non trovato")
    return {"run_id": run_id, "eventi": eventi}


# ------------------------------------------------------------------ Improver


class ImproveRichiesta(BaseModel):
    run_id: str | None = None
    issue_id: str | None = None
    feedback: str | None = None


def _vista_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """La patch senza il testo integrale della skill nuova (resta il diff)."""
    return {k: v for k, v in patch.items() if k != "skill_nuova"}


@router.post("/workflows/{name}/improve")
def migliora(
    name: str,
    body: ImproveRichiesta,
    _admin: Utente = Depends(richiedi_admin),
    improver: Improver = Depends(get_improver),
) -> dict[str, Any]:
    """Avvia l'Improver: proposta di patch + replay sul golden set."""
    try:
        patch = improver.proponi(
            name, run_id=body.run_id, issue_id=body.issue_id, feedback=body.feedback
        )
    except ImproverError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DalError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _vista_patch(patch)


@router.get("/patches")
def elenco_patches(
    stato: str | None = Query(default=None),
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    patches = dal.list_patches()
    if stato:
        patches = [p for p in patches if p.get("stato") == stato]
    patches.sort(key=lambda p: p.get("creato") or "", reverse=True)
    return {"patches": [_vista_patch(p) for p in patches]}


@router.get("/patches/{patch_id}")
def dettaglio_patch(
    patch_id: str,
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    try:
        return _vista_patch(dal.leggi_patch(patch_id))
    except DalError as exc:
        raise HTTPException(status_code=404, detail="patch non trovata") from exc


@router.post("/patches/{patch_id}/approve")
def approva(
    patch_id: str,
    admin: Utente = Depends(richiedi_admin),
    improver: Improver = Depends(get_improver),
) -> dict[str, Any]:
    """Applica la patch (bump versione + commit) e riesegue il documento d'origine."""
    patch = _patch_da_decidere(improver.dal, patch_id)
    patch = improver.applica(patch, admin.username)
    return {
        "patch": _vista_patch(patch),
        "versione": patch["a_versione"],
        "rerun": _riprocessa_origine(improver, patch),
    }


@router.post("/patches/{patch_id}/reject")
def rifiuta(
    patch_id: str,
    admin: Utente = Depends(richiedi_admin),
    improver: Improver = Depends(get_improver),
) -> dict[str, Any]:
    patch = improver.rifiuta(_patch_da_decidere(improver.dal, patch_id), admin.username)
    return {"id": patch["id"], "stato": patch["stato"]}


# ------------------------------------------------------------------ interni


def _patch_da_decidere(dal: DAL, patch_id: str) -> dict[str, Any]:
    try:
        patch = dal.leggi_patch(patch_id)
    except DalError as exc:
        raise HTTPException(status_code=404, detail="patch non trovata") from exc
    if patch.get("stato") != "proposta":
        raise HTTPException(status_code=409, detail=f"patch già {patch.get('stato')}")
    return patch


def _riprocessa_origine(improver: Improver, patch: dict[str, Any]) -> dict[str, Any] | None:
    """Riesegue il documento d'origine con la nuova versione e ne aggiorna lo stato."""
    dal = improver.dal
    origine = patch.get("origine") or {}
    doc = origine.get("doc")
    if not doc or not (dal.data_dir / doc).is_file():
        return None
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    esito = WorkflowRuntime(dal, improver.gateway).esegui(patch["workflow"], doc, run_id=run_id)
    _ripunta_documento(dal, origine.get("run_id"), esito)
    if origine.get("issue_id"):
        with contextlib.suppress(DalError):
            dal.chiudi_issue(origine["issue_id"], run_id=esito.run_id)
    ritenuta = None
    if esito.entity_id:
        with contextlib.suppress(DalError):
            entita = dal.read(tipo_da_id(esito.entity_id) or "fattura", esito.entity_id)
            ritenuta = entita.dati.get("ritenuta_acconto")
    return {
        "run_id": esito.run_id,
        "entity_id": esito.entity_id,
        "esito": esito.esito,
        "ritenuta": ritenuta,
    }


def _ripunta_documento(dal: DAL, run_id_origine: str | None, esito: RunResult) -> None:
    if not run_id_origine:
        return
    for documento in dal.list_all("documento"):
        if documento.dati.get("run_id") != run_id_origine:
            continue
        documento.dati.update(
            {
                "run_id": esito.run_id,
                "esito": esito.esito,
                "entity_id": esito.entity_id,
                "entity_tipo": tipo_da_id(esito.entity_id),
                "richiede_revisione": esito.richiede_revisione,
            }
        )
        documento.stato = "errore" if esito.esito == "errore" else "bozza"
        with contextlib.suppress(DalError):
            dal.update(documento, run_id=esito.run_id)
        return
