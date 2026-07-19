"""Toolsmith: consolida un calcolo ricorrente in un tool Python (Fase 3, M16).

È il §3.6 punti 1–2. Dove l'Improver (§M5) riscrive una *skill*, il Toolsmith
propone un *tool deterministico*: prende un calcolo/normalizzazione che oggi è
affidato al prompt (l'esempio canonico è la **ritenuta d'acconto**) e lo
trasforma in una funzione Python pura.

Il punto non negoziabile: i **test si generano dalle coppie storiche già
validate** dall'ufficio (l'instrumentazione del delta estratto→validato, M16),
non da esempi inventati. Con T1 si generano funzione e schema; la sandbox (M14)
esegue i test. L'output è una **proposta** ispezionabile — analoga a una
``Patch`` — salvata per l'approvazione umana: **non registra nulla** nel
registry (l'attivazione è M17).

I prompt vivono in ``data/workflows/toolsmith/`` (dati, non codice).
"""

import json
from typing import Any

import yaml

from app.core.dal import DAL
from app.core.dataset import leggi_derivazioni
from app.core.gateway import Gateway, estrai_json
from app.core.pytools import NOME_PYTOOL
from app.core.sandbox import esegui_in_sandbox
from app.core.tools.base import ToolError
from app.models.envelope import now_iso

# Un candidato serve solo se il calcolo si ripete: sotto questa soglia di esempi
# validati non c'è materia per generare né per testare in modo credibile.
MIN_ESEMPI = 3
# Quante volte un campo dev'essere stato corretto per emergere come candidato.
MIN_OCCORRENZE = 2


class ToolsmithError(Exception):
    """Il candidato non è consolidabile o manca il contesto per generarlo."""


class Toolsmith:
    def __init__(self, dal: DAL, gateway: Gateway) -> None:
        self.dal = dal
        self.data_dir = dal.data_dir
        self.gateway = gateway
        self.wf_dir = self.data_dir / "workflows" / "toolsmith"

    # ------------------------------------------------------------ candidati

    def candidati(self) -> list[dict[str, Any]]:
        """I campi corretti in modo ricorrente: il segnale di un calcolo da consolidare.

        Deriva dal delta estratto→validato (M16): un campo che l'ufficio corregge
        di frequente allo stesso modo è quasi sempre una derivazione deterministica
        che il prompt sta facendo a mano. Non inventa la formula — la sceglie
        l'umano (M17) — ma indica *dove* vale la pena guardare.
        """
        gruppi: dict[tuple[str, str, str], dict[str, Any]] = {}
        for der in leggi_derivazioni(self.data_dir):
            tipo, workflow = der.get("tipo"), der.get("workflow")
            validato = der.get("validato") or {}
            for campo in der.get("corretti") or []:
                if validato.get(campo) is None:
                    continue
                chiave = (workflow or "", tipo or "", campo)
                voce = gruppi.setdefault(
                    chiave,
                    {"workflow": workflow, "tipo": tipo, "campo": campo, "occorrenze": 0,
                     "valori": []},
                )
                voce["occorrenze"] += 1
                if len(voce["valori"]) < 5:
                    voce["valori"].append(validato.get(campo))
        candidati = [v for v in gruppi.values() if v["occorrenze"] >= MIN_OCCORRENZE]
        candidati.sort(key=lambda v: v["occorrenze"], reverse=True)
        return candidati

    def esempi(self, candidato: dict[str, Any]) -> list[dict[str, Any]]:
        """Le coppie I/O validate del candidato, in forma di casi di test.

        Ground truth: legge dal lato *validato* delle derivazioni (ciò che
        l'ufficio ha confermato), non dal grezzo. Tiene solo le coppie complete
        (tutti gli ingressi e l'uscita presenti e non nulli) e le deduplica.
        """
        tipo = candidato["tipo"]
        workflow = candidato.get("workflow")
        campi_input = candidato["campi_input"]
        campo_output = candidato["campo_output"]
        esempi: list[dict[str, Any]] = []
        visti: set[str] = set()
        for der in leggi_derivazioni(self.data_dir):
            if der.get("tipo") != tipo:
                continue
            if workflow and der.get("workflow") != workflow:
                continue
            validato = der.get("validato") or {}
            argomenti = {c: validato.get(c) for c in campi_input}
            atteso_val = validato.get(campo_output)
            if any(v is None for v in argomenti.values()) or atteso_val is None:
                continue
            chiave = repr(sorted(argomenti.items()))
            if chiave in visti:
                continue
            visti.add(chiave)
            esempi.append({"argomenti": argomenti, "atteso": {campo_output: atteso_val}})
        return esempi

    # ------------------------------------------------------------- proposta

    def proponi(self, candidato: dict[str, Any]) -> dict[str, Any]:
        """Genera una proposta di tool dal candidato: codice+schema (T1) e test (dai trace).

        La proposta è dato ispezionabile, con l'esito dei test in sandbox; non
        attiva nulla. Solleva se il candidato è malformato o senza esempi a
        sufficienza — non si consolida un calcolo che non si è mai osservato.
        """
        self._valida_candidato(candidato)
        esempi = self.esempi(candidato)
        if len(esempi) < MIN_ESEMPI:
            raise ToolsmithError(
                f"servono almeno {MIN_ESEMPI} esempi validati, trovati {len(esempi)}"
            )
        generato = self._genera(candidato, esempi)
        codice = generato["codice"]
        schema = generato["schema"]
        schema.setdefault("type", "function")
        schema.setdefault("function", {})
        schema["function"]["name"] = candidato["nome"]  # lo schema segue il nome del tool
        esito = self._prova(codice, esempi)
        proposta = {
            "nome": candidato["nome"],
            "candidato": candidato,
            "codice": codice,
            "schema": schema,
            "test": esempi,
            "esito_test": esito,
            "esempi": len(esempi),
            "stato": "proposta",
            "creato": now_iso(),
            "deciso_da": None,
        }
        return self.dal.salva_proposta(proposta)

    # --------------------------------------------------------------- interni

    @staticmethod
    def _valida_candidato(candidato: dict[str, Any]) -> None:
        nome = candidato.get("nome")
        if not isinstance(nome, str) or not NOME_PYTOOL.match(nome):
            raise ToolsmithError(f"nome di tool non valido: {nome!r}")
        if not candidato.get("tipo"):
            raise ToolsmithError("il candidato deve indicare il tipo di entità")
        campi_input = candidato.get("campi_input")
        if not isinstance(campi_input, list) or not campi_input:
            raise ToolsmithError("il candidato deve indicare i campi in ingresso")
        if not isinstance(candidato.get("campo_output"), str) or not candidato["campo_output"]:
            raise ToolsmithError("il candidato deve indicare il campo di uscita")

    def _genera(self, candidato: dict[str, Any], esempi: list[dict[str, Any]]) -> dict[str, Any]:
        manifest = yaml.safe_load((self.wf_dir / "manifest.yaml").read_text(encoding="utf-8"))
        skill = (self.wf_dir / manifest["skills"]["generazione"]).read_text(encoding="utf-8")
        risposta = self.gateway.complete(
            tier=manifest.get("tier_generazione", "T1"),
            messages=[
                {"role": "system", "content": skill},
                {"role": "user", "content": self._prompt(candidato, esempi)},
            ],
        )
        dato = estrai_json(risposta.text or "")
        if not isinstance(dato, dict) or not dato.get("codice") or not isinstance(
            dato.get("schema"), dict
        ):
            raise ToolsmithError("la generazione non ha prodotto codice e schema validi")
        return dato

    @staticmethod
    def _prompt(candidato: dict[str, Any], esempi: list[dict[str, Any]]) -> str:
        righe = [
            f"Nome del tool: {candidato['nome']}",
            f"Campi in ingresso: {', '.join(candidato['campi_input'])}",
            f"Campo di uscita: {candidato['campo_output']}",
            "",
            "Esempi già validati dall'ufficio (input → output reali):",
        ]
        for e in esempi:
            righe.append(
                f"- {json.dumps(e['argomenti'], ensure_ascii=False)} → "
                f"{json.dumps(e['atteso'], ensure_ascii=False)}"
            )
        return "\n".join(righe)

    def _prova(self, codice: str, test: list[dict[str, Any]]) -> dict[str, Any]:
        """Esegue ogni caso in sandbox e raccoglie l'esito, senza mai sollevare.

        La proposta registra la verità: se il codice generato non passa i test
        (dai trace), l'esito lo dice e l'umano non approva.
        """
        casi = []
        for caso in test:
            esito = {"argomenti": caso["argomenti"], "atteso": caso["atteso"]}
            try:
                ottenuto = esegui_in_sandbox(codice, caso["argomenti"])
                esito["ottenuto"] = ottenuto
                esito["ok"] = ottenuto == caso["atteso"]
            except ToolError as exc:
                esito["ottenuto"] = None
                esito["ok"] = False
                esito["errore"] = str(exc)
            casi.append(esito)
        return {"totale": len(casi), "ok": sum(1 for c in casi if c["ok"]), "casi": casi}
