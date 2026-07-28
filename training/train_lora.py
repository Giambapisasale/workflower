"""LoRA su FunctionGemma 270M con gli esempi validati di Workflower (tier T3).

Gira in WSL, su ~/ft-functiongemma/.venv. Iperparametri tarati sugli 8 GB di una
RTX 3080 Laptop: il collo di bottiglia di Gemma 3 270M **non** sono i pesi
(0,54 GB in bf16) ma il tensore dei logits, perché il vocabolario è 262.144
token — `batch × seq × 262144 × 4 byte`. Per questo `use_liger_kernel=True`
(cross-entropy fusa/chunked) e `batch=1` con accumulo: senza, un batch 4 × 2048
chiede da solo più di 8 GB e va in OOM.

Il target della loss è **solo** la tool call da emettere (dataset
prompt/completion → `completion_only_loss`): non si addestra il modello a
riscrivere la skill che ha in input.

    python train_lora.py --dataset sft.jsonl --out ./functiongemma-workflower-lora
    python train_lora.py --dataset sft.jsonl --solo-statistiche   # niente training

Prerequisito: i pesi Gemma sono *gated* su Hugging Face. Serve accettare la
licenza sulla pagina del modello e autenticarsi una volta:

    ~/ft-functiongemma/.venv/bin/hf auth login
"""

import argparse
import json
import random
from pathlib import Path


def applica_liger(modello_id: str) -> None:
    """Applica a mano la cross-entropy fusa di Liger. È la leva che rende
    fattibile l'addestramento su 8 GB — non un'ottimizzazione opzionale.

    Misurato su una sequenza da 3509 token (la più lunga del dataset):

        eager + CE standard   12,66 GB   ← OOM
        sdpa  + CE standard   12,62 GB   ← OOM
        eager + liger          1,45 GB
        sdpa  + liger          0,83 GB   ← questa configurazione

    Il costo è tutto nei logit: 3509 × 262.146 × 4 byte sono 3,7 GB per il solo
    tensore, e la cross-entropy standard ne materializza anche il gradiente e i
    passaggi intermedi. Liger li calcola a blocchi e non li materializza mai.

    **Perché a mano e non con `SFTConfig(use_liger_kernel=True)`**: in trl 1.9.1
    quel campo esiste, è documentato ("reduces memory by ~60%") e viene accettato
    senza un avviso — ma nel `SFTTrainer` di mainline nessuno lo legge (lo
    consumano solo i trainer sotto `trl/experimental/`). Impostarlo dà la
    sensazione di aver ottimizzato e non ottimizza niente.
    """
    from liger_kernel.transformers import monkey_patch
    from transformers import AutoConfig

    tipo = AutoConfig.from_pretrained(modello_id).model_type
    funzione = getattr(monkey_patch, f"apply_liger_kernel_to_{tipo}", None)
    if funzione is None:
        raise SystemExit(
            f"Liger non ha una patch per l'architettura '{tipo}'. Senza cross-entropy "
            f"fusa servono ~12,6 GB e la GPU ne ha 8: rivedere la configurazione "
            f"prima di addestrare."
        )
    funzione()
    print(f"liger applicato: apply_liger_kernel_to_{tipo}")


def carica(percorso: Path) -> list[dict]:
    esempi = []
    for riga in percorso.read_text(encoding="utf-8").splitlines():
        if riga.strip():
            esempi.append(json.loads(riga))
    return esempi


CODA_DA_TOGLIERE = "<start_function_response>"


def messaggio_target_testo(testo: str) -> dict:
    """Il turno assistant quando l'uscita è il JSON del contratto, non una tool call.

    È il caso dell'estrazione: il runtime compone `salva_bozza` da sé, il modello
    consegna `{dati, confidence}` come testo.
    """
    return {"role": "assistant", "content": testo}


def messaggio_target(tool_calls: list[dict]) -> dict:
    """Il turno assistant atteso (una o più tool call), in formato OpenAI.

    Un turno può contenere più chiamate: nell'estrazione fattura il modello invoca
    `cerca_fornitore` e `cerca_cantiere` insieme. Si addestra sul turno intero,
    come lo emetterebbe a inferenza.
    """
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "type": "function",
                "function": {
                    "name": chiamata["name"],
                    "arguments": json.dumps(chiamata["args"], ensure_ascii=False),
                },
            }
            for chiamata in tool_calls
        ],
    }


def _chiamate_semplici(tool_calls: list[dict]) -> str:
    return json.dumps(
        [{"name": c["name"], "arguments": c["args"]} for c in tool_calls], ensure_ascii=False
    )


def rendering_esplicito(tokenizer, esempio: dict) -> tuple[str, str]:
    """Riserva per i modelli il cui chat template non conosce i tool.

    Serve allo **smoke test** su un base model qualsiasi (es. `gemma-3-270m-it`,
    il cui template pretende l'alternanza user/assistant e non ha i tool):
    stesso contenuto e quindi stesso ordine di grandezza in token, così le misure
    di VRAM e di velocità restano valide. Con FunctionGemma si usa invece il suo
    template nativo, che le tool call le sa formattare da sé.
    """
    blocchi = []
    for messaggio in esempio["messages"]:
        if messaggio.get("tool_calls"):
            corpo = json.dumps(
                [
                    {
                        "name": tc["function"]["name"],
                        "arguments": json.loads(tc["function"]["arguments"]),
                    }
                    for tc in messaggio["tool_calls"]
                ],
                ensure_ascii=False,
            )
        else:
            corpo = messaggio.get("content") or ""
        blocchi.append(f"[{messaggio['role']}]\n{corpo}")
    strumenti = json.dumps(esempio["tools"], ensure_ascii=False)
    prompt = f"[tools]\n{strumenti}\n\n" + "\n\n".join(blocchi) + "\n\n[assistant]\n"
    atteso = esempio.get("testo_atteso") or _chiamate_semplici(esempio["tool_calls"])
    return prompt, atteso + (tokenizer.eos_token or "")


def normalizza_per_template(messaggi: list[dict]) -> list[dict]:
    """Adatta i messages al chat template di FunctionGemma.

    Due richieste sue, che il formato OpenAI del gateway non soddisfa:
    ogni messaggio ``tool`` deve portare il ``name`` del tool che ha risposto
    (altrimenti: "Invalid tool response: 'name' must be provided"), e il ``name``
    si ricava dal ``tool_call_id`` del turno assistant precedente. Il dataset
    resta canonico: l'adattamento vive qui, non nei dati.
    """
    nomi_per_id: dict[str, str] = {}
    fuori: list[dict] = []
    for messaggio in messaggi:
        for chiamata in messaggio.get("tool_calls") or []:
            nomi_per_id[chiamata.get("id", "")] = chiamata["function"]["name"]
        if messaggio.get("role") == "tool" and "name" not in messaggio:
            messaggio = {
                **messaggio,
                "name": nomi_per_id.get(messaggio.get("tool_call_id", ""), "tool"),
            }
        fuori.append(messaggio)
    return fuori


def in_prompt_completion(tokenizer, esempi: list[dict]) -> tuple[list[dict], str]:
    """Ogni esempio → {prompt, completion}. Ritorna anche il formato usato.

    Con un template che conosce i tool, il completion è ricavato **per differenza**
    (conversazione completa meno prompt): non si codifica a mano il formato delle
    tool call, che viene dal template del modello. Se il template non regge i tool,
    si passa al rendering esplicito.
    """
    fuori: list[dict] = []
    nativi = 0
    for esempio in esempi:
        messaggi = normalizza_per_template(esempio["messages"])
        # gli schemi vanno passati AVVOLTI ({"type":"function","function":{…}}):
        # il template di FunctionGemma legge `tool.function`, non il dict nudo
        strumenti = esempio["tools"] or None
        atteso = (
            messaggio_target_testo(esempio["testo_atteso"])
            if esempio.get("testo_atteso")
            else messaggio_target(esempio["tool_calls"])
        )
        try:
            prompt = tokenizer.apply_chat_template(
                messaggi, tools=strumenti, tokenize=False, add_generation_prompt=True
            )
            completo = tokenizer.apply_chat_template(
                [*messaggi, atteso], tools=strumenti, tokenize=False
            )
            if not completo.startswith(prompt):
                raise ValueError("template non prefisso-consistente")
            completion = completo[len(prompt) :]
            # dopo una tool call il template apre già lo slot della risposta:
            # non è roba che il modello deve generare
            if completion.endswith(CODA_DA_TOGLIERE):
                completion = completion[: -len(CODA_DA_TOGLIERE)]
            fuori.append({"prompt": prompt, "completion": completion})
            nativi += 1
            continue
        except Exception as exc:  # noqa: BLE001
            if not fuori:
                print(f"  template nativo non applicabile ({type(exc).__name__}: "
                      f"{str(exc)[:90]}) → rendering esplicito")
            prompt, completion = rendering_esplicito(tokenizer, esempio)
            fuori.append({"prompt": prompt, "completion": completion})

    formato = "nativo" if nativi == len(esempi) else (
        "esplicito" if nativi == 0 else f"misto ({nativi} nativi)"
    )
    print(f"  formato dei prompt: {formato}")
    return fuori, formato


def statistiche(tokenizer, coppie: list[dict]) -> None:
    lunghezze = sorted(
        len(tokenizer(c["prompt"] + c["completion"], add_special_tokens=False)["input_ids"])
        for c in coppie
    )
    if not lunghezze:
        print("nessun esempio")
        return
    n = len(lunghezze)
    print(f"  esempi           {n}")
    print(f"  token: mediana   {lunghezze[n // 2]}")
    print(f"         p90       {lunghezze[int(n * 0.9)]}")
    print(f"         max       {lunghezze[-1]}")
    print(f"         totale    {sum(lunghezze):,}")
    for soglia in (1024, 2048, 4096, 8192):
        entro = sum(1 for x in lunghezze if x <= soglia)
        print(f"  entro {soglia:5d}      {entro}/{n} ({100 * entro / n:.0f}%)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--modello", default="google/functiongemma-270m-it")
    parser.add_argument("--out", type=Path, default=Path("./functiongemma-workflower-lora"))
    parser.add_argument("--max-length", type=int, default=4096)
    parser.add_argument("--epoche", type=float, default=3.0)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--val", type=float, default=0.1, help="frazione di validazione")
    parser.add_argument("--seed", type=int, default=20260728)
    parser.add_argument("--solo-statistiche", action="store_true")
    args = parser.parse_args()

    esempi = carica(args.dataset)
    print(f"dataset: {len(esempi)} esempi da {args.dataset}")
    from collections import Counter

    for tipo, n in Counter(e["tipo_esempio"] for e in esempi).most_common():
        print(f"  {tipo:16s} {n}")

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.modello)
    coppie, _formato = in_prompt_completion(tokenizer, esempi)
    print("\nlunghezze (prompt + completion):")
    statistiche(tokenizer, coppie)

    if args.solo_statistiche:
        return

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from trl import SFTConfig, SFTTrainer

    applica_liger(args.modello)

    rng = random.Random(args.seed)
    rng.shuffle(coppie)
    taglio = max(1, int(len(coppie) * args.val)) if args.val > 0 else 0
    valutazione = Dataset.from_list(coppie[:taglio]) if taglio else None
    addestramento = Dataset.from_list(coppie[taglio:])
    print(f"\ntrain {len(addestramento)} · validazione {taglio}")

    configurazione = SFTConfig(
        output_dir=str(args.out),
        num_train_epochs=args.epoche,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        # 8 GB: batch 1 + accumulo. Il picco è nei logits (vocab 262k), non nei pesi.
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        max_length=args.max_length,
        packing=False,
        completion_only_loss=True,
        # NIENTE use_liger_kernel qui: in trl 1.9.1 è accettato e ignorato.
        # La patch è applicata a mano sopra (vedi applica_liger).
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        bf16=True,
        optim="adamw_torch_fused",
        logging_steps=5,
        save_strategy="epoch",
        eval_strategy="epoch" if valutazione else "no",
        report_to=[],
        seed=args.seed,
        # sdpa, non eager: misurato 0,83 GB contro 1,45 GB, e molto più veloce
        model_init_kwargs={"dtype": torch.bfloat16, "attn_implementation": "sdpa"},
    )

    trainer = SFTTrainer(
        model=args.modello,
        args=configurazione,
        train_dataset=addestramento,
        eval_dataset=valutazione,
        processing_class=tokenizer,
        peft_config=LoraConfig(
            r=args.rank,
            lora_alpha=args.rank * 2,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules="all-linear",
        ),
    )
    trainer.train()
    trainer.save_model(str(args.out))
    print(f"\nadattatore salvato in {args.out}")
    if torch.cuda.is_available():
        print(f"picco VRAM: {torch.cuda.max_memory_allocated() / 1024**3:.2f} GiB")


if __name__ == "__main__":
    main()
