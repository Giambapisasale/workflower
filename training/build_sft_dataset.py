"""Da `data/traces` a un dataset SFT davvero addestrabile per FunctionGemma.

L'export del prodotto (`GET /api/dataset/finetuning.jsonl`) **non** è addestrabile
così com'è. Tre ragioni strutturali, tutte risolte qui:

1. **Il log è sanitizzato.** `tracer.sanitizza` sostituisce ogni stringa oltre 400
   caratteri con `<N caratteri, sha256:…>`. In `toolcalls.jsonl` questo colpisce i
   due prompt di sistema **e** i messaggi `tool` (il risultato di `cerca_fornitore`
   serializzato supera la soglia): il prefisso non è ricostruibile. Nel **trace**,
   invece, i risultati sono strutture con valori corti e restano interi — quindi la
   conversazione si ricostruisce da lì, e i prompt di sistema si **re-idratano** dal
   repo dati (`workflows/*/skills/*.md` + `CONTRATTO_OUTPUT` sullo schema).
   La ricostruzione è **verificata**: si ricalcola lo stesso sha256 del segnaposto,
   e se non combacia l'esempio viene scartato invece di entrare nel training con un
   prompt sbagliato.

2. **Le pagine sono immagini.** L'estrazione è multimodale (`ocr_pdf` → PNG), ma
   FunctionGemma 270M è **solo testo**. Qui l'immagine è sostituita dal *testo*
   della pagina (strato testuale del PDF, via pymupdf). È una decisione di
   progetto, non un dettaglio: T3 impara a estrarre da testo, quindi sui documenti
   scansionati a valle servirà un OCR vero.

3. **`salva_bozza` è loggato senza `messages`** (in `runtime._salva` il tracer è
   chiamato senza contesto): nel dataset l'esempio più prezioso — "dato il
   documento, emetti l'entità strutturata" — arriverebbe con input vuoto.

In più il **target** di `salva_bozza` non è la bozza estratta ma i dati
**validati** dall'ufficio: se l'ufficio ha corretto un campo si addestra sulla
correzione, non sull'errore.

    python build_sft_dataset.py --out sft.jsonl
"""

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

BACKEND = Path(r"C:\aitho\workflower\backend")
sys.path.insert(0, str(BACKEND))

import yaml  # noqa: E402
from app.core.dal import DAL, TIPI_INGRESSO  # noqa: E402
from app.core.runtime import CONTRATTO_OUTPUT, schema_contratto  # noqa: E402

SEGNAPOSTO = re.compile(r"<(\d+) caratteri, sha256:([0-9a-f]{12})>")
MAX_RISULTATO = 2000  # i risultati dei lookup entrano nel prompt, non serve di più


def digest(testo: str) -> str:
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()[:12]


def testo_documento(data_dir: Path, blob: str) -> str | None:
    """Strato testuale del documento caricato: sostituisce le pagine PNG."""
    percorso = data_dir / blob
    if not percorso.is_file():
        return None
    try:
        import pymupdf

        with pymupdf.open(percorso) as documento:
            pagine = [pagina.get_text() for pagina in documento]
    except Exception:  # noqa: BLE001
        return None
    return "\n\n".join(p.strip() for p in pagine if p.strip()) or None


class Costruttore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.motivi: Counter[str] = Counter()
        self._prompt_cache: dict[str, tuple[str, str, list[str]]] = {}

    # ------------------------------------------------------- prompt del workflow

    def prompt_workflow(self, workflow: str) -> tuple[str, str, list[str]] | None:
        """(skill, contratto di output, nomi dei tool dello step) per un workflow.

        È la stessa composizione di ``runtime._estrai_su_tier``: due messaggi di
        sistema, skill e contratto. Se cambiassero lì, il digest non combacerebbe
        più e gli esempi verrebbero scartati — il controllo è voluto.
        """
        if workflow in self._prompt_cache:
            return self._prompt_cache[workflow]
        manifest_path = self.data_dir / "workflows" / workflow / "manifest.yaml"
        if not manifest_path.is_file():
            self.motivi["manifest del workflow assente"] += 1
            return None
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        step = next((s for s in manifest.get("steps") or [] if "skill" in s), None)
        if not step:
            self.motivi["nessuno step con skill"] += 1
            return None
        skill = (manifest_path.parent / step["skill"]).read_text(encoding="utf-8")
        schema = json.loads((self.data_dir / step["output_schema"]).read_text(encoding="utf-8"))
        contratto = CONTRATTO_OUTPUT.format(
            schema=json.dumps(schema_contratto(schema), ensure_ascii=False)
        )
        valore = (skill, contratto, list(step.get("tools") or []))
        self._prompt_cache[workflow] = valore
        return valore

    def verifica_prompt(self, record_toolcall: dict, skill: str, contratto: str) -> bool:
        """I due segnaposto di sistema in `toolcalls.jsonl` combaciano col repo?"""
        attesi = {digest(skill), digest(contratto)}
        trovati = set()
        for messaggio in record_toolcall.get("messages") or []:
            if messaggio.get("role") != "system":
                continue
            trovato = SEGNAPOSTO.search(str(messaggio.get("content") or ""))
            if trovato:
                trovati.add(trovato.group(2))
            else:
                trovati.add(digest(str(messaggio.get("content"))))
        return bool(trovati) and trovati <= attesi

    # ------------------------------------------------- ricostruzione di un run

    def esempi_del_run(
        self, trace: Path, tools_per_nome: dict[str, dict], validati: dict[str, dict]
    ) -> list[dict]:
        eventi: list[dict] = []
        for riga in trace.read_text(encoding="utf-8").splitlines():
            if riga.strip():
                try:
                    eventi.append(json.loads(riga))
                except json.JSONDecodeError:
                    continue

        avvio = next((e for e in eventi if e.get("evento") == "run_start"), None)
        fine = next((e for e in eventi if e.get("evento") == "run_end"), None)
        if not avvio or not fine or fine.get("outcome") != "ok":
            self.motivi["run senza esito ok"] += 1
            return []

        workflow, versione, blob = avvio["workflow"], avvio.get("version"), avvio["input"]
        prompt = self.prompt_workflow(workflow)
        if prompt is None:
            return []
        skill, contratto, nomi_tool = prompt

        testo = testo_documento(self.data_dir, blob)
        if testo is None:
            self.motivi["testo del documento non estraibile"] += 1
            return []

        schemi = [tools_per_nome[n] for n in nomi_tool if n in tools_per_nome]
        messaggi: list[dict[str, Any]] = [
            {"role": "system", "content": skill},
            {"role": "system", "content": contratto},
            {"role": "user", "content": f"Documento da elaborare: {blob}"},
        ]

        # i tool_call che seguono una llm_call appartengono a quel turno assistant
        turni: list[list[dict]] = []
        for evento in eventi:
            if evento.get("evento") == "llm_call" and evento.get("step") != "salva":
                turni.append([])
            elif evento.get("evento") == "tool_call" and evento.get("step") != "salva":
                if turni:
                    turni[-1].append(evento)
        turni = [t for t in turni if t]

        esempi: list[dict] = []
        contatore = 0
        for chiamate in turni:
            esempi.append(
                {
                    "workflow": f"{workflow}@{versione}",
                    "tipo_esempio": "routing" if chiamate[0]["name"] == "ocr_pdf" else "lookup",
                    "tools": schemi,
                    "messages": [dict(m) for m in messaggi],
                    "tool_calls": [
                        {"name": c["name"], "args": c.get("args") or {}} for c in chiamate
                    ],
                }
            )
            # avanza la conversazione: assistant con le sue chiamate, poi i risultati
            identificativi = []
            for chiamata in chiamate:
                contatore += 1
                identificativi.append(f"call_{contatore}")
            messaggi.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": identificativo,
                            "type": "function",
                            "function": {
                                "name": chiamata["name"],
                                "arguments": json.dumps(
                                    chiamata.get("args") or {}, ensure_ascii=False
                                ),
                            },
                        }
                        for identificativo, chiamata in zip(identificativi, chiamate, strict=True)
                    ],
                }
            )
            for identificativo, chiamata in zip(identificativi, chiamate, strict=True):
                if chiamata["name"] == "ocr_pdf":
                    messaggi.append(
                        {
                            "role": "tool",
                            "tool_call_id": identificativo,
                            "content": "Pagine convertite: il testo è nel messaggio successivo.",
                        }
                    )
                    messaggi.append(
                        {"role": "user", "content": f"Pagine del documento:\n\n{testo}"}
                    )
                else:
                    messaggi.append(
                        {
                            "role": "tool",
                            "tool_call_id": identificativo,
                            "content": json.dumps(
                                chiamata.get("result"), ensure_ascii=False
                            )[:MAX_RISULTATO],
                        }
                    )

        # L'esempio di estrazione. Il target NON è una tool call `salva_bozza`:
        # quella la compone il runtime (`_step_salva`), che ci aggiunge `stato`,
        # `origine`, `workflow` e `run_id` — addestrare su quelli insegnerebbe al
        # modello a inventarsi un run_id esadecimale. Lo dice anche l'harness del
        # prodotto, che esclude `salva_bozza` perché "invocato dal runtime e non dal
        # modello" (eval_t3.py). L'uscita vera del modello è il JSON del contratto:
        # {dati, confidence}. `dati` viene dall'entità VALIDATA dall'ufficio.
        salva = next(
            (
                e
                for e in eventi
                if e.get("evento") == "tool_call" and e.get("name") == "salva_bozza"
            ),
            None,
        )
        if salva:
            argomenti = salva.get("args") or {}
            chiave = f"{avvio.get('run_id') or trace.stem}|{argomenti.get('tipo')}"
            dato_validato = validati.get(chiave)
            uscita = {
                "dati": dato_validato if dato_validato is not None else argomenti.get("dati"),
                "confidence": argomenti.get("confidence") or {},
            }
            esempi.append(
                {
                    "workflow": f"{workflow}@{versione}",
                    "tipo_esempio": "estrazione",
                    "tools": schemi,
                    "messages": [dict(m) for m in messaggi],
                    "tool_calls": [],
                    "testo_atteso": json.dumps(uscita, ensure_ascii=False),
                    "corretto_dall_ufficio": dato_validato is not None
                    and dato_validato != argomenti.get("dati"),
                }
            )
        return esempi


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(r"C:\aitho\workflower\data"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    dal = DAL(args.data)
    costruttore = Costruttore(args.data)

    # gli schemi dei tool, presi dai log: sono già nel formato OpenAI del gateway
    tools_per_nome: dict[str, dict] = {}
    percorso_toolcalls = args.data / "dataset" / "toolcalls.jsonl"
    record_per_run: dict[str, list[dict]] = {}
    for riga in percorso_toolcalls.read_text(encoding="utf-8").splitlines():
        if not riga.strip():
            continue
        record = json.loads(riga)
        record_per_run.setdefault(record.get("run_id", ""), []).append(record)
        for schema in record.get("tools") or []:
            nome = (schema.get("function") or {}).get("name")
            if nome:
                tools_per_nome.setdefault(nome, schema)
    print(f"schemi di tool disponibili: {sorted(tools_per_nome)}")

    # run validati dall'ufficio + il dato validato (target di salva_bozza)
    run_validati: set[str] = set()
    validati: dict[str, dict] = {}
    for tipo in TIPI_INGRESSO:
        for envelope in dal.list_all(tipo):
            if envelope.stato == "validato" and envelope.meta.run_id:
                run_validati.add(envelope.meta.run_id)
                validati[f"{envelope.meta.run_id}|{tipo}"] = envelope.dati
    print(f"run validati dall'ufficio: {len(run_validati)}")

    esempi: list[dict] = []
    verificati = non_verificati = 0
    for run_id in sorted(run_validati):
        trace = next((args.data / "traces").glob(f"*/*/{run_id}.jsonl"), None)
        if trace is None:
            costruttore.motivi["trace assente"] += 1
            continue
        del_run = costruttore.esempi_del_run(trace, tools_per_nome, validati)
        if not del_run:
            continue
        # auto-verifica: i prompt re-idratati devono avere lo stesso sha256 del log
        record = next((r for r in record_per_run.get(run_id, []) if r.get("messages")), None)
        prompt = costruttore.prompt_workflow(del_run[0]["workflow"].split("@")[0])
        if record and prompt and costruttore.verifica_prompt(record, prompt[0], prompt[1]):
            verificati += 1
        elif record:
            non_verificati += 1
            costruttore.motivi["prompt non verificabile col log (skill cambiata?)"] += 1
            continue
        esempi.extend(del_run)

    args.out.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in esempi) + "\n", encoding="utf-8"
    )

    print(f"\nesempi scritti: {len(esempi)} → {args.out}")
    print(f"run con prompt verificato via sha256: {verificati} (non verificati: {non_verificati})")
    print("\nper tipo di esempio:")
    for tipo, n in Counter(e["tipo_esempio"] for e in esempi).most_common():
        print(f"  {tipo:14s} {n}")
    print("\nper workflow:")
    for wf, n in Counter(e["workflow"] for e in esempi).most_common():
        print(f"  {wf:24s} {n}")
    print("\ntool nel target:")
    for nome, n in Counter(
        c["name"] for e in esempi for c in e["tool_calls"]
    ).most_common():
        print(f"  {nome:16s} {n}")
    testuali = sum(1 for e in esempi if e.get("testo_atteso"))
    print(f"  (target testuale, JSON del contratto): {testuali}")
    corretti = sum(1 for e in esempi if e.get("corretto_dall_ufficio"))
    print(f"\ntarget presi dalla correzione dell'ufficio (bozza ≠ validato): {corretti}")
    if costruttore.motivi:
        print("\nmotivi di scarto:")
        for motivo, n in costruttore.motivi.most_common():
            print(f"  {motivo:48s} {n}")
    lunghezze = sorted(len(json.dumps(e["messages"], ensure_ascii=False)) for e in esempi)
    if lunghezze:
        print(f"\nprompt (caratteri): mediana {lunghezze[len(lunghezze) // 2]}, max {lunghezze[-1]}")


if __name__ == "__main__":
    main()
