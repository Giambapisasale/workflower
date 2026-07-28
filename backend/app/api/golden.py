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
from pydantic import BaseModel

from app.api.deps import get_dal, get_data_dir, richiedi_admin
from app.core.auth import Utente
from app.core.dal import DAL
from app.core.golden import carica_golden
from app.core.interroga import InterrogaError, applica_guardrail, esegui_query

router = APIRouter(tags=["golden"])


class DomandaGolden(BaseModel):
    """Una domanda e la query che l'ufficio ha riconosciuto come giusta."""

    domanda: str
    sql: str
    run_id: str | None = None


@router.get("/golden")
def elenco(
    workflow: str | None = Query(default=None),
    tipo: str | None = Query(default=None, pattern="^(documento|domanda)$"),
    _admin: Utente = Depends(richiedi_admin),
    data_dir: Path = Depends(get_data_dir),
) -> dict[str, Any]:
    """I casi golden, opzionalmente di un workflow o di un tipo (senza l'atteso).

    L'``atteso`` integrale è il dato validato dell'entità e in elenco sarebbe
    rumore: qui bastano l'origine del caso e quanti campi copre.

    Il filtro per ``tipo`` serve perché i due tipi si rivedono separatamente: un
    caso-documento si giudica guardando il PDF, un caso-domanda rileggendo la query.
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


@router.post("/golden/domande", status_code=201)
def crea_domanda(
    body: DomandaGolden,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Promuove una domanda e la sua query a caso di regressione (§3.6).

    È il passo di approvazione umana del ciclo sull'interrogazione: l'ufficio pone
    la domanda in modalità admin, vede la query e le righe, e se sono giuste le
    fissa qui. Il server non si fida della query ricevuta: riapplica i guardrail
    di ``/ask`` e la **esegue**. Due rifiuti espliciti, perché un caso golden
    sbagliato è peggio di un caso in meno:

    - query che non passa i guardrail o non gira → 400;
    - query che non restituisce **nessuna riga** → 400: un riferimento vuoto lo
      pareggerebbe qualunque candidato muto, e il gate T3 diventerebbe un regalo.
    """
    try:
        sql = applica_guardrail(body.sql)
        righe = esegui_query(dal.data_dir, sql)
    except InterrogaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not righe:
        raise HTTPException(
            status_code=400,
            detail=(
                "la query non restituisce righe: come riferimento non "
                "distinguerebbe un modello bravo da uno muto"
            ),
        )
    caso = dal.crea_golden_domanda(
        body.domanda, sql, run_id=body.run_id, validato_da=admin.username
    )
    return {**caso, "righe": len(righe)}


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
