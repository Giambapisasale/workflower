"""Harness di valutazione offline del tier T3 (Fase 3, M18).

Prima di *instradare* un workflow sul modello locale fine-tuned (T3), bisogna
*misurare* se è abbastanza bravo: è il presupposto della distillazione (§3.7) e
dell'escalation (§3.1). Qui **non si addestra nulla** — si misura soltanto.

Riusa il dataset builder (:func:`app.core.dataset.toolcalls_validati`): rigioca
gli esempi già validati dall'ufficio contro un **modello candidato T3** (via
gateway, quindi un qualunque endpoint locale raggiungibile da litellm) e ne
misura la **function-calling accuracy** — tool giusto e argomenti giusti —
rispetto al ground truth validato, confrontandola con T1 per workflow. Il
verdetto "pronto per T3" richiede accuratezza alta *e* nessuna regressione su T1.
"""

import re
from copy import deepcopy
from typing import Any

from app.core.dal import DAL
from app.core.dataset import toolcalls_validati
from app.core.gateway import Gateway, GatewayError, ModelloNonConfigurato
from app.core.logbook import ottieni_logger
from app.core.tools import ocr_pdf
from app.core.tools.base import ToolError
from app.core.tracer import leggi_eventi

# Soglia di accuratezza (argomenti) sotto cui un workflow non è pronto per T3.
SOGLIA_PRONTO = 0.9

# Il segnaposto che ``tracer.sanitizza`` lascia al posto delle stringhe lunghe
# (i base64 delle immagini): ``<184320 caratteri, sha256:ab12cd34ef56>``.
SEGNAPOSTO = re.compile(r"^<\d+ caratteri, sha256:[0-9a-f]+>$")

_log = ottieni_logger("eval_t3")


def _oscurato(valore: Any) -> bool:
    """Vero se in questo valore c'è un segnaposto lasciato dal trace."""
    if isinstance(valore, str):
        return bool(SEGNAPOSTO.match(valore))
    if isinstance(valore, dict):
        return any(_oscurato(v) for v in valore.values())
    if isinstance(valore, list):
        return any(_oscurato(v) for v in valore)
    return False


def _parti_immagine(messaggi: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Le parti ``image_url`` dei messaggi, in ordine di invio."""
    parti = []
    for messaggio in messaggi:
        for parte in messaggio.get("content") or []:
            if isinstance(parte, dict) and parte.get("type") == "image_url":
                parti.append(parte)
    return parti


def _immagini_oscurate(messaggi: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Le immagini che il trace ha sostituito con un segnaposto.

    Sono l'unico ostacolo *tecnico* al replay: un ``image_url`` finto viene
    **rifiutato** dal provider (400), mentre un testo oscurato è un payload valido
    — inutile, ma valido. Distinguere i due casi è la differenza fra una misura
    che si può fare e un errore 500.
    """
    return [
        p
        for p in _parti_immagine(messaggi)
        if _oscurato((p.get("image_url") or {}).get("url"))
    ]


def _prompt_troncati(messaggi: list[dict[str, Any]]) -> int:
    """Quante parti *testuali* il trace ha oscurato (di norma le skill, lunghe).

    Non impedisce il replay, ma **abbassa** l'accuratezza assoluta di entrambi i
    tier: il modello riceve un prompt di sistema svuotato. Il confronto T3 contro
    T1 resta onesto perché la penalità è la stessa per tutti e due — ma il numero
    va letto sapendolo, e per questo finisce nel report.
    """
    troncati = 0
    for messaggio in messaggi:
        contenuto = messaggio.get("content")
        if isinstance(contenuto, str) and _oscurato(contenuto):
            troncati += 1
        elif isinstance(contenuto, list):
            troncati += sum(
                1 for p in contenuto if isinstance(p, dict) and _oscurato(p.get("text"))
            )
    return troncati


class EvalT3:
    def __init__(self, dal: DAL, gateway: Gateway) -> None:
        self.dal = dal
        self.gateway = gateway
        # Esempi validati che non si è riusciti a rimettere in condizione di essere
        # rigiocati, e prompt che il trace ha troncato: vanno dichiarati nel
        # report, non taciuti.
        self._scartati = 0
        self._troncati = 0

    def esempi_valutabili(self) -> list[dict[str, Any]]:
        """Gli esempi in cui il modello ha *scelto* un tool dato un contesto.

        Solo le tool call con messaggi e schemi offerti (le decisioni del
        modello): si esclude ``salva_bozza``, invocato dal runtime e non dal
        modello (nessun messaggio, nessuna scelta da valutare).

        Gli esempi dei workflow che leggono un documento arrivano con le immagini
        **oscurate** dal trace: vengono **reidratate** rifacendo l'OCR
        dell'originale (vedi :meth:`_reidrata`), perché un ``image_url`` finto il
        provider lo rifiuta. Quelli per cui non si riesce vengono scartati e
        contati, non spacciati per errori del modello.
        """
        self._scartati = 0
        self._troncati = 0
        esempi = []
        for es in toolcalls_validati(self.dal):
            if not (es.get("messages") and es.get("tools")):
                continue
            if not (es.get("tool_call") or {}).get("name"):
                continue
            if _immagini_oscurate(es["messages"]):
                messaggi = self._reidrata(es)
                if messaggi is None:
                    self._scartati += 1
                    continue
                es = {**es, "messages": messaggi}
            self._troncati += _prompt_troncati(es["messages"])
            esempi.append(es)
        return esempi

    def _reidrata(self, esempio: dict[str, Any]) -> list[dict[str, Any]] | None:
        """Rimette le immagini vere al posto dei segnaposto, rifacendo l'OCR.

        Il documento originale è ancora nel repo dati (``run_start.input`` del
        trace): riconvertirlo costa una lettura locale e nessun token, e restituisce
        le pagine **nello stesso ordine** in cui il runtime le aveva inviate.

        ``None`` se non si può ricostruire con certezza — originale mancante, OCR
        fallito, o un numero di pagine diverso dal numero di segnaposto. Meglio un
        esempio in meno che una misura fatta su un contesto inventato.
        """
        run_id = esempio.get("run_id")
        if not run_id:
            return None
        avvio = next(
            (e for e in leggi_eventi(self.dal.data_dir, str(run_id), {"run_start"})), None
        )
        blob = (avvio or {}).get("input")
        if not blob or not (self.dal.data_dir / str(blob)).is_file():
            return None
        try:
            immagini = ocr_pdf.esegui(self.dal.data_dir, str(blob))["immagini_png_base64"]
        except (ToolError, KeyError, OSError) as exc:
            _log.warning("OCR non ripetibile per %s: %s", run_id, exc)
            return None

        messaggi = deepcopy(esempio["messages"])
        da_riempire = _immagini_oscurate(messaggi)
        if len(da_riempire) != len(immagini):
            return None  # pagine e segnaposto non combaciano: non si indovina
        for parte, immagine in zip(da_riempire, immagini, strict=True):
            parte["image_url"]["url"] = f"data:image/png;base64,{immagine}"
        return messaggi

    def valuta(
        self,
        *,
        candidato: str = "T3",
        riferimento: str = "T1",
        soglia: float = SOGLIA_PRONTO,
    ) -> dict[str, Any]:
        """Rigioca il set validato sui due tier e produce il report comparativo."""
        esempi = self.esempi_valutabili()
        esiti_c = [self._prova(es, candidato) for es in esempi]
        esiti_r = [self._prova(es, riferimento) for es in esempi]

        per_wf: dict[str, dict[str, int]] = {}
        for es, ec, er in zip(esempi, esiti_c, esiti_r, strict=True):
            wf = es.get("workflow") or "?"
            g = per_wf.setdefault(
                wf, {"esempi": 0, "c_tool": 0, "c_args": 0, "r_tool": 0, "r_args": 0}
            )
            g["esempi"] += 1
            g["c_tool"] += ec["tool_ok"]
            g["c_args"] += ec["args_ok"]
            g["r_tool"] += er["tool_ok"]
            g["r_args"] += er["args_ok"]

        workflow: dict[str, Any] = {}
        for wf, g in sorted(per_wf.items()):
            n = g["esempi"]
            cand = {"tool": _quota(g["c_tool"], n), "args": _quota(g["c_args"], n)}
            rif = {"tool": _quota(g["r_tool"], n), "args": _quota(g["r_args"], n)}
            regressione = cand["args"] < rif["args"]
            workflow[wf] = {
                "esempi": n,
                "candidato": cand,
                "riferimento": rif,
                "regressione": regressione,
                "pronto_per_t3": cand["args"] >= soglia and not regressione,
            }

        n = len(esempi)
        return {
            "modello_candidato": self._modello(candidato),
            "modello_riferimento": self._modello(riferimento),
            "tier_candidato": candidato,
            "tier_riferimento": riferimento,
            "soglia": soglia,
            "esempi": n,
            # Dichiarati, non nascosti: se la misura copre 4 esempi su 40, o se i
            # prompt arrivano troncati, chi legge deve saperlo *prima* di decidere
            # di instradare traffico vero su T3.
            "non_rigiocabili": self._scartati,
            "prompt_troncati": self._troncati,
            # Senza ``LLM_T3_MODEL`` il gateway fa ricadere T3 su T1 (§3.1): la misura
            # gira, ma confronta un modello con se stesso. Va detto, altrimenti un
            # "pronto per T3" al 100% verrebbe letto come una promozione meritata.
            "t3_configurato": self.gateway.t3_attivo(),
            "totale": {
                "candidato": {
                    "tool": _quota(sum(e["tool_ok"] for e in esiti_c), n),
                    "args": _quota(sum(e["args_ok"] for e in esiti_c), n),
                },
                "riferimento": {
                    "tool": _quota(sum(e["tool_ok"] for e in esiti_r), n),
                    "args": _quota(sum(e["args_ok"] for e in esiti_r), n),
                },
            },
            "workflow": workflow,
            "pronti": [wf for wf, v in workflow.items() if v["pronto_per_t3"]],
            "regressioni": [wf for wf, v in workflow.items() if v["regressione"]],
        }

    # --------------------------------------------------------------- interni

    def _prova(self, esempio: dict[str, Any], tier: str) -> dict[str, int]:
        """Rigioca un esempio su un tier e confronta la tool call col ground truth.

        Non solleva mai: una misura è un rapporto, e un rapporto che va in errore a
        metà non serve a nessuno. Se il tier non è configurato o il provider rifiuta
        il payload, l'esempio conta zero e il motivo finisce nel logbook.
        """
        atteso = esempio.get("tool_call") or {}
        try:
            risposta = self.gateway.complete(
                tier=tier,
                messages=_contesto_pre_chiamata(esempio["messages"]),
                tools=esempio.get("tools") or None,
            )
        except GatewayError:
            return {"tool_ok": 0, "args_ok": 0}
        except Exception as exc:  # payload rifiutato dal provider, quota, rete…
            _log.warning("esempio non rigiocabile su %s: %s", tier, exc)
            return {"tool_ok": 0, "args_ok": 0}
        ottenuta = risposta.tool_calls[0] if risposta.tool_calls else None
        tool_ok = int(ottenuta is not None and ottenuta.name == atteso.get("name"))
        args_ok = int(bool(tool_ok) and ottenuta.arguments == (atteso.get("args") or {}))
        return {"tool_ok": tool_ok, "args_ok": args_ok}

    def _modello(self, tier: str) -> str | None:
        try:
            return self.gateway.modello(tier)
        except ModelloNonConfigurato:
            return None


def _quota(parte: int, totale: int) -> float:
    return round(parte / totale, 4) if totale else 0.0


def _contesto_pre_chiamata(messaggi: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Il contesto *prima* della tool call registrata, per valutarne la decisione.

    Il trace salva i messaggi già comprensivi del messaggio ``assistant`` che
    emette la tool call in corso: per misurare se il modello *sceglierebbe* quella
    chiamata bisogna rimuoverlo e riproporgli il contesto immediatamente prima.
    """
    contesto = list(messaggi)
    while (
        contesto
        and contesto[-1].get("role") == "assistant"
        and contesto[-1].get("tool_calls")
    ):
        contesto.pop()
    return contesto
