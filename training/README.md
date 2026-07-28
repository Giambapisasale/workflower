# training/ — il tier T3, fuori dall'app

Questi script **non** fanno parte del prodotto: girano su una macchina con GPU, in
un ambiente separato, e servono a costruire il dataset, addestrare il LoRA su
FunctionGemma 270M e misurare quanto ha imparato. Il prodotto li ignora — il
`Dockerfile` copia solo `backend/` e `frontend/`.

Stanno nel repo perché sono la ricetta, e una ricetta che vive solo in una
cartella temporanea è una ricetta perduta: fino al 28 luglio 2026 esistevano solo
in `~/ft-functiongemma` (WSL) e nello scratchpad di una sessione.

Il ragionamento sta in [`docs/finetuning-runbook.md`](../docs/finetuning-runbook.md);
qui c'è solo cosa lanciare e in che ordine.

## L'ambiente

Non è il `.venv` del backend: torch e trl non c'entrano niente con l'app.

```bash
# in WSL Ubuntu, senza sudo: il python di sistema non ha ensurepip funzionante
~/miniconda3/bin/python -m venv ~/ft-functiongemma/.venv
~/ft-functiongemma/.venv/bin/pip install torch transformers trl peft liger-kernel datasets
```

Verificato con torch 2.13.0+cu130, transformers 5.14.1, trl 1.9.1, peft 0.19.1 su
una RTX 3080 Laptop (8 GB, sm_86, bf16 nativo). Su Linux il wheel torch di PyPI è
già CUDA-enabled: non serve un index-url dedicato.

## L'ordine

```bash
python verifica_accesso.py                       # i pesi sono gated: serve il login HF
python build_sft_dataset.py --out sft.jsonl      # gira dove c'è data/ (Windows va bene)
python ispeziona_esempio.py                     # come arriva davvero al modello
python probe_vram.py                            # cosa ci sta in 8 GB, prima di provarci
python train_lora.py --dataset sft.jsonl --out ./functiongemma-workflower-lora
python valuta_lora.py --lora ./functiongemma-workflower-lora   # base vs adattato
```

`build_sft_dataset.py` legge `data/traces` e il repo dati: l'export
`GET /api/dataset/finetuning.jsonl` **non** è addestrabile così com'è (log
sanitizzato, pagine come immagini, `salva_bozza` senza `messages`) e le tre
correzioni stanno lì, verificate ricalcolando lo sha256 dei segnaposto.

## Cosa non è qui, e va bene

Il dataset (`sft.jsonl`), l'adapter addestrato e `train.log` sono **prodotti**, non
sorgenti: si rifanno lanciando gli script. Non stanno nel repo perché
`build_sft_dataset.py` legge i trace, e i trace cambiano — un dataset committato
oggi sarebbe già vecchio domani, e in più il dataset giusto per la prossima tornata
non è questo (vedi il passo 5 del runbook: prima si consolida in `t_*`, poi si
addestra su «domanda → chiamata a tool»).
