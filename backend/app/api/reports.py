"""Report Excel (Fase 2, M11): scarica un .xlsx generato dalle viste DuckDB."""

from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.api.deps import get_data_dir, richiedi_admin
from app.core.auth import Utente
from app.core.report import genera_report

router = APIRouter(tags=["reports"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/reports/mensile.xlsx")
def report_mensile(
    cantiere_id: str | None = Query(default=None),
    anno: int | None = Query(default=None),
    mese: int | None = Query(default=None, ge=1, le=12),
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> Response:
    """Report .xlsx (riepilogo + fatture/DDT/ore/SAL/scostamento), filtrabile."""
    contenuto = genera_report(data_dir, cantiere_id=cantiere_id, anno=anno, mese=mese)
    suffisso_mese = f"-{mese:02d}" if mese else ""
    nome = f"report-{cantiere_id or 'tutti'}-{anno or 'tutto'}{suffisso_mese}.xlsx"
    return Response(
        content=contenuto,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
