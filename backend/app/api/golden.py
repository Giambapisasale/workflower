"""Golden set: elenco e rimozione dei casi di regressione (solo ufficio).

Il golden set è la rete che impedisce all'Improver di «correggere un errore
introducendone tre»: ogni patch viene rigiocata su questi casi prima di essere
proposta. Finora era scrivibile (validando una bozza) ma non ispezionabile né
correggibile: un caso costruito su un dato poi ripudiato restava dentro per
sempre, e faceva sembrare regressione ogni miglioramento vero.

Le letture stanno in ``core/golden.py``; la rimozione passa dal DAL, come ogni
mutazione di ``data/``.
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_dal, get_data_dir, richiedi_admin
from app.core.auth import Utente
from app.core.dal import DAL
from app.core.golden import carica_golden

router = APIRouter(tags=["golden"])


@router.get("/golden")
def elenco(
    workflow: str | None = Query(default=None),
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> dict[str, Any]:
    """I casi golden, opzionalmente di un solo workflow (senza l'atteso completo).

    L'``atteso`` integrale è il dato validato dell'entità e in elenco sarebbe
    rumore: qui bastano l'origine del caso e quanti campi copre.
    """
    casi = []
    for caso in carica_golden(data_dir, workflow):
        casi.append(
            {
                "id": caso.id,
                "workflow": caso.workflow,
                "version": caso.version,
                "doc": caso.doc,
                "entity_tipo": caso.entity_tipo,
                "entity_id": caso.entity_id,
                "run_id": caso.run_id,
                "validato_da": caso.validato_da,
                "creato": caso.creato,
                "n_campi": len(caso.atteso),
                "originale_presente": (Path(data_dir) / caso.doc).is_file(),
            }
        )
    return {"golden": casi}


@router.delete("/golden/{golden_id}")
def elimina(
    golden_id: str,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, str]:
    """Toglie un caso dalla rete di regressione (commit git, reversibile)."""
    if not dal.elimina_golden(golden_id, eliminato_da=f"manual:{admin.username}"):
        raise HTTPException(status_code=404, detail=f"caso golden non trovato: {golden_id}")
    return {"rimosso": golden_id}
