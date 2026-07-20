"""Harness di valutazione offline del tier T3 (Fase 3, M18).

Prima di *instradare* un workflow sul modello locale fine-tuned (T3), bisogna
*misurare* se è abbastanza bravo: è il presupposto della distillazione (§3.7) e
dell'escalation (§3.1). Qui **non si addestra nulla** — si misura soltanto.

Riusa il dataset builder (:func:`app.core.dataset.esempi_finetuning`): rigioca
gli esempi già validati dall'ufficio contro un **modello candidato T3** (via
gateway, quindi un qualunque endpoint locale raggiungibile da litellm) e ne
misura la **function-calling accuracy** — tool giusto e argomenti giusti —
rispetto al ground truth validato, confrontandola con T1 per workflow. Il
verdetto "pronto per T3" richiede accuratezza alta *e* nessuna regressione su T1.
"""

from typing import Any

from app.core.dal import DAL
from app.core.dataset import esempi_finetuning
from app.core.gateway import Gateway, GatewayError, ModelloNonConfigurato

# Soglia di accuratezza (argomenti) sotto cui un workflow non è pronto per T3.
SOGLIA_PRONTO = 0.9


class EvalT3:
    def __init__(self, dal: DAL, gateway: Gateway) -> None:
        self.dal = dal
        self.gateway = gateway

    def esempi_valutabili(self) -> list[dict[str, Any]]:
        """Gli esempi in cui il modello ha *scelto* un tool dato un contesto.

        Solo le tool call con messaggi e schemi offerti (le decisioni del
        modello): si esclude ``salva_bozza``, invocato dal runtime e non dal
        modello (nessun messaggio, nessuna scelta da valutare).
        """
        esempi = []
        for es in esempi_finetuning(self.dal):
            if es.get("messages") and es.get("tools") and (es.get("tool_call") or {}).get("name"):
                esempi.append(es)
        return esempi

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
        """Rigioca un esempio su un tier e confronta la tool call col ground truth."""
        atteso = esempio.get("tool_call") or {}
        try:
            risposta = self.gateway.complete(
                tier=tier,
                messages=_contesto_pre_chiamata(esempio["messages"]),
                tools=esempio.get("tools") or None,
            )
        except GatewayError:
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
