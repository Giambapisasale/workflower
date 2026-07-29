"""Verifica autenticazione HF e accesso ai pesi gated di FunctionGemma."""

MODELLO = "google/functiongemma-270m-it"

from huggingface_hub import whoami  # noqa: E402

try:
    utente = whoami()
    print("autenticato come:", utente.get("name"))
except Exception as exc:  # noqa: BLE001
    print("NON autenticato:", type(exc).__name__, str(exc)[:160])

from transformers import AutoTokenizer  # noqa: E402

try:
    tok = AutoTokenizer.from_pretrained(MODELLO)
    template = tok.chat_template or ""
    print("accesso ai pesi OK · vocab =", len(tok), "· chat_template =", bool(template))
    print("il template conosce i tool:", "tool" in template.lower())
except Exception as exc:  # noqa: BLE001
    print("ACCESSO NEGATO:", type(exc).__name__, str(exc)[:240])
