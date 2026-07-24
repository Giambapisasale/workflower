"""Doppio di ``litellm.completion`` per il Diagnostico: una diagnosi deterministica.

Decide la categoria dal prompt come farebbe un modello che legge il contesto:
se sono presenti **artefatti-dato** (la skill di un workflow) il problema è
correggibile come dato; altrimenti, se c'è un traceback nel codice-cornice, è
architetturale. ``categoria_forzata`` bypassa l'euristica per i test mirati.
"""

import json
from typing import Any


class FakeDiagnostico:
    """Callable con la firma di ``litellm.completion``; risposte in forma OpenAI."""

    def __init__(self, categoria_forzata: str | None = None) -> None:
        self.categoria_forzata = categoria_forzata
        self.chiamate = 0

    def __call__(
        self, *, model: str, messages: list[dict[str, Any]], **_ignorati: Any
    ) -> dict[str, Any]:
        self.chiamate += 1
        prompt = str(messages[-1]["content"])
        categoria = self.categoria_forzata or (
            "dato" if "Artefatto-dato" in prompt else "architettura"
        )
        if categoria == "dato":
            azione = {
                "tipo": "improver",
                "workflow": "carica-fattura",
                "dettaglio": "aggiorna la skill",
            }
            proposta = "Aggiorna la skill di estrazione."
        else:
            azione = {"tipo": "nessuna", "workflow": None, "dettaglio": ""}
            proposta = "Modifica raccomandata nel codice-cornice (da valutare a mano)."
        out = {
            "categoria": categoria,
            "titolo": "Diagnosi di prova",
            "analisi": "Analisi basata sui fatti forniti.",
            "causa_radice": "Causa individuata.",
            "proposta": proposta,
            "azione_suggerita": azione,
            "file_coinvolti": ["backend/app/core/gateway.py"],
            "confidenza": 0.8,
        }
        return {
            "choices": [{"message": {"role": "assistant", "content": json.dumps(out)}}],
            "usage": {"prompt_tokens": 100 + self.chiamate, "completion_tokens": 20},
            "model": model,
            "_hidden_params": {"response_cost": 0.001},
        }
