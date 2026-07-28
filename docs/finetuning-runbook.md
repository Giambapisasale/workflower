# Runbook: fine-tuning del tier locale T3 (FunctionGemma)

Questo runbook chiude l'anello del **costo marginale** (§3.1, §3.7): distillare i
run già validati in un modello locale piccolo che gestisce i workflow maturi a
costo ~0, con T1 come rete di sicurezza (escalation). **Non è eseguito nel repo**:
non ci sono dipendenze GPU né pesi versionati. T3 si accende quando il modello è
pronto — prima si *misura*, poi si *instrada*.

> Regola d'oro: non si instrada un workflow su T3 finché l'harness di valutazione
> (`GET /api/dataset/eval-t3`, milestone M18) non lo dà "pronto" — accuratezza
> function-calling alta **e** nessuna regressione rispetto a T1.

## 0. Prerequisiti

- Esempi validati a sufficienza per i workflow candidati (li produce l'uso
  normale: ogni bozza validata diventa materia prima, §3.7).
- Una GPU per l'addestramento LoRA (fuori da questo repo/ambiente). Su una **RTX
  3080 Laptop da 8 GB** basta e avanza: picco misurato **1,87 GiB**, 3 epoche su
  216 esempi in **11 minuti**. Aspettati throttling termico su un portatile (88 °C
  e `clocks_throttle_reasons=0x20`): il tempo per step raddoppia, il run finisce.
- I pesi di FunctionGemma sono **gated**: accetta la licenza su
  <https://huggingface.co/google/functiongemma-270m-it> e autenticati una volta con
  `hf auth login`. L'id corretto è `google/functiongemma-270m-it` (270M, Gemma 3
  text-only, vocab 262.146).
- Un runtime di inferenza locale con API OpenAI-compatibile: Ollama, llama.cpp
  (`server`), o vLLM.

## 1. Esporta il dataset — e ricostruiscilo

Il dataset builder è già nel prodotto: solo le tool call dei run **validati**
(mai gli errori) diventano esempi.

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
     http://localhost:8000/api/dataset/finetuning.jsonl > finetuning.jsonl
```

Ogni riga è `{workflow, tools, messages, tool_call}`. **Ma non è addestrabile
così com'è**, e va saputo prima di perdere una giornata:

1. `tracer.sanitizza` sostituisce ogni stringa oltre 400 caratteri con
   `<N caratteri, sha256:…>`. Colpisce i due prompt di sistema **e** i messaggi
   `tool` (il risultato di `cerca_fornitore` serializzato supera la soglia): il
   prefisso non è ricostruibile da `toolcalls.jsonl`. Nei **trace**
   (`data/traces/AAAA/MM/<run_id>.jsonl`) i risultati sono strutture con valori
   corti e restano interi: ricostruisci da lì.
2. I prompt di sistema si **re-idratano** dal repo dati (la skill dichiarata dallo
   step + `CONTRATTO_OUTPUT` sullo schema) e la ricostruzione si **verifica**
   ricalcolando lo stesso sha256 del segnaposto. Se non combacia (skill cambiata
   dall'Improver dopo il run), scarta l'esempio: un prompt diverso è peggio di uno
   assente. È la stessa logica di `EvalT3._reidrata_prompt`.
3. Le pagine sono **immagini** PNG (`ocr_pdf`), e FunctionGemma 270M è solo testo:
   sostituiscile col testo della pagina (`ocr_pdf.testo_pagine`). Si perde il
   layout — su una fattura "Ritenuta d'acconto" in calce è un indizio *perché* è in
   calce — e sugli scansionati serve un OCR vero.
4. `salva_bozza` è loggato **senza `messages`** (`runtime._step_salva` chiama il
   tracer senza contesto). E comunque **non è un target valido**: quella chiamata
   la compone il runtime, aggiungendoci `stato`, `origine`, `workflow` e `run_id` —
   addestrare su quelli insegna al modello a inventarsi un run_id esadecimale. Per
   l'estrazione il target giusto è l'uscita vera del modello: il JSON del
   contratto `{dati, confidence}`, con `dati` preso dall'entità **validata**
   dall'ufficio (se l'ufficio ha corretto un campo, si addestra sulla correzione).
   Lo stesso principio è già in `eval_t3.esempi_valutabili`, che esclude
   `salva_bozza` perché "invocato dal runtime e non dal modello".

## 2. Addestra (LoRA) — fuori dal repo

```python
# trl 1.9.x / peft 0.19.x / transformers 5.14.x, verificato
from liger_kernel.transformers import apply_liger_kernel_to_gemma3_text
apply_liger_kernel_to_gemma3_text()          # PRIMA di costruire il trainer

trainer = SFTTrainer(
    model="google/functiongemma-270m-it",
    args=SFTConfig(
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        max_length=4096,
        completion_only_loss=True,           # loss solo sul target, non sulla skill
        gradient_checkpointing=True,
        bf16=True,
        model_init_kwargs={"attn_implementation": "sdpa"},
    ),
    train_dataset=ds,
    peft_config=LoraConfig(r=16, lora_alpha=32, task_type="CAUSAL_LM",
                           target_modules="all-linear"),
)
```

Due trappole che costano ore:

- **`SFTConfig(use_liger_kernel=True)` non fa niente.** In trl 1.9.1 il campo
  esiste, è documentato ("reduces memory by ~60%") e viene accettato senza
  avvisi, ma nel `SFTTrainer` di mainline nessuno lo legge — lo consumano solo i
  trainer sotto `trl/experimental/`. Applica la patch a mano.
- **Senza cross-entropy fusa non ci sta in 8 GB.** Il costo non è nei pesi
  (0,54 GB in bf16) ma nei logit: vocab 262.146 × 3.509 token × 4 byte = 3,7 GB
  per il solo tensore. Misurato su una sequenza da 3.509 token:

  | | picco |
  |---|---|
  | eager + CE standard | 12,66 GB → OOM |
  | sdpa + CE standard | 12,62 GB → OOM |
  | eager + liger | 1,45 GB |
  | **sdpa + liger** | **0,83 GB** |

- Il **chat template** di FunctionGemma vuole gli schemi dei tool **avvolti**
  (`{"type":"function","function":{…}}`: legge `tool.function`) e ogni messaggio
  `tool` con il campo `name`. Ricava il completion per differenza
  (`apply_chat_template` della conversazione intera meno il prompt) invece di
  scrivere a mano il formato delle tool call, e togli il `<start_function_response>`
  che il template appende in coda: non è roba che il modello deve generare.

Fondi l'adattatore ed esporta i pesi nel formato del tuo runtime (es. GGUF per
llama.cpp/Ollama).

### Non fidarti della loss

Su 216 esempi (72 documenti validati) il training riporta `eval_loss` 0,013 e
`mean_token_accuracy` 0,994: sembra risolto. In **generazione libera** sullo
held-out, invece:

| | base | adattato |
|---|---|---|
| routing (`ocr_pdf`) — tool / argomenti | 1/3 · 0/3 | **3/3 · 3/3** |
| lookup (`cerca_*`) — tool / argomenti | 0/6 · 0/6 | **6/6** · 2/6 |
| estrazione — campi esatti | 0/112 | 21/112 |

Quasi tutti i token sono impalcatura JSON prevedibile, quindi la token accuracy
resta altissima anche quando l'estrazione è sbagliata: basta una cifra. Misura
sempre per generazione, e per *campo*, non per token. La lettura: 216 esempi
insegnano **quale tool** chiamare, non **cosa estrarre**.

## 3. Servi il modello in locale

```bash
# Ollama
ollama create functiongemma-workflower -f Modelfile
ollama serve            # espone http://localhost:11434 (OpenAI-compatibile)
```

## 4. Misura PRIMA di accendere

Punta temporaneamente `LLM_T3_MODEL` al modello locale e chiedi il report:

```bash
export LLM_T3_MODEL=ollama/functiongemma-workflower
export LLM_T3_API_BASE=http://localhost:11434
export LLM_T3_SOLO_TESTO=1
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
     "http://localhost:8000/api/dataset/eval-t3" | jq .
```

`LLM_T3_SOLO_TESTO=1` serve quando il candidato **non è multimodale**: l'harness
offre le pagine come testo invece che come immagini, e lo fa per **entrambi** i
tier — altrimenti il verdetto misurerebbe la modalità e non il modello. Il report
lo dichiara in `modalita_documento`.

Guarda `pronti` e `regressioni`. Instrada su T3 **solo** i workflow in `pronti`.
Leggi anche i tre contatori che dicono quanto vale la misura: `non_rigiocabili`
(esempi persi), `prompt_troncati` (prompt arrivati a impronta) e
`prompt_reidratati` (prompt rimessi interi e verificati). Se `prompt_reidratati`
è 0 su un set non vuoto, la skill nel repo non è più quella con cui i run sono
girati: il confronto vale meno di quanto sembra.

## 5. Accendi T3

- Imposta `LLM_T3_MODEL` (e `LLM_T3_API_BASE`) nell'ambiente del backend.
- Nel manifest del workflow maturo, dichiara `tier: T3` (è dato: nessun codice).
- Da quel momento gli step girano su T3 e, su errore/bassa confidence/output
  fuori contratto, **escalano a T1** in automatico. Il costo del tier locale è ~0.

## 6. Sorveglia e ri-addestra

`GET /api/dataset/stats` riporta la **% di escalation per workflow**: è il
termometro del modello locale. Se sale, il modello sta faticando su casi nuovi:
riesporta il dataset (ora più ricco), ripeti dal passo 1. Se un workflow regredisce,
riportalo su T1 (togli `tier: T3` dal manifest) finché il modello non recupera.

La rete di sicurezza è sempre attiva: T3 è un'ottimizzazione, mai un
single-point-of-failure.
