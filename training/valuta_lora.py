"""Quanto ha imparato il LoRA: base contro adattato, sullo stesso held-out.

Misura diretta, senza passare da Ollama né da `eval-t3` (che oggi non può
valutare un T3 solo testo: rigioca gli esempi rimettendoci le **immagini** e
lascia i prompt di sistema troncati, cioè una distribuzione diversa da quella su
cui si addestra).

Tre metriche, per tipo di esempio:
- **tool**: il nome del tool richiesto è quello giusto;
- **args**: gli argomenti coincidono esattamente col ground truth;
- **campi**: per l'estrazione, quanti campi di `dati` sono esatti (parziale, più
  informativo dell'exact match).

    python valuta_lora.py --adattatore ./functiongemma-workflower-lora
"""

import argparse
import json
import random
import re
from pathlib import Path

import torch
from train_lora import in_prompt_completion
from transformers import AutoModelForCausalLM, AutoTokenizer

CHIAMATA = re.compile(
    r"<start_function_call>\s*call:(?P<nome>[\w.]+)\s*\{(?P<corpo>.*)\}\s*<end_function_call>",
    re.DOTALL,
)


def parse_chiamata(testo: str) -> tuple[str | None, dict | None]:
    """Estrae (nome, argomenti) dal formato di tool call di FunctionGemma."""
    trovato = CHIAMATA.search(testo)
    if not trovato:
        return None, None
    corpo = trovato.group("corpo").strip()
    for candidato in (corpo, "{" + corpo + "}"):
        try:
            valore = json.loads(candidato)
            if isinstance(valore, dict):
                return trovato.group("nome"), valore
        except json.JSONDecodeError:
            continue
    return trovato.group("nome"), None


def primo_json(testo: str) -> dict | None:
    inizio = testo.find("{")
    if inizio < 0:
        return None
    for fine in range(len(testo), inizio, -1):
        try:
            valore = json.loads(testo[inizio:fine])
            if isinstance(valore, dict):
                return valore
        except json.JSONDecodeError:
            continue
    return None


def confronta_campi(atteso: dict, ottenuto: dict | None) -> tuple[int, int]:
    if not isinstance(ottenuto, dict):
        return 0, len(atteso)
    esatti = 0
    for chiave, valore in atteso.items():
        altro = ottenuto.get(chiave)
        if isinstance(valore, float) or isinstance(altro, float):
            try:
                if abs(float(valore or 0) - float(altro or 0)) < 0.01:
                    esatti += 1
                    continue
            except (TypeError, ValueError):
                pass
        elif valore == altro:
            esatti += 1
    return esatti, len(atteso)


def genera(modello, tokenizer, prompt: str, max_nuovi: int) -> str:
    ingressi = tokenizer(prompt, return_tensors="pt").to(modello.device)
    with torch.no_grad():
        uscita = modello.generate(
            **ingressi,
            max_new_tokens=max_nuovi,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    return tokenizer.decode(uscita[0][ingressi["input_ids"].shape[1] :], skip_special_tokens=False)


def valuta(etichetta: str, modello, tokenizer, prove: list[tuple[dict, str]]) -> None:
    per_tipo: dict[str, dict[str, int]] = {}
    for esempio, prompt in prove:
        tipo = esempio["tipo_esempio"]
        conto = per_tipo.setdefault(
            tipo, {"n": 0, "tool": 0, "args": 0, "campi_ok": 0, "campi_tot": 0}
        )
        conto["n"] += 1
        atteso_testo = esempio.get("testo_atteso")
        uscita = genera(modello, tokenizer, prompt, 320 if atteso_testo else 160)

        if atteso_testo:
            atteso = json.loads(atteso_testo)
            ottenuto = primo_json(uscita)
            esatti, totale = confronta_campi(atteso.get("dati") or {}, (ottenuto or {}).get("dati"))
            conto["campi_ok"] += esatti
            conto["campi_tot"] += totale
            conto["tool"] += int(ottenuto is not None)
            conto["args"] += int(esatti == totale and totale > 0)
        else:
            atteso_chiamate = esempio["tool_calls"]
            nome, argomenti = parse_chiamata(uscita)
            giusto = nome == atteso_chiamate[0]["name"]
            conto["tool"] += int(giusto)
            conto["args"] += int(giusto and argomenti == atteso_chiamate[0]["args"])

    print(f"\n=== {etichetta} ===")
    for tipo, c in sorted(per_tipo.items()):
        riga = (f"  {tipo:12s} n={c['n']:3d}  tool {c['tool']}/{c['n']}"
                f"  args {c['args']}/{c['n']}")
        if c["campi_tot"]:
            riga += f"  campi {c['campi_ok']}/{c['campi_tot']}"
        print(riga)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("sft.jsonl"))
    parser.add_argument("--modello", default="google/functiongemma-270m-it")
    parser.add_argument("--adattatore", type=Path, required=True)
    parser.add_argument("--val", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=20260728)
    parser.add_argument("--limite", type=int, default=0, help="0 = tutto l'held-out")
    args = parser.parse_args()

    esempi = [json.loads(r) for r in args.dataset.read_text(encoding="utf-8").splitlines() if r.strip()]
    tokenizer = AutoTokenizer.from_pretrained(args.modello)
    coppie, _ = in_prompt_completion(tokenizer, esempi)

    # stessa permutazione di train_lora.py: shuffle con lo stesso seed su una lista
    # della stessa lunghezza dà lo stesso ordine, quindi lo held-out è identico
    indici = list(range(len(coppie)))
    random.Random(args.seed).shuffle(indici)
    taglio = max(1, int(len(coppie) * args.val))
    held_out = indici[:taglio]
    if args.limite:
        held_out = held_out[: args.limite]
    prove = [(esempi[i], coppie[i]["prompt"]) for i in held_out]
    print(f"held-out: {len(prove)} esempi (mai visti in training)")

    base = AutoModelForCausalLM.from_pretrained(
        args.modello, dtype=torch.bfloat16, attn_implementation="eager"
    ).to("cuda").eval()
    valuta("BASE (FunctionGemma senza adattatore)", base, tokenizer, prove)

    from peft import PeftModel

    adattato = PeftModel.from_pretrained(base, str(args.adattatore)).eval()
    valuta("ADATTATO (LoRA Workflower)", adattato, tokenizer, prove)


if __name__ == "__main__":
    main()
