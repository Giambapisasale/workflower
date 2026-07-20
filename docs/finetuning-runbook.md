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
- Una GPU per l'addestramento LoRA (fuori da questo repo/ambiente).
- Un runtime di inferenza locale con API OpenAI-compatibile: Ollama, llama.cpp
  (`server`), o vLLM.

## 1. Esporta il dataset

Il dataset builder è già nel prodotto: solo le tool call dei run **validati**
(mai gli errori) diventano esempi.

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
     http://localhost:8000/api/dataset/finetuning.jsonl > finetuning.jsonl
```

Ogni riga è `{workflow, tools, messages, tool_call}`: il contesto offerto al
modello e la tool call giusta (ground truth). Filtra per il workflow che vuoi
consolidare su T3.

## 2. Addestra (LoRA) — fuori dal repo

Parti da FunctionGemma (o altro modello base con buon function-calling) e
addestra un adattatore LoRA sul formato function-calling degli esempi. In pseudo:

```python
# esempio indicativo (trl/peft), NON eseguito qui
from datasets import load_dataset
from trl import SFTTrainer
from peft import LoraConfig

ds = load_dataset("json", data_files="finetuning.jsonl", split="train")
# formatta messages+tools+tool_call nel template del modello base
trainer = SFTTrainer(
    model="google/functiongemma-base",
    train_dataset=ds,
    peft_config=LoraConfig(r=16, lora_alpha=32, task_type="CAUSAL_LM"),
    # ...iperparametri, split di validazione...
)
trainer.train()
trainer.save_model("functiongemma-workflower-lora")
```

Fondi l'adattatore ed esporta i pesi nel formato del tuo runtime (es. GGUF per
llama.cpp/Ollama).

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
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
     "http://localhost:8000/api/dataset/eval-t3" | jq .
```

Guarda `pronti` e `regressioni`. Instrada su T3 **solo** i workflow in `pronti`.

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
