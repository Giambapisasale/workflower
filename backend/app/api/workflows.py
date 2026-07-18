"""Workflows admin (piano §3.4): manifest, versioni, statistiche run, trace.

L'Improver (avvio patch, approva/rifiuta) vive nello stesso router: vedi
la sezione aggiunta in M5.
"""

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_data_dir, richiedi_admin
from app.core.auth import Utente
from app.core.golden import carica_golden
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
