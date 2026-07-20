"""Esecutore dei workflow dichiarativi (manifest §3.2).

Generico per costruzione: aggiungere un'entità = nuovo schema + nuovo
manifest, zero codice qui (non-goal §5). Contratto verso il chiamante:
``esegui`` non solleva mai — qualunque fallimento produce un RunResult
con esito ``errore`` e una issue automatica ("ci pensa l'ufficio").
"""

import contextlib
import json
import uuid
from pathlib import Path
from typing import Any, Literal

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel

from app.core.dal import DAL
from app.core.gateway import Gateway, GatewayError, RispostaLLM, estrai_json
from app.core.rules import valuta_regole
from app.core.tools import Toolset
from app.core.tools.base import ToolError
from app.core.tracer import Tracer

MAX_GIRI_AGENTE = 12  # giri LLM↔tool per step di estrazione
MAX_RIPARAZIONI_JSON = 2  # §7: reparse con retry (max 2)

CONTRATTO_OUTPUT = """## Contratto di output

Consegna il risultato finale come unico oggetto JSON conforme a questo \
JSON Schema, senza testo prima o dopo:

{schema}

In `dati` va la trascrizione del documento; in `confidence` la tua \
confidenza (numero tra 0 e 1) per ogni campo di primo livello di `dati`."""


class EstrazioneFallita(Exception):
    """Uno step non ha prodotto un risultato utilizzabile."""


class RunResult(BaseModel):
    run_id: str
    esito: Literal["ok", "errore"]
    entity_id: str | None = None
    stato: str | None = None  # stato dell'envelope salvato (bozza | errore)
    richiede_revisione: bool = False  # confidence sotto soglia manifest
    errore: str | None = None
    issue_id: str | None = None


def schema_contratto(schema_entita: dict[str, Any]) -> dict[str, Any]:
    """Wrapper {dati, confidence} attorno allo schema dell'entità."""
    return {
        "type": "object",
        "required": ["dati", "confidence"],
        "additionalProperties": False,
        "properties": {
            "dati": schema_entita,
            "confidence": {
                "type": "object",
                "additionalProperties": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
    }


class WorkflowRuntime:
    def __init__(self, dal: DAL, gateway: Gateway) -> None:
        self.dal = dal
        self.data_dir = dal.data_dir
        self.gateway = gateway
        self.toolset = Toolset(dal)

    def esegui(self, workflow: str, doc: str, run_id: str | None = None) -> RunResult:
        """Esegue il workflow sul documento ``doc`` (percorso relativo al repo dati)."""
        run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
        try:
            manifest = self._manifest(workflow)
        except Exception as exc:
            tracer = Tracer(self.data_dir, run_id, workflow, "?")
            tracer.run_start(input_doc=doc)
            return self._fallimento(tracer, run_id, doc, f"manifest non caricabile: {exc}")

        tracer = Tracer(self.data_dir, run_id, manifest["name"], str(manifest["version"]))
        tracer.run_start(input_doc=doc)
        try:
            contesto = self._esegui_steps(manifest, doc, run_id, tracer)
        except Exception as exc:  # rete, tool, output irreparabile: mai al chiamante
            return self._fallimento(tracer, run_id, doc, str(exc))

        entity_id = contesto["entity_id"]
        stato = contesto["stato"]
        revisione = self._sotto_soglia(manifest, contesto["confidence"])
        if contesto["motivo_flag"]:
            motivo = contesto["motivo_flag"]
            issue_id = self._apri_issue(
                f"Verifiche non superate su {doc}: {motivo}", run_id, doc, entity_id
            )
            tracer.run_end(
                outcome="errore",
                entity_id=entity_id,
                stato=stato,
                errore=motivo,
                issue_id=issue_id,
                richiede_revisione=revisione,
            )
            self._commit_artefatti(tracer, run_id, doc)
            return RunResult(
                run_id=run_id,
                esito="errore",
                entity_id=entity_id,
                stato=stato,
                errore=motivo,
                issue_id=issue_id,
                richiede_revisione=revisione,
            )

        tracer.run_end(
            outcome="ok", entity_id=entity_id, stato=stato, richiede_revisione=revisione
        )
        self._commit_artefatti(tracer, run_id, doc)
        return RunResult(
            run_id=run_id,
            esito="ok",
            entity_id=entity_id,
            stato=stato,
            richiede_revisione=revisione,
        )

    # ---------------------------------------------------------------- step

    def _esegui_steps(
        self, manifest: dict[str, Any], doc: str, run_id: str, tracer: Tracer
    ) -> dict[str, Any]:
        wf_dir = self.data_dir / "workflows" / manifest["name"]
        contesto: dict[str, Any] = {
            "dati": None,
            "confidence": {},
            "entity_id": None,
            "stato": "bozza",
            "motivo_flag": None,
        }
        step_estrai: dict[str, Any] | None = None
        for step in manifest["steps"]:
            if "skill" in step:
                step_estrai = step
                contesto["dati"], contesto["confidence"] = self._step_estrazione(
                    manifest, step, wf_dir, doc, tracer
                )
            elif "rules" in step:
                falliti = self._step_valida(step, contesto["dati"], tracer)
                if falliti and step.get("on_fail") == "retry_T1_once_then_flag" and step_estrai:
                    feedback = (
                        "La bozza precedente non ha superato queste verifiche: "
                        + "; ".join(falliti)
                        + ". Rileggi il documento con attenzione e correggi i campi."
                    )
                    contesto["dati"], contesto["confidence"] = self._step_estrazione(
                        manifest, step_estrai, wf_dir, doc, tracer, feedback=feedback
                    )
                    falliti = self._step_valida(step, contesto["dati"], tracer)
                if falliti:
                    # flag: si salva comunque, in stato errore, e si apre una issue
                    contesto["stato"] = "errore"
                    contesto["motivo_flag"] = "; ".join(falliti)
            elif step.get("action") == "save_draft":
                contesto["entity_id"] = self._step_salva(
                    manifest, step_estrai, doc, run_id, tracer, contesto
                )
            else:
                raise EstrazioneFallita(f"step non riconosciuto nel manifest: {step.get('id')}")
        return contesto

    def _step_estrazione(
        self,
        manifest: dict[str, Any],
        step: dict[str, Any],
        wf_dir: Path,
        doc: str,
        tracer: Tracer,
        feedback: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, float]]:
        """Estrazione con escalation T3→T1 (M19).

        Se il workflow è instradato su T3 e T3 è attivo, gira prima su T3; su
        **errore**, **bassa confidence** o **output fuori contratto** rifà lo step
        su T1 e traccia l'escalation. Il tier resta l'unica dichiarazione del
        manifest (§3.1); a T3 spento il comportamento è invariato (si usa T1).
        """
        tier = manifest.get("tier", "T1")
        if tier != "T3" or not self.gateway.t3_attivo():
            return self._estrai_su_tier(manifest, step, wf_dir, doc, tracer, tier, feedback)
        try:
            dati, confidence = self._estrai_su_tier(
                manifest, step, wf_dir, doc, tracer, "T3", feedback
            )
            if not self._sotto_soglia(manifest, confidence):
                return dati, confidence
            motivo = "bassa confidence"
        except (EstrazioneFallita, GatewayError) as exc:
            motivo = f"errore: {exc}"
        tracer.escalation(step=step["id"], da="T3", a="T1", motivo=motivo)
        return self._estrai_su_tier(manifest, step, wf_dir, doc, tracer, "T1", feedback)

    def _estrai_su_tier(
        self,
        manifest: dict[str, Any],
        step: dict[str, Any],
        wf_dir: Path,
        doc: str,
        tracer: Tracer,
        tier: str,
        feedback: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, float]]:
        skill = (wf_dir / step["skill"]).read_text(encoding="utf-8")
        schema_entita = json.loads(
            (self.data_dir / step["output_schema"]).read_text(encoding="utf-8")
        )
        contratto = schema_contratto(schema_entita)
        validatore = Draft202012Validator(contratto, format_checker=FormatChecker())
        # Ai tool nativi dichiarati dallo step si aggiungono i tool Python
        # consolidati (M15/M17): la skill impara a chiamarli, l'LLM resta il
        # fallback. Un tool consolidato che erra torna come errore al modello
        # (sotto), che completa comunque lo step: mai un single-point-of-failure.
        nomi_tool = list(step.get("tools") or [])
        nomi_tool += [n for n in self.toolset.nomi_consolidati() if n not in nomi_tool]
        schemi_tool = self.toolset.schemi(nomi_tool) or None

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": skill},
            {
                "role": "system",
                "content": CONTRATTO_OUTPUT.format(
                    schema=json.dumps(contratto, ensure_ascii=False)
                ),
            },
            {"role": "user", "content": f"Documento da elaborare: {doc}"},
        ]
        if feedback:
            messages.append({"role": "user", "content": feedback})

        riparazioni = 0
        for _ in range(MAX_GIRI_AGENTE):
            risposta = self.gateway.complete(
                tier=tier,
                messages=messages,
                tools=schemi_tool,
                tracer=tracer,
                step=step["id"],
            )
            if risposta.tool_calls:
                messages.append(_messaggio_assistant(risposta))
                for chiamata in risposta.tool_calls:
                    ok, risultato = True, None
                    try:
                        risultato = self.toolset.esegui(
                            chiamata.name, chiamata.arguments, consentiti=nomi_tool
                        )
                    except ToolError as exc:
                        ok, risultato = False, {"errore": str(exc)}
                    tracer.tool_call(
                        step=step["id"],
                        name=chiamata.name,
                        args=chiamata.arguments,
                        result=risultato,
                        ok=ok,
                        messages=messages,
                        tools=schemi_tool,
                    )
                    testo_tool, allegato = _risultato_per_llm(risultato)
                    messages.append(
                        {"role": "tool", "tool_call_id": chiamata.id, "content": testo_tool}
                    )
                    if allegato:
                        messages.append(allegato)
                continue

            try:
                output = estrai_json(risposta.text or "")
                errori = [
                    f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
                    for e in validatore.iter_errors(output)
                ]
                if errori:
                    raise EstrazioneFallita("; ".join(errori[:5]))
                return output["dati"], output["confidence"]
            except (GatewayError, EstrazioneFallita) as exc:
                riparazioni += 1
                if riparazioni > MAX_RIPARAZIONI_JSON:
                    raise EstrazioneFallita(f"output non conforme: {exc}") from exc
                messages.append({"role": "assistant", "content": risposta.text or ""})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"L'output non è valido ({exc}). "
                            "Consegna di nuovo SOLO il JSON conforme al contratto."
                        ),
                    }
                )
        raise EstrazioneFallita(f"nessun output finale dopo {MAX_GIRI_AGENTE} giri di tool")

    def _step_valida(
        self, step: dict[str, Any], dati: dict[str, Any] | None, tracer: Tracer
    ) -> list[str]:
        """Valuta le regole del manifest; ritorna le verifiche fallite."""
        if dati is None:
            tracer.validation(step=step["id"], esito="fallita", dettagli="nessun dato estratto")
            return ["nessun dato estratto"]
        esiti = valuta_regole(list(step["rules"]), dati)
        falliti = [
            esito.regola + (f" ({esito.errore})" if esito.errore else "")
            for esito in esiti
            if not esito.ok
        ]
        tracer.validation(
            step=step["id"],
            esito="ok" if not falliti else "fallita",
            dettagli=[esito.model_dump() for esito in esiti],
        )
        return falliti

    def _step_salva(
        self,
        manifest: dict[str, Any],
        step_estrai: dict[str, Any] | None,
        doc: str,
        run_id: str,
        tracer: Tracer,
        contesto: dict[str, Any],
    ) -> str:
        if contesto["dati"] is None or step_estrai is None:
            raise EstrazioneFallita("niente da salvare: nessuno step di estrazione riuscito")
        # il tipo entità discende dallo schema dichiarato dallo step di estrazione
        tipo = Path(step_estrai["output_schema"]).name.split(".")[0]
        argomenti = {
            "tipo": tipo,
            "dati": contesto["dati"],
            "stato": contesto["stato"],
            "confidence": contesto["confidence"],
            "origine": doc,
            "workflow": f"{manifest['name']}@{manifest['version']}",
            "run_id": run_id,
        }
        schemi = self.toolset.schemi(["salva_bozza"])
        try:
            risultato = self.toolset.esegui("salva_bozza", argomenti)
        except ToolError as exc:
            tracer.tool_call(
                step="salva",
                name="salva_bozza",
                args=argomenti,
                result={"errore": str(exc)},
                ok=False,
                tools=schemi,
            )
            raise
        tracer.tool_call(
            step="salva",
            name="salva_bozza",
            args=argomenti,
            result=risultato,
            ok=True,
            tools=schemi,
        )
        return risultato["id"]

    # ------------------------------------------------------------- interni

    def _manifest(self, workflow: str) -> dict[str, Any]:
        percorso = self.data_dir / "workflows" / workflow / "manifest.yaml"
        manifest = yaml.safe_load(percorso.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or "steps" not in manifest:
            raise EstrazioneFallita(f"manifest non valido: {percorso}")
        return manifest

    def _fallimento(self, tracer: Tracer, run_id: str, doc: str, errore: str) -> RunResult:
        issue_id = self._apri_issue(
            f"Elaborazione automatica fallita su {doc}: {errore}", run_id, doc, None
        )
        tracer.run_end(outcome="errore", errore=errore, issue_id=issue_id)
        self._commit_artefatti(tracer, run_id, doc)
        return RunResult(run_id=run_id, esito="errore", errore=errore, issue_id=issue_id)

    def _apri_issue(
        self, testo: str, run_id: str, doc: str, entity_id: str | None
    ) -> str | None:
        try:
            issue = self.dal.crea_issue(
                "auto", testo, run_id=run_id, doc=doc, entity_id=entity_id
            )
            return issue.id
        except Exception:
            return None  # anche la issue può fallire: resta comunque il trace

    def _commit_artefatti(self, tracer: Tracer, run_id: str, doc: str) -> None:
        percorsi = [tracer.trace_path, tracer.dataset_path, self.data_dir / doc]
        # il commit degli artefatti non deve mai far fallire il run
        with contextlib.suppress(Exception):
            self.dal.commit_paths(percorsi, f"trace {run_id}: registra artefatti [{run_id}]")

    @staticmethod
    def _sotto_soglia(manifest: dict[str, Any], confidence: dict[str, float]) -> bool:
        soglia = manifest.get("confidence_threshold")
        if not soglia or not confidence:
            return False
        return min(confidence.values()) < float(soglia)


def _messaggio_assistant(risposta: RispostaLLM) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": risposta.text,
        "tool_calls": [
            {
                "id": chiamata.id,
                "type": "function",
                "function": {
                    "name": chiamata.name,
                    "arguments": json.dumps(chiamata.arguments, ensure_ascii=False),
                },
            }
            for chiamata in risposta.tool_calls
        ],
    }


def _risultato_per_llm(risultato: Any) -> tuple[str, dict[str, Any] | None]:
    """Contenuto del messaggio tool; le immagini viaggiano in un messaggio utente."""
    if isinstance(risultato, dict) and "immagini_png_base64" in risultato:
        immagini = risultato["immagini_png_base64"]
        parti: list[dict[str, Any]] = [{"type": "text", "text": "Pagine del documento:"}]
        parti += [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}}
            for img in immagini
        ]
        testo = (
            f"{risultato.get('pagine', len(immagini))} pagine convertite: "
            "le immagini sono nel messaggio utente successivo."
        )
        return testo, {"role": "user", "content": parti}
    return json.dumps(risultato, ensure_ascii=False), None
