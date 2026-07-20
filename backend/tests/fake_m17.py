"""Trasporto LLM combinato per il ciclo M17 (chiusura del §3.6).

Un solo callable che smista sui quattro compiti che il ciclo tocca, per marker
nel messaggio ``system``:

- "Generazione di un tool"        → Toolsmith: genera codice+schema (M16);
- "Insegna alla skill a usare il tool" → Toolsmith: patch di skill che insegna a
  chiamare il tool (con l'LLM come fallback);
- "Giudizio di regressione"       → Improver: giudizio del replay sul golden;
- altrimenti                       → estrazione fattura (FakeCompleter), che sa
  già seguire la skill e — dopo la patch — chiamare ``calcola_ritenuta``.
"""

import json
import re
from pathlib import Path
from typing import Any

from fake_improver import FakeCompleterImprover
from fake_llm import FakeCompleter
from fake_toolsmith import FakeCompleterToolsmith

# La sezione che la patch aggiunge alla skill: nomina il tool (il marker che fa
# scattare il percorso "tool" nel FakeCompleter delle fatture) e dichiara il
# fallback. Niente parola "calce": la ritenuta passa dal tool, non dal doc.
SEZIONE_TOOL = """

## Ritenuta d'acconto (tool deterministico)

Per la ritenuta d'acconto usa il tool `calcola_ritenuta`, passandogli
l'`imponibile`, e metti il risultato in `ritenuta_acconto`. Se il tool non è
disponibile o restituisce un errore, torna a leggere la ritenuta dal documento.
"""


def _messaggio(model: str, contenuto: str) -> dict[str, Any]:
    return {
        "choices": [{"message": {"role": "assistant", "content": contenuto}}],
        "usage": {"prompt_tokens": 320, "completion_tokens": 50},
        "model": model,
        "_hidden_params": {"response_cost": 0.004},
    }


class FakeCompleterM17:
    def __init__(self, data_dir: Path | str) -> None:
        self.fattura = FakeCompleter(data_dir)
        self.toolsmith = FakeCompleterToolsmith()
        self.improver = FakeCompleterImprover()
        self.patch_skill = 0

    def __call__(self, *, model: str, messages: list[dict[str, Any]], **kw: Any) -> Any:
        sistema = str(messages[0]["content"])
        if "Generazione di un tool" in sistema:
            return self.toolsmith(model=model, messages=messages)
        if "Insegna alla skill a usare il tool" in sistema:
            return self._patch(model, messages)
        if "Giudizio di regressione" in sistema:
            return self.improver(model=model, messages=messages)
        return self.fattura(model=model, messages=messages, **kw)

    def _patch(self, model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        self.patch_skill += 1
        utente = str(messages[-1]["content"])
        match = re.search(r"<<<SKILL_ATTUALE\n(.*)\nSKILL_ATTUALE>>>", utente, re.DOTALL)
        skill = match.group(1) if match else ""
        return _messaggio(
            model,
            json.dumps(
                {
                    "analisi": "la ritenuta d'acconto era calcolata dal prompt",
                    "motivazione": "il tool è deterministico; resta l'LLM come fallback",
                    "skill_nuova": skill + SEZIONE_TOOL,
                },
                ensure_ascii=False,
            ),
        )
