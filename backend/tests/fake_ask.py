"""Doppio di ``litellm.completion`` per il workflow "interroga".

Due sole mosse: alla skill di generazione SQL risponde con la query
configurata, alla skill di risposta con la frase configurata. Registra i
contesti ricevuti, così i test verificano cosa è arrivato al "modello".
"""

from typing import Any


class FakeCompleterInterroga:
    def __init__(self, sql: str, frase: str = "Hai speso circa 30 mila euro.") -> None:
        self.sql = sql
        self.frase = frase
        self.contesto_sql: str | None = None
        self.contesto_frase: str | None = None

    def __call__(
        self, *, model: str, messages: list[dict[str, Any]], **_ignorati: Any
    ) -> dict[str, Any]:
        sistema = str(messages[0]["content"])
        utente = str(messages[-1]["content"])
        if "Generazione SQL" in sistema:
            self.contesto_sql = utente
            contenuto = f"Ecco la query:\n```sql\n{self.sql}\n```"
        else:
            self.contesto_frase = utente
            contenuto = self.frase
        return {
            "choices": [{"message": {"role": "assistant", "content": contenuto}}],
            "usage": {"prompt_tokens": 200, "completion_tokens": 30},
            "model": model,
            "_hidden_params": {"response_cost": 0.0001},
        }
