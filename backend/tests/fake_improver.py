"""Doppio di ``litellm.completion`` per l'Improver (M5).

Due mosse, riconosciute dal marker della skill nel messaggio ``system``:

- "Miglioramento del workflow" → propone una skill nuova. Con ``aggiunge_calce``
  (default) l'aggiunta contiene la parola "calce": è la chiave che sblocca
  l'estrazione della ritenuta nel ``FakeCompleter`` delle fatture. Senza, la
  patch NON risolve — utile per verificare che il replay la bocci.
- "Giudizio di regressione" → confronta ATTESO e OTTENUTO sui campi chiave.
"""

import json
import re
from typing import Any

CAMPI_CHIAVE = [
    "fornitore_id",
    "cantiere_id",
    "numero",
    "data",
    "imponibile",
    "iva",
    "totale",
    "ritenuta_acconto",
]

CON_CALCE = """

## Ritenuta d'acconto

Alcune parcelle dei professionisti riportano una ritenuta d'acconto **in calce**,
cioè in fondo al foglio, staccata dal riepilogo (vicino al "netto a pagare").
Quando c'è, metti l'importo in `ritenuta_acconto`; altrimenti lascia `null`.
"""

SENZA_CALCE = """

## Nota

Ricontrolla sempre il numero della fattura e la data prima di consegnare.
"""


class FakeCompleterImprover:
    def __init__(self, aggiunge_calce: bool = True) -> None:
        self.aggiunge_calce = aggiunge_calce
        self.proposte = 0
        self.giudizi = 0

    def __call__(
        self, *, model: str, messages: list[dict[str, Any]], **_ignorati: Any
    ) -> dict[str, Any]:
        sistema = str(messages[0]["content"])
        utente = str(messages[-1]["content"])
        if "Miglioramento del workflow" in sistema:
            return self._proposta(model, utente)
        if "Giudizio di regressione" in sistema:
            return self._giudizio(model, utente)
        raise AssertionError("prompt improver non riconosciuto dal fake")

    def _proposta(self, model: str, utente: str) -> dict[str, Any]:
        self.proposte += 1
        match = re.search(r"<<<SKILL_ATTUALE\n(.*)\nSKILL_ATTUALE>>>", utente, re.DOTALL)
        skill = match.group(1) if match else ""
        nuova = skill + (CON_CALCE if self.aggiunge_calce else SENZA_CALCE)
        return _messaggio(
            model,
            json.dumps(
                {
                    "analisi": "la skill non dice di cercare la ritenuta d'acconto in calce",
                    "motivazione": "aggiunge le istruzioni sulla ritenuta senza toccare il resto",
                    "skill_nuova": nuova,
                },
                ensure_ascii=False,
            ),
        )

    def _giudizio(self, model: str, utente: str) -> dict[str, Any]:
        self.giudizi += 1
        atteso = _json_dopo(utente, "ATTESO:")
        ottenuto = _json_dopo(utente, "OTTENUTO:")
        differenze = [c for c in CAMPI_CHIAVE if atteso.get(c) != ottenuto.get(c)]
        verdetto = {"uguale": not differenze, "differenze": differenze}
        return _messaggio(model, json.dumps(verdetto, ensure_ascii=False))


def _json_dopo(testo: str, etichetta: str) -> dict[str, Any]:
    dopo = testo.split(etichetta, 1)[1].lstrip()
    return json.loads(dopo.splitlines()[0])


def _messaggio(model: str, contenuto: str) -> dict[str, Any]:
    return {
        "choices": [{"message": {"role": "assistant", "content": contenuto}}],
        "usage": {"prompt_tokens": 300, "completion_tokens": 40},
        "model": model,
        "_hidden_params": {"response_cost": 0.003},
    }
