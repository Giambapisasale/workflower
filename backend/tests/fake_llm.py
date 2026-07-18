"""Doppio di ``litellm.completion`` per i test: un "modello" deterministico.

Simula un agente che segue la skill: legge il PDF della fixture (testo, via
pymupdf — il layout delle fixtures è fatto apposta), chiama i tool nell'ordine
naturale (ocr_pdf → cerca_fornitore → cerca_cantiere) leggendo i loro risultati
dalla conversazione, e consegna il JSON ``{dati, confidence}``.

Contratto con lo scenario M5 (ritenuta d'acconto): il fake estrae la ritenuta
SOLO se la skill (primo messaggio system) contiene la parola "calce".
La skill v1.0 non la contiene; sarà la patch dell'Improver ad aggiungerla.
"""

import json
import re
from pathlib import Path
from typing import Any

import pymupdf


def _importo(testo: str) -> float:
    """'8.330,00' → 8330.0 (dal formato italiano stampato in fattura)."""
    return float(testo.replace(".", "").replace(",", "."))


def _leggi_fattura(percorso: Path) -> dict[str, Any]:
    with pymupdf.open(percorso) as documento:
        testo = "\n".join(pagina.get_text() for pagina in documento)
    righe_doc = [riga.strip() for riga in testo.splitlines() if riga.strip()]

    testata = re.search(r"FATTURA N\. (\S+) del (\d{2})/(\d{2})/(\d{4})", testo)
    if not testata:
        raise AssertionError(f"fixture illeggibile: {percorso}")

    def euro(etichetta: str) -> float | None:
        match = re.search(etichetta + r": EUR ([\d.,]+)", testo)
        return _importo(match.group(1)) if match else None

    righe = []
    for riga in righe_doc:
        match = re.fullmatch(r"(.+?) \| (.+?) \| EUR ([\d.,]+)", riga)
        if not match:
            continue
        quantita, unita = None, None
        blocco_quantita = re.fullmatch(r"([\d.,]+) (\S+)", match.group(2))
        if blocco_quantita:
            quantita = _importo(blocco_quantita.group(1))
            unita = blocco_quantita.group(2)
        righe.append(
            {
                "descrizione": match.group(1),
                "quantita": quantita,
                "unita_misura": unita,
                "importo": _importo(match.group(3)),
                "voce_computo_id": None,
            }
        )

    return {
        "fornitore": righe_doc[0],
        "cantiere": re.search(r"Cantiere: (.+)", testo).group(1).strip(),
        "numero": testata.group(1),
        "data_iso": f"{testata.group(4)}-{testata.group(3)}-{testata.group(2)}",
        "imponibile": euro("Imponibile"),
        "iva": euro(r"IVA \d+%"),
        "totale": euro("TOTALE"),
        "ritenuta": euro(r"Ritenuta d'acconto \d+%"),
        "righe": righe,
    }


class FakeCompleter:
    """Callable con la firma di ``litellm.completion``; risposte in forma OpenAI."""

    def __init__(
        self,
        data_dir: Path | str,
        guasti: list[Exception] | None = None,
        totale_errato_volte: int = 0,
        confidence_override: dict[str, float] | None = None,
        costo_per_chiamata: float = 0.0021,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.guasti = list(guasti or [])
        self.totale_errato_restanti = totale_errato_volte
        self.confidence_override = confidence_override
        self.costo_per_chiamata = costo_per_chiamata
        self.chiamate = 0
        self.risposte_finali = 0

    def __call__(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **_ignorati: Any,
    ) -> dict[str, Any]:
        self.chiamate += 1
        if self.guasti:
            raise self.guasti.pop(0)

        skill = str(messages[0]["content"])
        doc = self._doc_path(messages)
        gia_chiamati = self._tool_chiamati(messages)
        if tools and "ocr_pdf" not in gia_chiamati:
            return self._risposta_tool(model, "ocr_pdf", {"path": doc})

        campi = _leggi_fattura(self.data_dir / doc)
        if tools and "cerca_fornitore" not in gia_chiamati:
            return self._risposta_tool(model, "cerca_fornitore", {"query": campi["fornitore"]})
        if tools and "cerca_cantiere" not in gia_chiamati:
            return self._risposta_tool(model, "cerca_cantiere", {"query": campi["cantiere"]})

        dati = {
            "fornitore_id": self._miglior_id(messages, "cerca_fornitore"),
            "cantiere_id": self._miglior_id(messages, "cerca_cantiere"),
            "numero": campi["numero"],
            "data": campi["data_iso"],
            "imponibile": campi["imponibile"],
            "iva": campi["iva"],
            "totale": campi["totale"],
            # il fake "segue le istruzioni": senza indicazione sulla dicitura
            # in calce, la ritenuta non viene cercata (scenario M5)
            "ritenuta_acconto": campi["ritenuta"] if "calce" in skill.lower() else None,
            "righe": campi["righe"],
        }
        self.risposte_finali += 1
        if self.totale_errato_restanti > 0:
            self.totale_errato_restanti -= 1
            dati["totale"] = round(dati["totale"] + 100, 2)
        confidence = self.confidence_override or dict.fromkeys(dati, 0.97)
        testo = json.dumps({"dati": dati, "confidence": confidence}, ensure_ascii=False)
        return self._risposta_finale(model, testo)

    # ------------------------------------------------------- lato "modello"

    @staticmethod
    def _doc_path(messages: list[dict[str, Any]]) -> str:
        for messaggio in messages:
            if messaggio.get("role") == "user" and isinstance(messaggio.get("content"), str):
                match = re.search(r"Documento da elaborare: (\S+)", messaggio["content"])
                if match:
                    return match.group(1)
        raise AssertionError("nessun documento nel prompt")

    @staticmethod
    def _tool_chiamati(messages: list[dict[str, Any]]) -> set[str]:
        nomi = set()
        for messaggio in messages:
            for chiamata in messaggio.get("tool_calls") or []:
                nomi.add(chiamata["function"]["name"])
        return nomi

    @staticmethod
    def _miglior_id(messages: list[dict[str, Any]], nome_tool: str) -> str | None:
        """Primo risultato del tool, letto dalla conversazione come farebbe il modello."""
        id_chiamata = None
        for messaggio in messages:
            for chiamata in messaggio.get("tool_calls") or []:
                if chiamata["function"]["name"] == nome_tool:
                    id_chiamata = chiamata["id"]
            if (
                id_chiamata
                and messaggio.get("role") == "tool"
                and messaggio.get("tool_call_id") == id_chiamata
            ):
                risultati = json.loads(messaggio["content"]).get("risultati") or []
                return risultati[0]["id"] if risultati else None
        return None

    def _risposta_tool(self, model: str, nome: str, argomenti: dict[str, Any]) -> dict[str, Any]:
        return self._risposta(
            model,
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call_{self.chiamate}",
                        "type": "function",
                        "function": {"name": nome, "arguments": json.dumps(argomenti)},
                    }
                ],
            },
        )

    def _risposta_finale(self, model: str, testo: str) -> dict[str, Any]:
        return self._risposta(model, {"role": "assistant", "content": testo})

    def _risposta(self, model: str, messaggio: dict[str, Any]) -> dict[str, Any]:
        return {
            "choices": [{"message": messaggio}],
            "usage": {"prompt_tokens": 1000 + self.chiamate, "completion_tokens": 42},
            "model": model,
            "_hidden_params": {"response_cost": self.costo_per_chiamata},
        }
