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

from app.api.deps import (
    get_dal,
    get_data_dir,
    get_docling,
    get_eval_interroga,
    get_eval_t3,
    richiedi_admin,
)
from app.core.auth import Utente
from app.core.dal import DAL, CatalogoNonValido
from app.core.dataset import (
    conteggio_fingerprint,
    conteggio_tool,
    esempi_finetuning,
    fingerprint,
    statistiche,
)
from app.core.docling import DoclingClient
from app.core.eval_agente import EvalAgente
from app.core.eval_t3 import EvalT3
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
    """Conteggi dell'archivio storico, senza testo o struttura delle query."""
    return {
        "gruppi": [
            {"fingerprint": g["fingerprint"], "conteggio": g["conteggio"], "archivio": True}
            for g in conteggio_fingerprint(data_dir)
        ]
    }


@router.post("/dataset/consolida")
def consolida(
    _admin: Utente = Depends(richiedi_admin),
) -> dict[str, Any]:
    """Compatibilità esplicita: la promozione dal catalogo storico è ritirata."""
    raise HTTPException(status_code=410, detail="promozione storica ritirata: usa Evoluzione agente")


@router.post("/dataset/consolida-tool")
def consolida_tool(
    _admin: Utente = Depends(richiedi_admin),
) -> dict[str, Any]:
    """Compatibilità esplicita: la promozione dal catalogo storico è ritirata."""
    raise HTTPException(status_code=410, detail="promozione storica ritirata: usa Evoluzione agente")


@router.delete("/dataset/tool/{macro}")
def rimuovi_tool(
    macro: str,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, str]:
    """Rimuove un tool parametrico ``t_*``. Il candidato torna libero (ri-consolidabile)."""
    try:
        rimosso = dal.elimina_tool(macro=macro, eliminato_da=admin.username)
    except CatalogoNonValido as exc:
        raise HTTPException(status_code=409, detail=f"impossibile rimuovere: {exc}") from exc
    if not rimosso:
        raise HTTPException(status_code=404, detail=f"tool non trovato: {macro}")
    return {"rimosso": macro}


@router.delete("/dataset/pytool/{nome}")
def rimuovi_pytool(
    nome: str,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, str]:
    """Rimuove un tool Python consolidato (M15): sorgente + riga di ledger.

    I tool Python sono indipendenti: la rimozione non può rompere il catalogo.
    Con il tool tolto, il candidato torna libero e può essere ri-consolidato.
    """
    if not dal.elimina_pytool(nome=nome, eliminato_da=admin.username):
        raise HTTPException(status_code=404, detail=f"tool non trovato: {nome}")
    return {"rimosso": nome}


@router.delete("/dataset/vista/{vista}")
def rimuovi_vista(
    vista: str,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, str]:
    """Rimuove una vista consolidata ``v_*`` (solo se nulla vi dipende)."""
    try:
        rimosso = dal.elimina_vista(vista=vista, eliminato_da=admin.username)
    except CatalogoNonValido as exc:
        raise HTTPException(status_code=409, detail=f"impossibile rimuovere: {exc}") from exc
    if not rimosso:
        raise HTTPException(status_code=404, detail=f"vista non trovata: {vista}")
    return {"rimosso": vista}


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


@router.get("/dataset/eval-t3")
def eval_t3(
    candidato: str = "T3",
    riferimento: str = "T1",
    _admin: Utente = Depends(richiedi_admin),
    valutatore: EvalT3 = Depends(get_eval_t3),
    valutatore_domande: EvalAgente = Depends(get_eval_interroga),
) -> dict[str, Any]:
    """Valuta un modello candidato T3 sul set validato (M18): accuratezza vs T1.

    Due misure distinte in un solo verdetto, perché il prodotto ha due compiti:

    - **documenti**: rigioca gli esempi validati e misura la function-calling
      accuracy (tool giusto, argomenti giusti);
    - **interrogazione**: rigioca i casi-domanda del golden set e confronta le
      righe con quelle della query approvata (``interrogazione``).

    ``pronti`` e ``regressioni`` restano l'unico posto da leggere per decidere
    cosa instradare. Nessun training: solo misura (il candidato è
    ``LLM_<tier>_MODEL``).
    """
    documenti = valutatore.valuta(candidato=candidato, riferimento=riferimento)
    agente = valutatore_domande.valuta(candidato=candidato, riferimento=riferimento)
    unito = {**documenti, "agente_dati": agente}
    if agente.get("pronto_per_t3"):
        unito["pronti"] = [*documenti.get("pronti", []), "interroga"]
    if agente.get("regressione"):
        unito["regressioni"] = [*documenti.get("regressioni", []), "interroga"]
    return unito


@router.get("/tools")
def elenco_tool(
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
    docling: DoclingClient = Depends(get_docling),
) -> dict[str, Any]:
    """Registry dei tool nativi con i contatori d'uso + i candidati al consolidamento."""
    usi = conteggio_tool(dal.data_dir)
    # Stesso ``Toolset`` che vede il runtime, sidecar compreso: la pagina deve
    # mostrare i tool che il modello può davvero chiamare su *questa* macchina,
    # non un elenco teorico.
    # ``elenco()`` porta già ciclo e origine (nativa | pytool): non li sovrascriviamo,
    # così i tool Python consolidati compaiono col loro stato di ciclo reale (M15).
    tools = [
        {**voce, "usi": usi.get(voce["name"], 0)}
        for voce in Toolset(dal, docling=docling).elenco()
    ]
    tools.sort(key=lambda t: t["usi"], reverse=True)
    return {
        "tools": tools,
        # Le strutture SQL restano archivio interno e non fanno piu' parte del
        # contratto amministrativo dell'agente.
        "candidati": [],
        "viste": [],
        "macro": [],
    }
