"""Cruscotto admin (piano §3.4): aggregati di costo dalle viste DuckDB.

SQL scritto dal codice (fidato): niente guardrail, a differenza di ``/ask``.
Le viste rileggono i file a ogni query, quindi i numeri sono sempre freschi.
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import get_data_dir, richiedi_admin
from app.core.auth import Utente
from app.core.views import query

router = APIRouter(tags=["dashboard"])

SQL_TOTALI = """
SELECT COUNT(*)                                            AS n_fatture,
       COALESCE(SUM(totale), 0)                            AS totale,
       COALESCE(SUM(imponibile), 0)                        AS imponibile,
       COALESCE(SUM(iva), 0)                               AS iva,
       COALESCE(SUM(COALESCE(ritenuta_acconto, 0)), 0)     AS ritenute,
       COALESCE(SUM(CASE WHEN stato = 'bozza' THEN 1 ELSE 0 END), 0)   AS da_validare
FROM v_fatture
"""

SQL_PER_CANTIERE = """
SELECT c.id                       AS cantiere_id,
       c.nome                     AS cantiere,
       c.budget                   AS budget,
       COUNT(f.id)                AS n_fatture,
       COALESCE(SUM(f.totale), 0) AS speso
FROM v_cantieri c
LEFT JOIN v_fatture f ON f.cantiere_id = c.id
GROUP BY c.id, c.nome, c.budget
ORDER BY speso DESC
"""

SQL_PER_FORNITORE = """
SELECT f.fornitore_id            AS fornitore_id,
       fo.ragione_sociale        AS fornitore,
       COUNT(*)                  AS n_fatture,
       COALESCE(SUM(f.totale), 0) AS speso
FROM v_fatture f
LEFT JOIN v_fornitori fo ON fo.id = f.fornitore_id
GROUP BY f.fornitore_id, fo.ragione_sociale
ORDER BY speso DESC
LIMIT 8
"""


@router.get("/dashboard/costs")
def costi(
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> dict[str, Any]:
    """KPI globali + costo per cantiere (con scostamento sul budget) e per fornitore."""
    totali = query(data_dir, SQL_TOTALI)[0]
    per_cantiere = query(data_dir, SQL_PER_CANTIERE)
    for riga in per_cantiere:
        budget = riga.get("budget") or 0
        speso = riga.get("speso") or 0
        riga["residuo"] = round(budget - speso, 2) if budget else None
        riga["quota_budget"] = round(speso / budget, 4) if budget else None
    return {
        "totali": totali,
        "per_cantiere": per_cantiere,
        "per_fornitore": query(data_dir, SQL_PER_FORNITORE),
    }
