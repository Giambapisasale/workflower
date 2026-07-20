"""Doppio di ``litellm.completion`` per il Toolsmith (M16).

Riconosce il marker "Generazione di un tool" nel messaggio ``system`` e
restituisce ``{codice, schema}``: una funzione ``esegui`` che calcola l'uscita
come ``ingresso * aliquota`` con ``Decimal`` (lo scenario ritenuta d'acconto).
Con un'``aliquota`` diversa da quella delle coppie storiche la funzione NON
riproduce gli output validati — utile per verificare che l'esito dei test in
sandbox lo registri onestamente.
"""

import json
import re
from typing import Any


def _messaggio(model: str, contenuto: str) -> dict[str, Any]:
    return {
        "choices": [{"message": {"role": "assistant", "content": contenuto}}],
        "usage": {"prompt_tokens": 300, "completion_tokens": 60},
        "model": model,
        "_hidden_params": {"response_cost": 0.004},
    }


class FakeCompleterToolsmith:
    def __init__(self, aliquota: str = "0.2") -> None:
        self.aliquota = aliquota
        self.generazioni = 0

    def __call__(
        self, *, model: str, messages: list[dict[str, Any]], **_ignorati: Any
    ) -> dict[str, Any]:
        sistema = str(messages[0]["content"])
        if "Generazione di un tool" in sistema:
            return self._genera(model, str(messages[-1]["content"]))
        raise AssertionError("prompt toolsmith non riconosciuto dal fake")

    def _genera(self, model: str, utente: str) -> dict[str, Any]:
        self.generazioni += 1
        ingressi = re.search(r"Campi in ingresso: (.+)", utente).group(1).split(", ")
        uscita = re.search(r"Campo di uscita: (.+)", utente).group(1).strip()
        param = ingressi[0].strip()
        codice = (
            "from decimal import Decimal, ROUND_HALF_UP\n\n\n"
            f"def esegui({param}):\n"
            f'    val = (Decimal(str({param})) * Decimal("{self.aliquota}")).quantize(\n'
            '        Decimal("0.01"), rounding=ROUND_HALF_UP\n'
            "    )\n"
            f'    return {{"{uscita}": float(val)}}\n'
        )
        schema = {
            "type": "function",
            "function": {
                "name": "placeholder",  # il Toolsmith lo riallinea al nome del candidato
                "description": "Calcola un importo derivato in modo deterministico.",
                "parameters": {
                    "type": "object",
                    "properties": {param: {"type": "number"}},
                    "required": [param],
                },
            },
        }
        payload = json.dumps({"codice": codice, "schema": schema}, ensure_ascii=False)
        return _messaggio(model, payload)
