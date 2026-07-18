"""Doppio di ``litellm.completion`` per i test: un "modello" deterministico.

Simula un agente che segue la skill: legge il documento della fixture (testo, via
pymupdf — il layout delle fixtures è fatto apposta), chiama i tool nell'ordine
naturale (ocr_pdf → cerca_fornitore → cerca_cantiere) leggendo i loro risultati
dalla conversazione, e consegna il JSON ``{dati, confidence}``.

Copre tre compiti, riconosciuti dal marker nella skill (primo messaggio system):

- "Classificazione del documento" → legge l'intestazione e dice se è fattura o DDT.
- "Estrazione fattura" → trascrive la fattura (con lo scenario ritenuta M5).
- "Estrazione DDT" → trascrive il documento di trasporto.

Contratto con lo scenario M5 (ritenuta d'acconto): il fake estrae la ritenuta
SOLO se la skill dell'estrazione fattura contiene la parola "calce".
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


def _testo_documento(percorso: Path) -> str:
    with pymupdf.open(percorso) as documento:
        return "\n".join(pagina.get_text() for pagina in documento)


def _leggi_fattura(percorso: Path) -> dict[str, Any]:
    testo = _testo_documento(percorso)
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


def _leggi_ddt(percorso: Path) -> dict[str, Any]:
    testo = _testo_documento(percorso)
    righe_doc = [riga.strip() for riga in testo.splitlines() if riga.strip()]

    testata = re.search(r"DDT N\. (\S+) del (\d{2})/(\d{2})/(\d{4})", testo)
    if not testata:
        raise AssertionError(f"fixture DDT illeggibile: {percorso}")

    def campo(etichetta: str) -> str | None:
        match = re.search(etichetta + r": (.+)", testo)
        valore = match.group(1).strip() if match else None
        return None if valore in (None, "-") else valore

    righe = []
    for riga in righe_doc:
        match = re.fullmatch(r"(.+?) \| (.+?) \| (.+)", riga)
        if not match or match.group(1) == "Descrizione":
            continue
        grezza = match.group(2).strip()
        quantita = _importo(grezza) if re.fullmatch(r"[\d.,]+", grezza) else None
        righe.append(
            {
                "descrizione": match.group(1),
                "quantita": quantita,
                "unita_misura": match.group(3).strip(),
                "voce_computo_id": None,
            }
        )

    cantiere = re.search(r"Destinazione \(cantiere\): (.+)", testo)
    return {
        "fornitore": righe_doc[0],
        "cantiere": cantiere.group(1).strip() if cantiere else "",
        "numero": testata.group(1),
        "data_iso": f"{testata.group(4)}-{testata.group(3)}-{testata.group(2)}",
        "causale": campo("Causale"),
        "riferimento_ordine": campo(r"Rif\. ordine"),
        "righe": righe,
    }


class FakeCompleter:
    """Callable con la firma di ``litellm.completion``; risposte in forma OpenAI."""

    def __init__(
        self,
        data_dir: Path | str,
        guasti: list[Exception] | None = None,
        guasto_persistente: Exception | None = None,
        totale_errato_volte: int = 0,
        confidence_override: dict[str, float] | None = None,
        costo_per_chiamata: float = 0.0021,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.guasti = list(guasti or [])
        self.guasto_persistente = guasto_persistente  # rotto su OGNI chiamata (es. chiave errata)
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
        if self.guasto_persistente is not None:
            raise self.guasto_persistente
        if self.guasti:
            raise self.guasti.pop(0)

        skill = str(messages[0]["content"])
        if "Classificazione del documento" in skill:
            return self._classifica(model, messages)
        if "Estrazione DDT" in skill:
            return self._estrai_ddt(model, messages, tools)
        return self._estrai_fattura(model, messages, tools, skill)

    # ------------------------------------------------------- classificazione

    def _classifica(self, model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        testo = _testo_documento(self.data_dir / self._doc_path(messages)).lower()
        tipo = "ddt" if ("documento di trasporto" in testo or "d.d.t" in testo) else "fattura"
        return self._risposta_finale(
            model, json.dumps({"tipo": tipo, "confidence": 0.95}, ensure_ascii=False)
        )

    # ------------------------------------------------------- estrazione DDT

    def _estrai_ddt(
        self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> dict[str, Any]:
        doc = self._doc_path(messages)
        gia_chiamati = self._tool_chiamati(messages)
        offerti = self._offerti(tools)
        if "ocr_pdf" in offerti and "ocr_pdf" not in gia_chiamati:
            return self._risposta_tool(model, "ocr_pdf", {"path": doc})

        campi = _leggi_ddt(self.data_dir / doc)
        if "cerca_fornitore" in offerti and "cerca_fornitore" not in gia_chiamati:
            return self._risposta_tool(model, "cerca_fornitore", {"query": campi["fornitore"]})
        if "cerca_cantiere" in offerti and "cerca_cantiere" not in gia_chiamati:
            return self._risposta_tool(model, "cerca_cantiere", {"query": campi["cantiere"]})

        dati = {
            "fornitore_id": self._miglior_id(messages, "cerca_fornitore"),
            "cantiere_id": self._miglior_id(messages, "cerca_cantiere"),
            "numero": campi["numero"],
            "data": campi["data_iso"],
            "causale": campi["causale"],
            "riferimento_ordine": campi["riferimento_ordine"],
            "righe": campi["righe"],
        }
        self.risposte_finali += 1
        confidence = self.confidence_override or dict.fromkeys(dati, 0.96)
        testo = json.dumps({"dati": dati, "confidence": confidence}, ensure_ascii=False)
        return self._risposta_finale(model, testo)

    # ------------------------------------------------------- estrazione fattura

    def _estrai_fattura(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        skill: str,
    ) -> dict[str, Any]:
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
        """Il percorso del documento dal prompt (estrazione o classificazione)."""
        for messaggio in messages:
            for testo in _testi(messaggio.get("content")):
                match = re.search(r"Documento da (?:elaborare|classificare): (\S+)", testo)
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
    def _offerti(tools: list[dict[str, Any]] | None) -> set[str]:
        return {t["function"]["name"] for t in (tools or []) if "function" in t}

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


def _testi(contenuto: Any) -> list[str]:
    """Le parti testuali di un messaggio (stringa semplice o lista di parti)."""
    if isinstance(contenuto, str):
        return [contenuto]
    if isinstance(contenuto, list):
        return [p["text"] for p in contenuto if isinstance(p, dict) and p.get("type") == "text"]
    return []
