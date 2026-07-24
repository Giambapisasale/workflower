"""Diagnostico: all'arrivo di errori analizza i log e propone una risoluzione.

È l'ultimo tassello del logging. Quando nel logbook compaiono errori, un trigger
(``main.py``, opzionale) o l'endpoint ``/api/diagnoses/analyze`` avviano qui
l'analisi. Per ogni **firma** d'errore distinta il Diagnostico:

1. raccoglie il cluster (le voci con quella firma) e legge il **proprio codice
   sorgente** coinvolto dal traceback (``codebase.py``);
2. se l'errore nasce in un workflow, allega gli **artefatti-dato** (skill,
   manifest, schema);
3. chiede a un LLM (prompt-dato in ``data/workflows/diagnostico/``) una diagnosi
   che **classifica** il problema:
   - ``dato`` → correggibile modificando skill/tool/schema/config: propone la
     modifica (e, per le skill di estrazione, rimanda all'Improver);
   - ``architettura`` → richiede di toccare il codice-cornice: **sola analisi**.

Non applica mai nulla: la diagnosi è una proposta ispezionabile in
``data/diagnoses/``, in attesa di una decisione umana (human-in-the-loop).
Le firme già diagnosticate non ripartono: si limita ad aggiornarne il conteggio.
"""

from typing import Any

import yaml

from app.core import codebase
from app.core.dal import DAL, DalError
from app.core.gateway import Gateway, GatewayError, estrai_json
from app.core.logbook import firma as calcola_firma
from app.core.logbook import leggi_log, ottieni_logger
from app.models.envelope import now_iso

_log = ottieni_logger("diagnostico")

MAX_CAMPIONE = 3  # voci di log di esempio conservate nella diagnosi
MAX_ERRORI_SCANSIONE = 200  # tetto di voci d'errore lette per ciclo di analisi
STATI_APERTI = ("proposta",)


class DiagnosticoError(Exception):
    """L'analisi non è producibile (contesto o risposta LLM inutilizzabili)."""


class Diagnostico:
    def __init__(self, dal: DAL, gateway: Gateway) -> None:
        self.dal = dal
        self.data_dir = dal.data_dir
        self.gateway = gateway
        self.wf_dir = self.data_dir / "workflows" / "diagnostico"

    # ------------------------------------------------------------- pubblico

    def analizza_recenti(
        self, giorni: int = 1, limite: int = MAX_ERRORI_SCANSIONE
    ) -> list[dict[str, Any]]:
        """Diagnostica ogni firma d'errore distinta nei log recenti.

        Le firme già aperte vengono solo aggiornate (conteggio), le nuove
        analizzate. Robusto: un fallimento su un cluster non ferma gli altri.
        """
        errori = leggi_log(self.data_dir, livello_min="ERROR", giorni=giorni, limite=limite)
        clusters: dict[str, list[dict[str, Any]]] = {}
        for voce in errori:
            if voce.get("fase") == "diagnostico":
                continue  # mai diagnosticare la diagnostica (niente cicli)
            f = str(voce.get("firma") or calcola_firma(voce))
            clusters.setdefault(f, []).append(voce)
        risultati: list[dict[str, Any]] = []
        for f, voci in clusters.items():
            try:
                risultati.append(self.diagnostica_cluster(f, voci))
            except (DiagnosticoError, GatewayError, DalError) as exc:
                _log.error("analisi della firma %s fallita: %s", f, exc)
        return risultati

    def diagnostica_cluster(
        self, firma: str, voci: list[dict[str, Any]], forza: bool = False
    ) -> dict[str, Any]:
        """Diagnosi (nuova o aggiornata) per un cluster di errori con la stessa firma."""
        if not voci:
            raise DiagnosticoError("cluster vuoto")
        esistente = self._diagnosi_aperta(firma)
        if esistente and not forza:
            return self._aggiorna_conteggio(esistente, voci)

        rappresentativa = voci[0]  # leggi_log: dalla più recente
        sorgenti = codebase.sorgenti_per_voce(rappresentativa)
        artefatti = self._artefatti_dato(rappresentativa)
        analisi = self._analizza_llm(rappresentativa, len(voci), sorgenti, artefatti)

        ts = [str(v.get("ts", "")) for v in voci if v.get("ts")]
        diagnosi = {
            "firma": firma,
            "stato": "proposta",
            "deciso_da": None,
            "fase": rappresentativa.get("fase"),
            "livello": rappresentativa.get("livello"),
            "messaggio": rappresentativa.get("messaggio"),
            "run_id": rappresentativa.get("run_id"),
            "workflow": rappresentativa.get("workflow"),
            "documento": rappresentativa.get("documento"),
            "n_occorrenze": len(voci),
            "prima_occorrenza": min(ts) if ts else None,
            "ultima_occorrenza": max(ts) if ts else None,
            "categoria": analisi["categoria"],
            "titolo": analisi["titolo"],
            "analisi": analisi["analisi"],
            "causa_radice": analisi["causa_radice"],
            "proposta": analisi["proposta"],
            "azione_suggerita": analisi["azione_suggerita"],
            "file_coinvolti": analisi["file_coinvolti"],
            "confidenza": analisi["confidenza"],
            "eccezione": rappresentativa.get("eccezione"),
            "campione": voci[:MAX_CAMPIONE],
            "sorgenti_lette": sorgenti,
            "creato": now_iso(),
        }
        salvata = self.dal.salva_diagnosi(diagnosi)
        _log.info(
            "diagnosi %s aperta (%s) per la firma %s",
            salvata["id"],
            salvata["categoria"],
            firma,
        )
        return salvata

    def risolvi(self, diagnosi_id: str, deciso_da: str) -> dict[str, Any]:
        diagnosi = self.dal.leggi_diagnosi(diagnosi_id)
        return self.dal.aggiorna_diagnosi(
            {**diagnosi, "stato": "risolta", "deciso_da": deciso_da}, "risolvi"
        )

    def archivia(self, diagnosi_id: str, deciso_da: str) -> dict[str, Any]:
        diagnosi = self.dal.leggi_diagnosi(diagnosi_id)
        return self.dal.aggiorna_diagnosi(
            {**diagnosi, "stato": "archiviata", "deciso_da": deciso_da}, "archivia"
        )

    # ------------------------------------------------------------- interni

    def _diagnosi_aperta(self, firma: str) -> dict[str, Any] | None:
        for diagnosi in self.dal.list_diagnosi():
            if diagnosi.get("firma") == firma and diagnosi.get("stato") in STATI_APERTI:
                return diagnosi
        return None

    def _aggiorna_conteggio(
        self, diagnosi: dict[str, Any], voci: list[dict[str, Any]]
    ) -> dict[str, Any]:
        ts = [str(v.get("ts", "")) for v in voci if v.get("ts")]
        aggiornata = {
            **diagnosi,
            "n_occorrenze": int(diagnosi.get("n_occorrenze", 0)) + len(voci),
            "ultima_occorrenza": max([diagnosi.get("ultima_occorrenza") or "", *ts]) or None,
        }
        return self.dal.aggiorna_diagnosi(aggiornata, "riscontrata")

    def _artefatti_dato(self, voce: dict[str, Any]) -> dict[str, str]:
        """Skill/manifest/schema del workflow coinvolto (se l'errore ne cita uno)."""
        workflow = voce.get("workflow")
        if not workflow:
            return {}
        wf_root = self.data_dir / "workflows" / str(workflow)
        manifest_path = wf_root / "manifest.yaml"
        if not manifest_path.is_file():
            return {}
        artefatti: dict[str, str] = {}
        try:
            testo_manifest = manifest_path.read_text(encoding="utf-8")
            artefatti["manifest"] = testo_manifest
            manifest = yaml.safe_load(testo_manifest) or {}
        except (OSError, yaml.YAMLError):
            return artefatti
        for step in manifest.get("steps", []):
            if isinstance(step, dict) and "skill" in step:
                skill_path = wf_root / step["skill"]
                if skill_path.is_file():
                    artefatti["skill"] = skill_path.read_text(encoding="utf-8")
                schema_rel = step.get("output_schema")
                schema_path = self.data_dir / str(schema_rel) if schema_rel else None
                if schema_path and schema_path.is_file():
                    artefatti["schema"] = schema_path.read_text(encoding="utf-8")
                break
        return artefatti

    def _analizza_llm(
        self,
        voce: dict[str, Any],
        n_occorrenze: int,
        sorgenti: list[dict[str, Any]],
        artefatti: dict[str, str],
    ) -> dict[str, Any]:
        skill = (self.wf_dir / self._manifest()["skill"]).read_text(encoding="utf-8")
        prompt = self._prompt(voce, n_occorrenze, sorgenti, artefatti)
        risposta = self.gateway.complete(
            tier=self._manifest().get("tier", "T1"),
            messages=[
                {"role": "system", "content": skill},
                {"role": "user", "content": prompt},
            ],
        )
        dato = estrai_json(risposta.text or "")
        if not isinstance(dato, dict) or not dato.get("categoria"):
            raise DiagnosticoError("la diagnosi non contiene una categoria")
        categoria = str(dato["categoria"]).strip().lower()
        if categoria not in ("dato", "architettura"):
            categoria = "architettura"  # nel dubbio, sola analisi
        azione = dato.get("azione_suggerita")
        if not isinstance(azione, dict):
            azione = {"tipo": "nessuna", "workflow": None, "dettaglio": ""}
        return {
            "categoria": categoria,
            "titolo": str(dato.get("titolo") or voce.get("messaggio") or "Errore"),
            "analisi": str(dato.get("analisi") or ""),
            "causa_radice": str(dato.get("causa_radice") or ""),
            "proposta": str(dato.get("proposta") or ""),
            "azione_suggerita": {
                "tipo": str(azione.get("tipo") or "nessuna"),
                "workflow": azione.get("workflow") or voce.get("workflow"),
                "dettaglio": str(azione.get("dettaglio") or ""),
            },
            "file_coinvolti": [str(f) for f in (dato.get("file_coinvolti") or [])],
            "confidenza": _confidenza(dato.get("confidenza")),
        }

    def _prompt(
        self,
        voce: dict[str, Any],
        n_occorrenze: int,
        sorgenti: list[dict[str, Any]],
        artefatti: dict[str, str],
    ) -> str:
        parti = [
            "## Errore da diagnosticare",
            f"- fase: {voce.get('fase')}",
            f"- livello: {voce.get('livello')}",
            f"- occorrenze: {n_occorrenze}",
            f"- messaggio: {voce.get('messaggio')}",
        ]
        for chiave in ("run_id", "workflow", "documento", "step"):
            if voce.get(chiave):
                parti.append(f"- {chiave}: {voce[chiave]}")
        parti.append(f"\nIndizio automatico sulla categoria: {self._indizio(voce, sorgenti)}")

        eccezione = voce.get("eccezione")
        if isinstance(eccezione, str) and eccezione:
            parti += ["\n## Traceback", "```", eccezione[:4000], "```"]

        if sorgenti:
            parti.append("\n## Codice sorgente coinvolto (cornice dell'applicazione)")
            for s in sorgenti:
                intest = f"FILE {s['file']}" + (f" (riga {s['lineno']})" if s.get("lineno") else "")
                parti += [f"\n{intest}", "```python", str(s["estratto"]), "```"]

        for nome, contenuto in artefatti.items():
            parti += [f"\n## Artefatto-dato: {nome}", "```", contenuto[:4000], "```"]

        parti.append("\nProduci ora la diagnosi nel formato JSON richiesto.")
        return "\n".join(parti)

    @staticmethod
    def _indizio(voce: dict[str, Any], sorgenti: list[dict[str, Any]]) -> str:
        """Indizio deterministico: solo un suggerimento, l'LLM decide."""
        ha_traceback = bool(voce.get("eccezione"))
        if voce.get("workflow") and not ha_traceback:
            return "probabile 'dato' (errore in un workflow, senza eccezione di codice)"
        if ha_traceback and sorgenti:
            return "probabile 'architettura' (eccezione nel codice-cornice)"
        return "incerto (valuta i fatti)"

    def _manifest(self) -> dict[str, Any]:
        percorso = self.wf_dir / "manifest.yaml"
        if not percorso.is_file():
            raise DiagnosticoError("manifest del diagnostico assente (rifare il seed)")
        return yaml.safe_load(percorso.read_text(encoding="utf-8")) or {}


def _confidenza(valore: Any) -> float:
    try:
        return max(0.0, min(1.0, float(valore)))
    except (TypeError, ValueError):
        return 0.0
