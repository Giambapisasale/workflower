"""Log & Dataset + Skills & Tools admin (piano §M6, §3.6/§3.7).

Osservabilità (conteggi, costi, fingerprint query) e la materia prima del tier
locale: le tool call dei run validati diventano esempi per il fine-tuning
(FunctionGemma). Il registro dei tool mostra i contatori d'uso e i candidati al
consolidamento — nessun Toolsmith automatico in v1 (non-goal §5).
"""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from app.api.deps import get_dal, get_data_dir, richiedi_admin
from app.core.auth import Utente
from app.core.dal import DAL
from app.core.dataset import (
    conteggio_fingerprint,
    conteggio_tool,
    esempi_finetuning,
    statistiche,
)
from app.core.tools import Toolset

router = APIRouter(tags=["dataset"])

NDJSON = "application/x-ndjson"


@router.get("/dataset/stats")
def stats(
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    dati = statistiche(dal.data_dir)
    dati["esempi_finetuning"] = sum(1 for _ in esempi_finetuning(dal))
    return dati


@router.get("/dataset/queries")
def queries(
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> dict[str, Any]:
    """Le query di ``/ask`` per fingerprint: i duplicati sono candidati a tool (§3.6)."""
    return {"gruppi": conteggio_fingerprint(data_dir)}


@router.get("/dataset/export")
def export(
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> FileResponse:
    """Scarica ``dataset/toolcalls.jsonl`` (tutte le tool call grezze)."""
    percorso = Path(data_dir) / "dataset" / "toolcalls.jsonl"
    if not percorso.is_file():
        raise HTTPException(status_code=404, detail="dataset non ancora disponibile")
    return FileResponse(
        percorso, media_type=NDJSON, filename="toolcalls.jsonl"
    )


@router.get("/dataset/finetuning.jsonl")
def finetuning(
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> Response:
    """Esempi per il fine-tuning: solo le tool call dei run validati (§3.7)."""
    linee = [json.dumps(esempio, ensure_ascii=False) for esempio in esempi_finetuning(dal)]
    contenuto = "\n".join(linee) + ("\n" if linee else "")
    return Response(
        content=contenuto,
        media_type=NDJSON,
        headers={"Content-Disposition": 'attachment; filename="finetuning.jsonl"'},
    )


@router.get("/tools")
def elenco_tool(
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Registry dei tool nativi con i contatori d'uso + i candidati al consolidamento."""
    usi = conteggio_tool(dal.data_dir)
    tools = [
        {**voce, "usi": usi.get(voce["name"], 0), "ciclo": "consolidata"}
        for voce in Toolset(dal).elenco()
    ]
    tools.sort(key=lambda t: t["usi"], reverse=True)
    return {"tools": tools, "candidati": conteggio_fingerprint(dal.data_dir)}
