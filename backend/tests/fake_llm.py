"""Doppio di ``litellm.completion`` per i test: un "modello" deterministico.

Simula un agente che segue la skill: legge il documento della fixture (testo, via
pymupdf — il layout delle fixtures è fatto apposta), chiama i tool nell'ordine
naturale (ocr_pdf → cerca_fornitore → cerca_cantiere) leggendo i loro risultati
dalla conversazione, e consegna il JSON ``{dati, confidence}``.

Compiti, riconosciuti dal marker nella skill (primo messaggio system):

- "Classificazione del documento" → legge l'intestazione e dice il tipo.
- "Estrazione fattura" → trascrive la fattura (con lo scenario ritenuta M5).
- "Estrazione DDT|SAL|rapportino" → trascrive il documento (percorso generico).

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
    """'8.330,00' → 8330.0 (dal formato italiano stampato nei documenti)."""
    return float(testo.replace(".", "").replace(",", "."))


def _testo_documento(percorso: Path) -> str:
    with pymupdf.open(percorso) as documento:
        return "\n".join(pagina.get_text() for pagina in documento)


def _righe_utili(testo: str) -> list[str]:
    return [riga.strip() for riga in testo.splitlines() if riga.strip()]


def _data_iso(giorno: str, mese: str, anno: str) -> str:
    return f"{anno}-{mese}-{giorno}"


def _leggi_fattura(percorso: Path) -> dict[str, Any]:
    testo = _testo_documento(percorso)
    righe_doc = _righe_utili(testo)

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
        "data_iso": _data_iso(testata.group(2), testata.group(3), testata.group(4)),
        "imponibile": euro("Imponibile"),
        "iva": euro(r"IVA \d+%"),
        "totale": euro("TOTALE"),
        "ritenuta": euro(r"Ritenuta d'acconto \d+%"),
        "righe": righe,
    }


# ---------- lettori dei documenti "semplici" (DDT/SAL/rapportino) ----------
# Ognuno ritorna {query_fornitore?, query_cantiere?, dati}: il fake riempie
# fornitore_id/cantiere_id dai risultati dei tool, come farebbe il modello.


def _leggi_ddt(percorso: Path) -> dict[str, Any]:
    testo = _testo_documento(percorso)
    righe_doc = _righe_utili(testo)
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
        "query_fornitore": righe_doc[0],
        "query_cantiere": cantiere.group(1).strip() if cantiere else "",
        "dati": {
            "fornitore_id": None,
            "cantiere_id": None,
            "numero": testata.group(1),
            "data": _data_iso(testata.group(2), testata.group(3), testata.group(4)),
            "causale": campo("Causale"),
            "riferimento_ordine": campo(r"Rif\. ordine"),
            "righe": righe,
        },
    }


def _leggi_sal(percorso: Path) -> dict[str, Any]:
    testo = _testo_documento(percorso)
    testata = re.search(r"SAL N\. (\S+) del (\d{2})/(\d{2})/(\d{4})", testo)
    if not testata:
        raise AssertionError(f"fixture SAL illeggibile: {percorso}")

    def euro(etichetta: str) -> float | None:
        match = re.search(etichetta + r": EUR ([\d.,]+)", testo)
        return _importo(match.group(1)) if match else None

    cantiere = re.search(r"Cantiere: (.+)", testo)
    percentuale = re.search(r"Avanzamento complessivo: ([\d.,]+) %", testo)
    return {
        "query_cantiere": cantiere.group(1).strip() if cantiere else "",
        "dati": {
            "cantiere_id": None,
            "numero": testata.group(1),
            "data": _data_iso(testata.group(2), testata.group(3), testata.group(4)),
            "importo_lavori": euro("Importo lavori contrattuali"),
            "importo_progressivo": euro("Lavori eseguiti a tutto il presente SAL"),
            "percentuale_avanzamento": _importo(percentuale.group(1)) if percentuale else None,
        },
    }


def _leggi_rapportino(percorso: Path) -> dict[str, Any]:
    testo = _testo_documento(percorso)
    testata = re.search(r"Data: (\d{2})/(\d{2})/(\d{4})", testo)
    if not testata:
        raise AssertionError(f"fixture rapportino illeggibile: {percorso}")

    righe = []
    for riga in _righe_utili(testo):
        match = re.fullmatch(r"(.+?) \| (.+?) \| (.+?) \| (.+)", riga)
        if not match or match.group(1) == "Nominativo":
            continue
        mansione = match.group(2).strip()
        costo = match.group(4).strip()
        righe.append(
            {
                "nominativo": match.group(1).strip(),
                "mansione": None if mansione == "-" else mansione,
                "ore": _importo(match.group(3).strip()),
                "costo_orario": None if costo == "-" else _importo(costo),
            }
        )

    cantiere = re.search(r"Cantiere: (.+)", testo)
    return {
        "query_cantiere": cantiere.group(1).strip() if cantiere else "",
        "dati": {
            "cantiere_id": None,
            "data": _data_iso(testata.group(1), testata.group(2), testata.group(3)),
            "righe": righe,
        },
    }


LETTORI = {"ddt": _leggi_ddt, "sal": _leggi_sal, "rapportino": _leggi_rapportino}


def _tipo_estrazione(skill: str) -> str | None:
    for marker, tipo in (("Estrazione DDT", "ddt"), ("Estrazione SAL", "sal"),
                         ("Estrazione rapportino", "rapportino")):
        if marker in skill:
            return tipo
    return None


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
        tipo = _tipo_estrazione(skill)
        if tipo:
            return self._estrai_semplice(model, messages, tools, tipo)
        return self._estrai_fattura(model, messages, tools, skill)

    # ------------------------------------------------------- classificazione

    def _classifica(self, model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        testo = _testo_documento(self.data_dir / self._doc_path(messages)).lower()
        if "stato avanzamento" in testo or "s.a.l" in testo:
            tipo = "sal"
        elif "rapportino" in testo:
            tipo = "rapportino"
        elif "documento di trasporto" in testo or "d.d.t" in testo:
            tipo = "ddt"
        else:
            tipo = "fattura"
        return self._risposta_finale(
            model, json.dumps({"tipo": tipo, "confidence": 0.95}, ensure_ascii=False)
        )

    # ---------------------------------------- estrazione generica (DDT/SAL/…)

    def _estrai_semplice(
        self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None,
        tipo: str,
    ) -> dict[str, Any]:
        doc = self._doc_path(messages)
        gia_chiamati = self._tool_chiamati(messages)
        offerti = self._offerti(tools)
        if "ocr_pdf" in offerti and "ocr_pdf" not in gia_chiamati:
            return self._risposta_tool(model, "ocr_pdf", {"path": doc})

        lettura = LETTORI[tipo](self.data_dir / doc)
        query_forn = lettura.get("query_fornitore")
        query_cant = lettura.get("query_cantiere")
        if "cerca_fornitore" in offerti and "cerca_fornitore" not in gia_chiamati and query_forn:
            return self._risposta_tool(model, "cerca_fornitore", {"query": query_forn})
        if "cerca_cantiere" in offerti and "cerca_cantiere" not in gia_chiamati and query_cant:
            return self._risposta_tool(model, "cerca_cantiere", {"query": query_cant})

        dati = dict(lettura["dati"])
        if "fornitore_id" in dati:
            dati["fornitore_id"] = self._miglior_id(messages, "cerca_fornitore")
        if "cantiere_id" in dati:
            dati["cantiere_id"] = self._miglior_id(messages, "cerca_cantiere")
        self.risposte_finali += 1
        confidence = self.confidence_override or dict.fromkeys(dati, 0.96)
        # Riferimento non trovato (ricerca vuota → id null): registra i dati grezzi.
        rif = {}
        if dati.get("fornitore_id") is None and lettura.get("query_fornitore"):
            rif["fornitore_id"] = {"ragione_sociale": lettura["query_fornitore"]}
        if dati.get("cantiere_id") is None and lettura.get("query_cantiere"):
            rif["cantiere_id"] = {"nome": lettura["query_cantiere"]}
        if rif:
            dati["riferimenti_estratti"] = rif
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
        offerti = self._offerti(tools)
        if tools and "cerca_fornitore" not in gia_chiamati:
            return self._risposta_tool(model, "cerca_fornitore", {"query": campi["fornitore"]})
        if tools and "cerca_cantiere" not in gia_chiamati:
            return self._risposta_tool(model, "cerca_cantiere", {"query": campi["cantiere"]})

        # M17: se la skill ha imparato a usare il tool e la fattura riporta una
        # ritenuta (dicitura sul documento), il fake ne fa CALCOLARE l'importo al
        # tool invece di trascriverlo. Se sul documento non c'è ritenuta, resta
        # `null` come prima: il tool non si inventa un valore.
        usa_tool = (
            "calcola_ritenuta" in skill
            and "calcola_ritenuta" in offerti
            and campi["ritenuta"] is not None
        )
        if usa_tool and "calcola_ritenuta" not in gia_chiamati and campi["imponibile"] is not None:
            return self._risposta_tool(
                model, "calcola_ritenuta", {"imponibile": campi["imponibile"]}
            )

        dati = {
            "fornitore_id": self._miglior_id(messages, "cerca_fornitore"),
            "cantiere_id": self._miglior_id(messages, "cerca_cantiere"),
            "numero": campi["numero"],
            "data": campi["data_iso"],
            "imponibile": campi["imponibile"],
            "iva": campi["iva"],
            "totale": campi["totale"],
            "ritenuta_acconto": self._ritenuta(messages, skill, campi, usa_tool),
            "righe": campi["righe"],
        }
        self.risposte_finali += 1
        if self.totale_errato_restanti > 0:
            self.totale_errato_restanti -= 1
            dati["totale"] = round(dati["totale"] + 100, 2)
        confidence = self.confidence_override or dict.fromkeys(dati, 0.97)
        # Riferimento non trovato in anagrafica (ricerca vuota → id null): come la
        # skill, registra i dati grezzi letti sul documento in `riferimenti_estratti`.
        rif = {}
        if dati["fornitore_id"] is None:
            rif["fornitore_id"] = {"ragione_sociale": campi["fornitore"]}
        if dati["cantiere_id"] is None:
            rif["cantiere_id"] = {"nome": campi["cantiere"]}
        if rif:
            dati["riferimenti_estratti"] = rif
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

    def _ritenuta(
        self,
        messages: list[dict[str, Any]],
        skill: str,
        campi: dict[str, Any],
        usa_tool: bool,
    ) -> float | None:
        """La ritenuta secondo le istruzioni della skill (M5 e M17).

        - col tool: prende il risultato di ``calcola_ritenuta``; se il tool è
          andato in errore (fallback), ricade sulla lettura dal documento;
        - senza tool: la cerca in calce solo se la skill lo dice (scenario M5).
        """
        if usa_tool:
            esito = self._risultato_tool(messages, "calcola_ritenuta")
            if isinstance(esito, dict) and "ritenuta_acconto" in esito:
                return esito["ritenuta_acconto"]
            return campi["ritenuta"]  # tool in errore → fallback all'LLM (legge dal doc)
        return campi["ritenuta"] if "calce" in skill.lower() else None

    @staticmethod
    def _risultato_tool(messages: list[dict[str, Any]], nome_tool: str) -> Any:
        """Il risultato (parsed) dell'ultima chiamata a ``nome_tool`` nella conversazione."""
        id_chiamata = None
        trovato = None
        for messaggio in messages:
            for chiamata in messaggio.get("tool_calls") or []:
                if chiamata["function"]["name"] == nome_tool:
                    id_chiamata = chiamata["id"]
            if (
                id_chiamata
                and messaggio.get("role") == "tool"
                and messaggio.get("tool_call_id") == id_chiamata
            ):
                try:
                    trovato = json.loads(messaggio["content"])
                except (ValueError, TypeError):
                    trovato = None
                id_chiamata = None
        return trovato

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
