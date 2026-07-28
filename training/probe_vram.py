"""Misura il picco VRAM di un passo di training vero, per configurazione.

Serve a smettere di indovinare: un forward+backward sulla sequenza più lunga del
dataset, per ogni combinazione di attenzione e cross-entropy. Il sospetto è che il
costo non sia nei pesi (0,54 GB) ma nei logit — vocab 262.146 — e nell'attenzione
`eager`, che materializza la matrice seq×seq.

Ogni configurazione gira in un processo separato: così il picco misurato è suo e
non l'eredità di quella prima.
"""

import argparse
import json
import subprocess
import sys

CONFIGURAZIONI = [
    ("eager  + CE standard", "eager", False),
    ("eager  + liger", "eager", True),
    ("sdpa   + CE standard", "sdpa", False),
    ("sdpa   + liger", "sdpa", True),
]

FIGLIO = '''
import json, sys, torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM

attenzione, liger, lunghezza = sys.argv[1], sys.argv[2] == "1", int(sys.argv[3])
modello_id = "google/functiongemma-270m-it"

if liger:
    from liger_kernel.transformers import apply_liger_kernel_to_gemma3_text
    apply_liger_kernel_to_gemma3_text()

libera_prima, totale = torch.cuda.mem_get_info()
modello = AutoModelForCausalLM.from_pretrained(
    modello_id, dtype=torch.bfloat16, attn_implementation=attenzione
).to("cuda")
modello = get_peft_model(modello, LoraConfig(
    r=16, lora_alpha=32, task_type="CAUSAL_LM", target_modules="all-linear"))
modello.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
modello.enable_input_require_grads()
modello.train()

ids = torch.randint(5, 200000, (1, lunghezza), device="cuda")
etichette = ids.clone()
etichette[:, : lunghezza // 2] = -100          # loss solo sulla "completion"
torch.cuda.reset_peak_memory_stats()
uscita = modello(input_ids=ids, labels=etichette)
uscita.loss.backward()
torch.cuda.synchronize()

libera_dopo, _ = torch.cuda.mem_get_info()
print(json.dumps({
    "picco_allocato_gib": torch.cuda.max_memory_allocated() / 1024**3,
    "picco_riservato_gib": torch.cuda.max_memory_reserved() / 1024**3,
    "libera_prima_gib": libera_prima / 1024**3,
    "libera_dopo_gib": libera_dopo / 1024**3,
    "totale_gib": totale / 1024**3,
    "loss": float(uscita.loss),
}))
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lunghezza", type=int, default=3509, help="token della seq più lunga")
    args = parser.parse_args()

    print(f"sequenza di prova: {args.lunghezza} token (la più lunga del dataset)\n")
    print(f"{'configurazione':22s} {'picco':>9s} {'riservato':>11s} {'libera dopo':>13s}  loss")
    for etichetta, attenzione, liger in CONFIGURAZIONI:
        esito = subprocess.run(
            [sys.executable, "-c", FIGLIO, attenzione, "1" if liger else "0", str(args.lunghezza)],
            capture_output=True,
            text=True,
        )
        righe = [r for r in esito.stdout.splitlines() if r.startswith("{")]
        if not righe:
            errore = (esito.stderr or "").strip().splitlines()
            motivo = errore[-1][:80] if errore else "nessun output"
            print(f"{etichetta:22s} {'FALLITA':>9s}  {motivo}")
            continue
        m = json.loads(righe[-1])
        print(f"{etichetta:22s} {m['picco_allocato_gib']:8.2f}G {m['picco_riservato_gib']:10.2f}G "
              f"{m['libera_dopo_gib']:12.2f}G  {m['loss']:.3f}")


if __name__ == "__main__":
    main()
