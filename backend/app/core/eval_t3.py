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

import hashlib
import json
import os
import re
from copy import deepcopy
from typing import Any

import yaml

from app.core.dal import DAL
from app.core.dataset import toolcalls_validati
from app.core.gateway import Gateway, GatewayError, ModelloNonConfigurato
from app.core.logbook import ottieni_logger
from app.core.runtime import CONTRATTO_OUTPUT, schema_contratto
from app.core.tools import ocr_pdf
from app.core.tools.base import ToolError
from app.core.tracer import leggi_eventi

# Soglia di accuratezza (argomenti) sotto cui un workflow non è pronto per T3.
SOGLIA_PRONTO = 0.9

# Il segnaposto che ``tracer.sanitizza`` lascia al posto delle stringhe lunghe
# (i base64 delle immagini): ``<184320 caratteri, sha256:ab12cd34ef56>``.
SEGNAPOSTO = re.compile(r"^<\d+ caratteri, sha256:[0-9a-f]+>$")
# Lo stesso, ma catturando l'impronta: serve a *verificare* una ricostruzione.
IMPRONTA = re.compile(r"^<(\d+) caratteri, sha256:([0-9a-f]+)>$")

# Un T3 fine-tuned su un modello piccolo può non avere torre visiva (è il caso di
# FunctionGemma 270M). Con ``LLM_T3_SOLO_TESTO=1`` le pagine vengono offerte come
# **testo** invece che come immagini — a *entrambi* i tier, altrimenti il confronto
# misurerebbe la modalità e non il modello. Sta nell'ambiente come i nomi dei
# modelli: mai deciso nel codice.
ENV_SOLO_TESTO = "LLM_T3_SOLO_TESTO"

_log = ottieni_logger("eval_t3")


def solo_testo() -> bool:
    return os.environ.get(ENV_SOLO_TESTO, "").strip().lower() in ("1", "true", "si", "sì")


def _impronta(testo: str) -> str:
    """Lo stesso digest che usa ``tracer.sanitizza`` (primi 12 char dello sha256)."""
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()[:12]


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
        # Prompt di sistema rimessi al loro posto (e verificati), e prompt per cui
        # non si è potuto: la differenza fra una misura pulita e una penalizzata.
        self._prompt_reidratati = 0
        self._solo_testo = solo_testo()

    # ------------------------------------------------- re-idratazione dei prompt

    def _prompt_del_workflow(self, workflow: str) -> list[str]:
        """I due prompt di sistema che il runtime compone per quel workflow.

        Stessa composizione di ``runtime._estrai_su_tier``: la skill e il contratto
        di output sullo schema dell'entità. Sono i due testi che ``tracer.sanitizza``
        riduce a impronta, perché superano i 400 caratteri.
        """
        nome = workflow.split("@")[0]
        manifest_path = self.dal.data_dir / "workflows" / nome / "manifest.yaml"
        if not manifest_path.is_file():
            return []
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            step = next((s for s in manifest.get("steps") or [] if "skill" in s), None)
            if not step:
                return []
            skill = (manifest_path.parent / step["skill"]).read_text(encoding="utf-8")
            schema = json.loads(
                (self.dal.data_dir / step["output_schema"]).read_text(encoding="utf-8")
            )
        except (OSError, yaml.YAMLError, json.JSONDecodeError, KeyError) as exc:
            _log.warning("prompt di %s non ricostruibili: %s", workflow, exc)
            return []
        contratto = CONTRATTO_OUTPUT.format(
            schema=json.dumps(schema_contratto(schema), ensure_ascii=False)
        )
        return [skill, contratto]

    def _reidrata_prompt(self, esempio: dict[str, Any]) -> list[dict[str, Any]]:
        """Rimette i prompt di sistema veri al posto delle impronte, **verificando**.

        Il repo dati conserva ancora la skill e lo schema, quindi il testo si
        ricostruisce; ma la skill può essere stata cambiata dall'Improver dopo il
        run, e un prompt *diverso* è peggio di un prompt troncato: falserebbe la
        misura invece di limitarla. Quindi si sostituisce **solo** se il digest del
        testo ricostruito coincide con quello lasciato nel trace. Se non coincide,
        l'impronta resta e l'esempio finisce fra i ``prompt_troncati``, come prima.
        """
        candidati = self._prompt_del_workflow(str(esempio.get("workflow") or ""))
        if not candidati:
            return esempio["messages"]
        per_impronta = {_impronta(testo): testo for testo in candidati}

        messaggi = deepcopy(esempio["messages"])
        for messaggio in messaggi:
            contenuto = messaggio.get("content")
            if messaggio.get("role") != "system" or not isinstance(contenuto, str):
                continue
            trovato = IMPRONTA.match(contenuto)
            if not trovato:
                continue
            testo = per_impronta.get(trovato.group(2))
            if testo is not None:
                messaggio["content"] = testo
                self._prompt_reidratati += 1
        return messaggi

    # ------------------------------------------------------ pagine come testo

    def _pagine_testuali(self, esempio: dict[str, Any]) -> list[dict[str, Any]] | None:
        """Sostituisce le immagini delle pagine con il loro **testo**.

        Serve per un T3 senza torre visiva. Cosa si perde va messo in conto: il
        layout (su una fattura la ritenuta è in calce, e quello è un indizio) e le
        tabelle, che si appiattiscono. Su un documento scansionato lo strato
        testuale non c'è: si torna ``None`` e l'esempio è dichiarato non
        rigiocabile, invece di misurare il modello su una pagina vuota.
        """
        blob = self._originale(esempio)
        if blob is None:
            return None
        try:
            pagine = ocr_pdf.testo_pagine(self.dal.data_dir, blob)
        except (ToolError, OSError) as exc:
            _log.warning("testo non estraibile da %s: %s", blob, exc)
            return None
        if not any(pagine):
            return None  # scansione senza strato testuale: servirebbe un OCR vero

        messaggi = deepcopy(esempio["messages"])
        sostituite = 0
        for messaggio in messaggi:
            contenuto = messaggio.get("content")
            if not isinstance(contenuto, list):
                continue
            nuove_parti = []
            for parte in contenuto:
                if isinstance(parte, dict) and parte.get("type") == "image_url":
                    if sostituite < len(pagine):
                        nuove_parti.append(
                            {"type": "text", "text": pagine[sostituite]}
                        )
                    sostituite += 1
                else:
                    nuove_parti.append(parte)
            messaggio["content"] = nuove_parti
        if sostituite != len(pagine):
            return None  # pagine e segnaposto non combaciano: non si indovina
        return messaggi

    def _originale(self, esempio: dict[str, Any]) -> str | None:
        """Il blob del documento di quel run, se è ancora nel repo dati."""
        run_id = esempio.get("run_id")
        if not run_id:
            return None
        avvio = next(
            (e for e in leggi_eventi(self.dal.data_dir, str(run_id), {"run_start"})), None
        )
        blob = (avvio or {}).get("input")
        if not blob or not (self.dal.data_dir / str(blob)).is_file():
            return None
        return str(blob)

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

        Con ``LLM_T3_SOLO_TESTO=1`` le pagine diventano **testo** invece di
        immagini (:meth:`_pagine_testuali`): è l'unico modo di valutare un T3 senza
        torre visiva. Anche i prompt di sistema vengono rimessi al loro posto
        (:meth:`_reidrata_prompt`), perché valutare su una skill svuotata misura
        qualcos'altro — e il modello locale, se è stato addestrato sulla skill
        intera, la troverebbe irriconoscibile.
        """
        self._scartati = 0
        self._troncati = 0
        self._prompt_reidratati = 0
        esempi = []
        for es in toolcalls_validati(self.dal):
            if not (es.get("messages") and es.get("tools")):
                continue
            if not (es.get("tool_call") or {}).get("name"):
                continue
            es = {**es, "messages": self._reidrata_prompt(es)}
            if _immagini_oscurate(es["messages"]):
                messaggi = (
                    self._pagine_testuali(es) if self._solo_testo else self._reidrata(es)
                )
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
            # Quanti prompt di sistema si è riusciti a rimettere interi, verificando
            # l'impronta: se è 0 su un set non vuoto, la skill nel repo non è più
            # quella con cui i run sono girati e il confronto vale meno.
            "prompt_reidratati": self._prompt_reidratati,
            # In che modalità sono state offerte le pagine. Va dichiarato: la stessa
            # misura su immagini o su testo non dà lo stesso numero, e il testo
            # perde il layout.
            "modalita_documento": "testo" if self._solo_testo else "immagini",
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
