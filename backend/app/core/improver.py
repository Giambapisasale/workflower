"""Improver: il cuore dell'auto-miglioramento (§3.5 dell'analisi, §M5 del piano).

Input: un run andato storto + il feedback di chi se n'è accorto. Output: una
**patch** alla skill del workflow, con l'esito del replay sul golden set. Il
punto non negoziabile della letteratura (e dell'analisi): *mai promuovere una
modifica senza replay sui casi già validati*. Perciò il replay gira in una
sandbox (copia usa-e-getta del repo dati): non tocca la fonte di verità finché
un umano non approva. L'approvazione applica il diff, alza la versione (semver)
e committa; solo allora il documento d'origine è rieseguibile con la nuova skill.

I prompt (proposta T1, giudizio T2) vivono in ``data/workflows/improver/``:
sono dati, non codice.
"""

import difflib
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml
from git import Repo

from app.core.dal import DAL, GIT_AUTHOR
from app.core.gateway import Gateway, estrai_json
from app.core.golden import CasoGolden, carica_golden
from app.core.runtime import WorkflowRuntime
from app.core.tracer import leggi_eventi
from app.models.envelope import now_iso

MAX_GOLDEN = 20  # §7: replay contenuto; oltre, si campiona


class ImproverError(Exception):
    """La proposta non è utilizzabile o manca il contesto per generarla."""


class Improver:
    def __init__(self, dal: DAL, gateway: Gateway) -> None:
        self.dal = dal
        self.data_dir = dal.data_dir
        self.gateway = gateway
        self.wf_dir = self.data_dir / "workflows" / "improver"

    # ------------------------------------------------------------ proposta

    def proponi(
        self,
        workflow: str,
        run_id: str | None = None,
        issue_id: str | None = None,
        feedback: str | None = None,
    ) -> dict[str, Any]:
        """Genera la patch (T1) e la misura sul golden set (replay + giudizio T2)."""
        contesto = self._contesto(run_id, issue_id, feedback)
        manifest_wf = self._manifest_workflow(workflow)
        skill_file, skill_testo = self._skill_estrazione(workflow, manifest_wf)
        proposta = self._proponi_llm(workflow, manifest_wf, skill_testo, contesto)
        skill_nuova = proposta["skill_nuova"]
        casi = self._replay(workflow, skill_file, skill_nuova)
        patch = {
            "workflow": workflow,
            "da_versione": str(manifest_wf.get("version", "1.0")),
            "a_versione": self._bump(str(manifest_wf.get("version", "1.0"))),
            "stato": "proposta",
            "analisi": str(proposta.get("analisi", "")),
            "motivazione": str(proposta.get("motivazione", "")),
            "file_skill": skill_file,
            "skill_nuova": skill_nuova,
            "diff_skill": self._diff(skill_file, skill_testo, skill_nuova),
            "diff_manifest": None,
            "origine": {
                "run_id": contesto["run_id"],
                "issue_id": issue_id,
                "doc": contesto["doc"],
            },
            "replay": {
                "totale": len(casi),
                "ok": sum(1 for c in casi if c["uguale"]),
                "casi": casi,
            },
            "creato": now_iso(),
            "deciso_da": None,
        }
        return self.dal.salva_patch(patch)

    # ------------------------------------------------------ approva/rifiuta

    def applica(self, patch: dict[str, Any], deciso_da: str) -> dict[str, Any]:
        """Applica la skill patchata al workflow vero e alza la versione (semver)."""
        wf_root = self.data_dir / "workflows" / patch["workflow"]
        skill_path = wf_root / patch["file_skill"]
        skill_path.write_text(patch["skill_nuova"], encoding="utf-8")
        manifest_path = wf_root / "manifest.yaml"
        testo = manifest_path.read_text(encoding="utf-8")
        testo = re.sub(r'(version:\s*)"[^"]*"', rf'\1"{patch["a_versione"]}"', testo, count=1)
        manifest_path.write_text(testo, encoding="utf-8")
        pid, versione = patch["id"], patch["a_versione"]
        self.dal.commit_paths(
            [skill_path, manifest_path],
            f"workflow {patch['workflow']}: patch {pid} → v{versione} [{pid}]",
        )
        return self.dal.aggiorna_patch(
            {**patch, "stato": "approvata", "deciso_da": deciso_da}, "approva"
        )

    def rifiuta(self, patch: dict[str, Any], deciso_da: str) -> dict[str, Any]:
        return self.dal.aggiorna_patch(
            {**patch, "stato": "rifiutata", "deciso_da": deciso_da}, "rifiuta"
        )

    # ------------------------------------------------------------- contesto

    def _contesto(
        self, run_id: str | None, issue_id: str | None, feedback: str | None
    ) -> dict[str, Any]:
        issue = self.dal.leggi_issue(issue_id) if issue_id else None
        run_id = run_id or (issue.run_id if issue else None)
        if not run_id:
            raise ImproverError("serve un run (diretto o via segnalazione) da correggere")
        doc, entita = self._doc_e_entita(run_id, issue)
        note: list[str] = []
        if feedback:
            note.append(feedback)
        if issue:
            note.append(issue.testo)
        for ev in leggi_eventi(self.data_dir, run_id, {"field_feedback", "operator_feedback"}):
            if ev.get("evento") == "field_feedback":
                note.append(f"campo {ev.get('campo')}: {ev.get('nota')}")
            elif ev.get("tipo") == "segnalazione" and ev.get("testo"):
                note.append(str(ev["testo"]))
        return {
            "run_id": run_id,
            "doc": doc,
            "entita": entita,
            "note": list(dict.fromkeys(n for n in note if n)),  # dedup, ordine stabile
        }

    def _doc_e_entita(
        self, run_id: str, issue: Any
    ) -> tuple[str | None, dict[str, Any] | None]:
        for documento in self.dal.list_all("documento"):
            if documento.dati.get("run_id") == run_id:
                return documento.dati.get("file"), self._forse_dati(documento.dati.get("entity_id"))
        if issue and issue.doc:
            return issue.doc, self._forse_dati(issue.entity_id if issue else None)
        for fattura in self.dal.list_all("fattura"):
            if fattura.meta.run_id == run_id:
                return fattura.meta.origine, fattura.dati
        return None, None

    def _forse_dati(self, entity_id: str | None) -> dict[str, Any] | None:
        from app.core.dal import DalError, tipo_da_id

        tipo = tipo_da_id(entity_id)
        if tipo is None or entity_id is None:
            return None
        try:
            return self.dal.read(tipo, entity_id).dati
        except DalError:
            return None

    # --------------------------------------------------------------- T1/T2

    def _proponi_llm(
        self,
        workflow: str,
        manifest_wf: dict[str, Any],
        skill_testo: str,
        contesto: dict[str, Any],
    ) -> dict[str, Any]:
        manifest = self._manifest_improver()
        skill = (self.wf_dir / manifest["skills"]["proposta"]).read_text(encoding="utf-8")
        prompt = self._prompt_proposta(workflow, manifest_wf, skill_testo, contesto)
        risposta = self.gateway.complete(
            tier=manifest.get("tier_proposta", "T1"),
            messages=[
                {"role": "system", "content": skill},
                {"role": "user", "content": prompt},
            ],
        )
        dato = estrai_json(risposta.text or "")
        if not isinstance(dato, dict) or not dato.get("skill_nuova"):
            raise ImproverError("la proposta non contiene una nuova skill")
        return dato

    def _prompt_proposta(
        self,
        workflow: str,
        manifest_wf: dict[str, Any],
        skill_testo: str,
        contesto: dict[str, Any],
    ) -> str:
        note = "\n".join(f"- {n}" for n in contesto["note"]) or "- (nessuna nota)"
        parti = [
            f"Workflow: {workflow}@{manifest_wf.get('version')}",
            "",
            "Skill attuale del passo di estrazione:",
            "<<<SKILL_ATTUALE",
            skill_testo,
            "SKILL_ATTUALE>>>",
            "",
        ]
        if contesto.get("entita") is not None:
            parti += [
                "Cosa ha estratto il run (bozza da correggere):",
                json.dumps(contesto["entita"], ensure_ascii=False),
                "",
            ]
        parti += ["Feedback ricevuti:", note]
        return "\n".join(parti)

    def _giudica(self, atteso: dict[str, Any], ottenuto: dict[str, Any]) -> dict[str, Any]:
        manifest = self._manifest_improver()
        skill = (self.wf_dir / manifest["skills"]["giudizio"]).read_text(encoding="utf-8")
        utente = (
            'Rispondi in JSON {"uguale": true|false, "differenze": [campi]}.\n\n'
            f"ATTESO:\n{json.dumps(atteso, ensure_ascii=False)}\n\n"
            f"OTTENUTO:\n{json.dumps(ottenuto, ensure_ascii=False)}"
        )
        risposta = self.gateway.complete(
            tier=manifest.get("tier_giudizio", "T2"),
            messages=[
                {"role": "system", "content": skill},
                {"role": "user", "content": utente},
            ],
        )
        dato = estrai_json(risposta.text or "")
        return {
            "uguale": bool(dato.get("uguale")),
            "differenze": [str(d) for d in (dato.get("differenze") or [])],
        }

    # -------------------------------------------------------------- replay

    def _replay(self, workflow: str, skill_file: str, skill_nuova: str) -> list[dict[str, Any]]:
        golden = carica_golden(self.data_dir, workflow)[:MAX_GOLDEN]
        if not golden:
            return []
        sandbox = self._crea_sandbox()
        try:
            skill_sandbox = sandbox / "workflows" / workflow / skill_file
            skill_sandbox.write_text(skill_nuova, encoding="utf-8")
            dal_sandbox = DAL(sandbox)
            runtime = WorkflowRuntime(dal_sandbox, self.gateway)
            return [self._replay_uno(runtime, dal_sandbox, workflow, caso) for caso in golden]
        finally:
            shutil.rmtree(sandbox.parent, ignore_errors=True)

    def _replay_uno(
        self, runtime: WorkflowRuntime, dal_sandbox: DAL, workflow: str, caso: CasoGolden
    ) -> dict[str, Any]:
        esito = runtime.esegui(workflow, caso.doc)  # non solleva mai
        base = {"golden_id": caso.id, "doc": caso.doc}
        if esito.esito != "ok" or not esito.entity_id:
            return {**base, "uguale": False, "differenze": ["esecuzione"], "nota": esito.errore}
        ottenuto = dal_sandbox.read(caso.entity_tipo, esito.entity_id).dati
        return {**base, **self._giudica(caso.atteso, ottenuto)}

    def _crea_sandbox(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="wf-improver-"))
        dst = tmp / "data"
        shutil.copytree(self.data_dir, dst, ignore=shutil.ignore_patterns(".git"))
        repo = Repo.init(dst)
        with repo.config_writer() as cfg:
            cfg.set_value("user", "name", GIT_AUTHOR.name)
            cfg.set_value("user", "email", GIT_AUTHOR.email)
        repo.git.add(all=True)
        repo.index.commit("sandbox replay", author=GIT_AUTHOR, committer=GIT_AUTHOR)
        return dst

    # -------------------------------------------------------------- utility

    def _manifest_workflow(self, workflow: str) -> dict[str, Any]:
        percorso = self.data_dir / "workflows" / workflow / "manifest.yaml"
        if not percorso.is_file():
            raise ImproverError(f"workflow sconosciuto: {workflow}")
        return yaml.safe_load(percorso.read_text(encoding="utf-8")) or {}

    def _manifest_improver(self) -> dict[str, Any]:
        return yaml.safe_load((self.wf_dir / "manifest.yaml").read_text(encoding="utf-8"))

    def _skill_estrazione(self, workflow: str, manifest_wf: dict[str, Any]) -> tuple[str, str]:
        for step in manifest_wf.get("steps", []):
            if isinstance(step, dict) and "skill" in step:
                rel = step["skill"]
                testo = (self.data_dir / "workflows" / workflow / rel).read_text(encoding="utf-8")
                return rel, testo
        raise ImproverError(f"il workflow {workflow} non ha un passo di estrazione con skill")

    @staticmethod
    def _bump(versione: str) -> str:
        parti = versione.split(".")
        if len(parti) >= 2 and parti[-1].isdigit():
            parti[-1] = str(int(parti[-1]) + 1)
            return ".".join(parti)
        return f"{versione}.1"

    @staticmethod
    def _diff(nome: str, vecchio: str, nuovo: str) -> str:
        return "\n".join(
            difflib.unified_diff(
                vecchio.splitlines(),
                nuovo.splitlines(),
                fromfile=f"a/{nome}",
                tofile=f"b/{nome}",
                lineterm="",
            )
        )
