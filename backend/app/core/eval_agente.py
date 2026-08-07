"""Valutazione read-only dell'agente dati su golden tool+risultati."""

from __future__ import annotations

from typing import Any

from app.core.agente_dati import AgenteDati, RegistryToolDati
from app.core.dal import DAL
from app.core.gateway import Gateway
from app.core.golden_agente import casi, impronta_risultato

SOGLIA_PRONTO = 0.9


class EvalAgente:
    def __init__(self, dal: DAL, gateway: Gateway) -> None:
        self.dal, self.gateway = dal, gateway
        self.agente = AgenteDati(dal, gateway)

    def valuta(self, *, candidato: str = "T3", riferimento: str = "T1") -> dict[str, Any]:
        golden = casi(self.dal.data_dir)
        if not self.gateway.t3_attivo():
            return self._vuoto(golden)
        dettaglio = [
            {"golden_id": caso["id"], "domanda": caso["question"],
             "candidato": self._prova(caso, candidato), "riferimento": self._prova(caso, riferimento)}
            for caso in golden
        ]
        cand, rif = self._quote(dettaglio, "candidato"), self._quote(dettaglio, "riferimento")
        return {"casi": len(golden), "casi_totali": len(golden), "candidato": cand,
                "riferimento": rif, "regressione": cand["args"] < rif["args"],
                "pronto_per_t3": bool(len(golden) and cand["args"] >= SOGLIA_PRONTO and cand["args"] >= rif["args"]),
                "dettaglio": dettaglio}

    def _vuoto(self, golden: list[dict[str, Any]]) -> dict[str, Any]:
        zero = {"tool": 0.0, "args": 0.0, "result": 0.0}
        return {"casi": len(golden), "casi_totali": len(golden), "candidato": zero,
                "riferimento": zero, "regressione": False, "pronto_per_t3": False, "dettaglio": []}

    def _prova(self, caso: dict[str, Any], tier: str) -> dict[str, Any]:
        ruolo, cantieri = caso.get("role", "admin"), caso.get("cantieri", [])
        registry = RegistryToolDati(self.dal.data_dir)
        try:
            risposta = self.gateway.complete(
                tier=tier,
                messages=[
                    {"role": "system", "content": self.agente._istruzioni(self.agente._manifest(), ruolo, cantieri)},
                    *caso.get("context", []), {"role": "user", "content": caso["question"]},
                ], tools=registry.schemi(ruolo, cantieri),
            )
        except Exception as exc:
            return {"tool": 0, "args": 0, "result": 0, "errore": str(exc)}
        attese, ottenute = caso.get("tool_calls", []), risposta.tool_calls
        if len(attese) != len(ottenute):
            return {"tool": 0, "args": 0, "result": 0}
        nomi = int([t["name"] for t in attese] == [t.name for t in ottenute])
        argomenti = int(nomi and [t.get("arguments", {}) for t in attese] == [t.arguments for t in ottenute])
        risultati = 0
        if argomenti:
            try:
                risultati = int(all(
                    impronta_risultato(registry.esegui(t.name, t.arguments, ruolo, cantieri)) == atteso.get("result_hash")
                    for t, atteso in zip(ottenute, attese, strict=True)
                ))
            except Exception:
                risultati = 0
        return {"tool": nomi, "args": argomenti, "result": risultati}

    @staticmethod
    def _quote(dettaglio: list[dict[str, Any]], chi: str) -> dict[str, float]:
        if not dettaglio:
            return {"tool": 0.0, "args": 0.0, "result": 0.0}
        return {campo: round(sum(r[chi][campo] for r in dettaglio) / len(dettaglio), 4)
                for campo in ("tool", "args", "result")}
