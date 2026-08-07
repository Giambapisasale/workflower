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
    tipo: str | None = Query(default=None, pattern="^(documento|legacy_sql)$"),
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> dict[str, Any]:
    """I casi golden, opzionalmente di un workflow o di un tipo (senza l'atteso).

    L'``atteso`` integrale è il dato validato dell'entità e in elenco sarebbe
    rumore: qui bastano l'origine del caso e quanti campi copre.

    Il filtro per ``tipo`` serve perché i due tipi si rivedono separatamente.
    I casi storici sono etichettati ``legacy_sql`` ma non espongono la loro
    implementazione.
    """
    casi = []
    for caso in carica_golden(data_dir, workflow, tipo=tipo):
        casi.append(
            {
                "id": caso.id,
                "tipo": caso.tipo,
                "workflow": caso.workflow,
                "version": caso.version,
                "doc": caso.doc,
                "domanda": caso.domanda,
                "entity_tipo": caso.entity_tipo,
                "entity_id": caso.entity_id,
                "run_id": caso.run_id,
                "validato_da": caso.validato_da,
                "creato": caso.creato,
                "n_campi": len(caso.atteso),
                # un caso-domanda non ha un originale su disco: l'input è il testo
                "originale_presente": (
                    (Path(data_dir) / caso.doc).is_file() if caso.doc else True
                ),
            }
        )
    return {"golden": casi}


@router.post("/golden/domande")
def crea_domanda(
    _admin: Utente = Depends(richiedi_admin),
) -> dict[str, Any]:
    """Compatibilità esplicita: la creazione dei golden storici è ritirata."""
    raise HTTPException(
        status_code=410,
        detail="golden storici ritirati: gli oracoli dell'agente sono approvati dall'evoluzione",
    )


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
