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

from app.api.deps import (
    get_dal,
    get_data_dir,
    get_eval_interroga,
    get_eval_t3,
    richiedi_admin,
)
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
    fingerprint,
    statistiche,
)
from app.core.eval_interroga import EvalInterroga, unisci
from app.core.eval_t3 import EvalT3
from app.core.golden import casi_domanda
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


class Sorgente(BaseModel):
    """Da dove viene la query da consolidare: una delle tre, non due.

    ``fingerprint`` era l'unica via, e nasceva dall'idea che i candidati si
    scoprano perché una query **si ripete**. Vale nell'uso quotidiano, non quando
    si consolida partendo da un catalogo di domande: 120 domande diverse danno 119
    fingerprint distinti, nessuno ricorrente (vedi ``docs/finetuning-runbook.md``).

    Le altre due vie servono a questo. ``golden_id`` prende la query di un caso
    golden, che è già passata da un'approvazione umana. ``sql`` la prende dal corpo
    della richiesta, per il caso più importante: la vista giusta spesso **non è**
    nessuna delle query prodotte dal modello, va disegnata — è il senso di
    «l'umano conferma sempre» del §3.6. In tutti i casi valgono gli stessi
    guardrail di ``/ask`` e la stessa compilazione reale su DuckDB.
    """

    fingerprint: str | None = None
    golden_id: str | None = None
    sql: str | None = None

    def scelte(self) -> int:
        return sum(1 for v in (self.fingerprint, self.golden_id, self.sql) if v)


def _esempio(dal: DAL, sorgente: Sorgente) -> tuple[str, str]:
    """La query da consolidare e il fingerprint con cui registrarla.

    Il fingerprint finisce nel ledger anche quando la query arriva da ``sql`` o da
    un caso golden: serve a ``consolidati_per_fingerprint`` per marcare il candidato
    quando quella stessa query ricompare fra le domande.
    """
    if sorgente.scelte() != 1:
        raise HTTPException(
            status_code=400,
            detail="indica una sola sorgente: fingerprint, golden_id oppure sql",
        )
    if sorgente.sql:
        return sorgente.sql, fingerprint(sorgente.sql)
    if sorgente.golden_id:
        caso = next(
            (c for c in casi_domanda(dal.data_dir) if c.id == sorgente.golden_id), None
        )
        if caso is None or not caso.sql_riferimento:
            raise HTTPException(
                status_code=404,
                detail=f"nessun caso golden-domanda con id {sorgente.golden_id}",
            )
        return caso.sql_riferimento, fingerprint(caso.sql_riferimento)
    gruppi = conteggio_fingerprint(dal.data_dir)
    gruppo = next((g for g in gruppi if g["fingerprint"] == sorgente.fingerprint), None)
    if gruppo is None:
        raise HTTPException(
            status_code=404, detail="nessuna query da consolidare per questo fingerprint"
        )
    return gruppo["esempio"], sorgente.fingerprint or ""


class ConsolidaRichiesta(Sorgente):
    nome: str


@router.post("/dataset/consolida")
def consolida(
    body: ConsolidaRichiesta,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Promuove una query a vista ``v_<nome>`` (§3.6, branca "vista SQL").

    Non genera codice: la vista vive in ``config/views.sql`` (dato). L'umano
    sceglie il nome; i guardrail di ``/ask`` e una compilazione reale su DuckDB
    garantiscono che la vista sia sicura ed eseguibile prima del commit.
    """
    esempio, impronta = _esempio(dal, body)
    try:
        preparata = prepara(dal.data_dir, body.nome, esempio)
    except ConsolidaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    voce = dal.consolida_vista(
        nome=body.nome,
        vista=preparata["vista"],
        corpo=preparata["corpo"],
        fingerprint=impronta,
        esempio=esempio,
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


class ConsolidaToolRichiesta(Sorgente):
    nome: str
    parametri: list[Parametro]


@router.post("/dataset/consolida-tool")
def consolida_tool(
    body: ConsolidaToolRichiesta,
    admin: Utente = Depends(richiedi_admin),
    dal: DAL = Depends(get_dal),
) -> dict[str, Any]:
    """Promuove una query parametrica a tool ``t_<nome>`` (§3.6, branca "parametrica").

    Non genera codice Python (Toolsmith automatico = non-goal §5): il tool è una
    **macro tabellare** in ``config/macros.sql`` (dato). L'ufficio nomina i
    parametri; i guardrail di ``/ask`` e una compilazione+chiamata reali su DuckDB
    garantiscono che il tool sia sicuro ed eseguibile prima del commit.
    """
    esempio, impronta = _esempio(dal, body)
    parametri = [p.model_dump() for p in body.parametri]
    try:
        preparata = prepara_tool(dal.data_dir, body.nome, esempio, parametri)
    except ConsolidaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    voce = dal.consolida_tool(
        nome=body.nome,
        macro=preparata["macro"],
        corpo=preparata["corpo"],
        parametri=preparata["parametri"],
        fingerprint=impronta,
        esempio=esempio,
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
    valutatore_domande: EvalInterroga = Depends(get_eval_interroga),
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
    return unisci(
        valutatore.valuta(candidato=candidato, riferimento=riferimento),
        valutatore_domande.valuta(candidato=candidato, riferimento=riferimento),
    )


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
