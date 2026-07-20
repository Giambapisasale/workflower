"""Registro di cantiere (Fase 2, M10): il fascicolo consolidato di un cantiere.

Mette in un'unica vista tutto ciò che ruota attorno a un cantiere — fatture, DDT,
ore di manodopera, SAL, scostamento sul computo — dai file JSON via DuckDB. È il
"registro che si aggiorna da solo" (§3.8): ogni documento validato ci confluisce
senza codice nuovo. Sola lettura, riservato all'ufficio (admin).
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_data_dir, richiedi_admin
from app.core.auth import Utente
from app.core.views import query

router = APIRouter(tags=["cantieri"])

SQL_FATTURE = """
SELECT f.id, f.numero, f.data, f.totale, f.stato, fo.ragione_sociale AS fornitore
FROM v_fatture f
LEFT JOIN v_fornitori fo ON fo.id = f.fornitore_id
WHERE f.cantiere_id = ?
ORDER BY f.data DESC
"""

SQL_DDT = """
SELECT d.id, d.numero, d.data, d.n_righe, d.stato, fo.ragione_sociale AS fornitore
FROM v_ddt d
LEFT JOIN v_fornitori fo ON fo.id = d.fornitore_id
WHERE d.cantiere_id = ?
ORDER BY d.data DESC
"""

SQL_SAL = """
SELECT id, numero, data, importo_progressivo, percentuale_avanzamento, stato
FROM v_sal WHERE cantiere_id = ? ORDER BY data DESC
"""

SQL_ORE = """
SELECT COALESCE(SUM(ore), 0)                 AS ore_totali,
       COALESCE(SUM(costo), 0)               AS costo_manodopera,
       COUNT(DISTINCT rapportino_id)         AS giornate
FROM v_rapportini_righe WHERE cantiere_id = ?
"""

SQL_POZZETTI = """
SELECT id, codice, tipo, ubicazione, stato_manufatto, data_installazione
FROM v_pozzetti WHERE cantiere_id = ? ORDER BY codice
"""

SQL_CRONO = """
SELECT descrizione, inizio_previsto, fine_prevista
FROM v_cronoprogramma_voci WHERE cantiere_id = ? ORDER BY inizio_previsto
"""


def _uno(righe: list[dict[str, Any]]) -> dict[str, Any] | None:
    return righe[0] if righe else None


@router.get("/cantieri/{cantiere_id}/registro")
def registro(
    cantiere_id: str,
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> dict[str, Any]:
    """Fascicolo del cantiere: anagrafica + spesa, ore, avanzamento, scostamento."""
    cantiere = _uno(query(data_dir, "SELECT * FROM v_cantieri WHERE id = ?", [cantiere_id]))
    if cantiere is None:
        raise HTTPException(status_code=404, detail="cantiere non trovato")

    fatture = query(data_dir, SQL_FATTURE, [cantiere_id])
    ore = query(data_dir, SQL_ORE, [cantiere_id])[0]
    sal = query(data_dir, SQL_SAL, [cantiere_id])
    scostamento = _uno(
        query(data_dir, "SELECT * FROM v_cantiere_scostamento WHERE cantiere_id = ?", [cantiere_id])
    )
    # Registri automatici (M21): si popolano dalle entità e si aggiornano a ogni documento.
    pozzetti = query(data_dir, SQL_POZZETTI, [cantiere_id])
    pozzetti_riepilogo = _uno(
        query(data_dir, "SELECT * FROM v_pozzetti_riepilogo WHERE cantiere_id = ?", [cantiere_id])
    )
    cronoprogramma = _uno(
        query(data_dir, "SELECT * FROM v_cronoprogramma WHERE cantiere_id = ?", [cantiere_id])
    )
    speso = sum(f.get("totale") or 0 for f in fatture)
    budget = cantiere.get("budget") or 0
    return {
        "cantiere": cantiere,
        "totali": {
            "speso_fatture": round(speso, 2),
            "n_fatture": len(fatture),
            "budget": budget,
            "quota_budget": round(speso / budget, 4) if budget else None,
            "ore_totali": ore.get("ore_totali"),
            "costo_manodopera": ore.get("costo_manodopera"),
            "giornate": ore.get("giornate"),
            "avanzamento": sal[0]["percentuale_avanzamento"] if sal else None,
            "scostamento": scostamento,
            "cronoprogramma": cronoprogramma,
            "pozzetti": pozzetti_riepilogo,
        },
        "fatture": fatture,
        "ddt": query(data_dir, SQL_DDT, [cantiere_id]),
        "sal": sal,
        "pozzetti": pozzetti,
        "cronoprogramma": query(data_dir, SQL_CRONO, [cantiere_id]),
    }
