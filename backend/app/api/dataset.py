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
from pydantic import BaseModel

from app.api.deps import get_dal, get_data_dir, get_eval_t3, richiedi_admin
from app.core.auth import Utente
from app.core.consolida import (
    ConsolidaError,
    consolidati_per_fingerprint,
    corpo_vista,
    leggi_consolidamenti,
    leggi_tool,
    letterali,
    prepara,
    prepara_tool,
)
from app.core.dal import DAL, CatalogoNonValido
from app.core.dataset import (
    conteggio_fingerprint,
    conteggio_tool,
    esempi_finetuning,
    statistiche,
)
from app.core.eval_t3 import EvalT3
from app.core.tools import Toolset


def _candidati(data_dir: Path) -> list[dict[str, Any]]:
    """I gruppi per fingerprint, marcati con l'artefatto se già consolidato.

    Ogni gruppo porta i ``letterali`` del suo esempio: sono i valori che
    l'ufficio può rendere parametri quando promuove la query a tool.
    """
    consolidati = consolidati_per_fingerprint(data_dir)
    return [
        {
            **gruppo,
            "consolidato": consolidati.get(gruppo["fingerprint"]),
            "letterali": letterali(corpo_vista(gruppo["esempio"])),
        }
        for gruppo in conteggio_fingerprint(data_dir)
    ]

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
    return {"gruppi": _candidati(data_dir)}


class ConsolidaRichiesta(BaseModel):
    fingerprint: str
    nome: str


@router.post("/dataset/consolida")
def consolida(
    body: ConsolidaRichiesta,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Promuove un candidato ricorrente a vista ``v_<nome>`` (§3.6, branca "vista SQL").

    Non genera codice: la vista vive in ``config/views.sql`` (dato). L'umano
    sceglie il nome; i guardrail di ``/ask`` e una compilazione reale su DuckDB
    garantiscono che la vista sia sicura ed eseguibile prima del commit.
    """
    gruppo = next(
        (g for g in conteggio_fingerprint(dal.data_dir) if g["fingerprint"] == body.fingerprint),
        None,
    )
    if gruppo is None:
        raise HTTPException(
            status_code=404, detail="nessuna query da consolidare per questo fingerprint"
        )
    try:
        preparata = prepara(dal.data_dir, body.nome, gruppo["esempio"])
    except ConsolidaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    voce = dal.consolida_vista(
        nome=body.nome,
        vista=preparata["vista"],
        corpo=preparata["corpo"],
        fingerprint=body.fingerprint,
        esempio=gruppo["esempio"],
        creato_da=admin.username,
    )
    return {
        "vista": preparata["vista"],
        "corpo": preparata["corpo"],
        "righe": preparata["righe"],
        "creato": voce["creato"],
    }


class Parametro(BaseModel):
    valore: str  # il letterale dell'esempio (es. "'Le Palme'" o "100")
    nome: str  # il nome del parametro nella macro (es. "cantiere")


class ConsolidaToolRichiesta(BaseModel):
    fingerprint: str
    nome: str
    parametri: list[Parametro]


@router.post("/dataset/consolida-tool")
def consolida_tool(
    body: ConsolidaToolRichiesta,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Promuove un candidato parametrico a tool ``t_<nome>`` (§3.6, branca "query parametrica").

    Non genera codice Python (Toolsmith automatico = non-goal §5): il tool è una
    **macro tabellare** in ``config/macros.sql`` (dato). L'ufficio nomina i
    parametri; i guardrail di ``/ask`` e una compilazione+chiamata reali su DuckDB
    garantiscono che il tool sia sicuro ed eseguibile prima del commit.
    """
    gruppo = next(
        (g for g in conteggio_fingerprint(dal.data_dir) if g["fingerprint"] == body.fingerprint),
        None,
    )
    if gruppo is None:
        raise HTTPException(
            status_code=404, detail="nessuna query da consolidare per questo fingerprint"
        )
    parametri = [p.model_dump() for p in body.parametri]
    try:
        preparata = prepara_tool(dal.data_dir, body.nome, gruppo["esempio"], parametri)
    except ConsolidaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    voce = dal.consolida_tool(
        nome=body.nome,
        macro=preparata["macro"],
        corpo=preparata["corpo"],
        parametri=preparata["parametri"],
        fingerprint=body.fingerprint,
        esempio=gruppo["esempio"],
        creato_da=admin.username,
    )
    return {
        "macro": preparata["macro"],
        "corpo": preparata["corpo"],
        "parametri": preparata["parametri"],
        "righe": preparata["righe"],
        "creato": voce["creato"],
    }


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
) -> dict[str, Any]:
    """Valuta un modello candidato T3 sul set validato (M18): accuratezza vs T1.

    Rigioca gli esempi già validati e misura la function-calling accuracy;
    indica quali workflow sono "pronti per T3" e dove regredirebbero rispetto a
    T1. Nessun training: solo misura (il modello candidato è ``LLM_<tier>_MODEL``).
    """
    return valutatore.valuta(candidato=candidato, riferimento=riferimento)


@router.get("/tools")
def elenco_tool(
    _admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Registry dei tool nativi con i contatori d'uso + i candidati al consolidamento."""
    usi = conteggio_tool(dal.data_dir)
    # ``elenco()`` porta già ciclo e origine (nativa | pytool): non li sovrascriviamo,
    # così i tool Python consolidati compaiono col loro stato di ciclo reale (M15).
    tools = [
        {**voce, "usi": usi.get(voce["name"], 0)}
        for voce in Toolset(dal).elenco()
    ]
    tools.sort(key=lambda t: t["usi"], reverse=True)
    return {
        "tools": tools,
        "candidati": _candidati(dal.data_dir),
        "viste": leggi_consolidamenti(dal.data_dir),
        "macro": leggi_tool(dal.data_dir),
    }
