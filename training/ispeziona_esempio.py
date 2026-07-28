"""Mostra come un esempio arriva davvero al modello: coda del prompt + completion."""

import json

from train_lora import in_prompt_completion  # noqa: F401
from transformers import AutoTokenizer

esempi = [json.loads(r) for r in open("sft.jsonl", encoding="utf-8")]
tok = AutoTokenizer.from_pretrained("google/functiongemma-270m-it")
coppie, formato = in_prompt_completion(tok, esempi)

for tipo in ("routing", "lookup", "estrazione"):
    indice = next(i for i, e in enumerate(esempi) if e["tipo_esempio"] == tipo)
    prompt, completion = coppie[indice]["prompt"], coppie[indice]["completion"]
    print(f"\n{'=' * 78}\n{tipo.upper()}  ({esempi[indice]['workflow']})")
    print(f"prompt: {len(tok(prompt, add_special_tokens=False)['input_ids'])} token")
    print(f"--- testa del prompt (300 char) ---\n{prompt[:300]}")
    print(f"--- coda del prompt (400 char) ---\n{prompt[-400:]}")
    print(f"--- COMPLETION ({len(tok(completion, add_special_tokens=False)['input_ids'])} token,"
          f" quello su cui cade la loss) ---\n{completion[:700]}")
