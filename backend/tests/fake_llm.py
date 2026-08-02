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

from app.core.docling import ESTENSIONI as FORMATI_LEGGI_DOCUMENTO

# La soglia con cui le skill accettano un candidato delle anagrafiche. Vive qui
# perché il fake deve *rifiutare* come il reale: sotto questo punteggio non si
# collega niente.
SOGLIA_RIFERIMENTO = 0.75


def _importo(testo: str) -> float:
    """'8.330,00' → 8330.0 (dal formato italiano stampato nei documenti)."""
    return float(testo.replace(".", "").replace(",", "."))


def _testo_documento(sorgente: Path | str) -> str:
    """Il testo del documento: estratto dal PDF su disco, oppure già pronto.

    I lettori accettano entrambe le forme perché il modello vero è nella stessa
    situazione: o guarda le pagine come immagini e il testo se lo ricava lui
    (``ocr_pdf``), oppure riceve il Markdown già pronto (``leggi_documento``).
    Passare una stringa significa "questo documento l'hai già letto con un tool".
    """
    if isinstance(sorgente, str):
        return sorgente
    with pymupdf.open(sorgente) as documento:
        return "\n".join(pagina.get_text() for pagina in documento)


def _righe_utili(testo: str) -> list[str]:
    """Le righe non vuote, con le tabelle Markdown normalizzate.

    Docling restituisce le tabelle come ``| cella | cella |``, il testo di un PDF
    come ``cella | cella``. Un modello vero non nota la differenza; il fake, per
    non notarla, toglie le pipe di bordo e scarta le righe-separatore. Senza
    questo, lo stesso documento letto nei due modi darebbe risultati diversi — e
    il test misurerebbe il parser del fake, non il sistema.
    """
    righe = []
    for grezza in testo.splitlines():
        riga = grezza.strip()
        if not riga:
            continue
        if riga.startswith("|") and riga.endswith("|"):
            riga = riga[1:-1].strip()
            if set(riga.replace("|", "").replace(" ", "")) <= {"-", ":"}:
                continue  # riga di separazione dell'intestazione
        righe.append(riga)
    return righe


def _data_iso(giorno: str, mese: str, anno: str) -> str:
    return f"{anno}-{mese}-{giorno}"


def _destinatario(testo: str) -> str | None:
    """La ragione sociale dopo «Spett.le», senza l'indirizzo che la segue.

    Come chiede la skill: solo il nome, non la riga intera. Un finto che
    restituisse la riga completa renderebbe il confronto più facile del vero.
    """
    match = re.search(r"Spett\.le\s+(.+)", testo)
    if not match:
        return None
    return re.split(r"\s+[-—]\s+", match.group(1).strip())[0].strip() or None


def _leggi_fattura(sorgente: Path | str) -> dict[str, Any]:
    testo = _testo_documento(sorgente)
    righe_doc = _righe_utili(testo)

    testata = re.search(r"FATTURA N\. (\S+) del (\d{2})/(\d{2})/(\d{4})", testo)
    if not testata:
        raise AssertionError(f"fixture illeggibile: {sorgente}")

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
        "destinatario": _destinatario(testo),
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


def _leggi_ddt(sorgente: Path | str) -> dict[str, Any]:
    testo = _testo_documento(sorgente)
    righe_doc = _righe_utili(testo)
    testata = re.search(r"DDT N\. (\S+) del (\d{2})/(\d{2})/(\d{4})", testo)
    if not testata:
        raise AssertionError(f"fixture DDT illeggibile: {sorgente}")

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


def _leggi_sal(sorgente: Path | str) -> dict[str, Any]:
    testo = _testo_documento(sorgente)
    testata = re.search(r"SAL N\. (\S+) del (\d{2})/(\d{2})/(\d{4})", testo)
    if not testata:
        raise AssertionError(f"fixture SAL illeggibile: {sorgente}")

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


def _leggi_rapportino(sorgente: Path | str) -> dict[str, Any]:
    testo = _testo_documento(sorgente)
    testata = re.search(r"Data: (\d{2})/(\d{2})/(\d{4})", testo)
    if not testata:
        raise AssertionError(f"fixture rapportino illeggibile: {sorgente}")

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
                "dipendente_id": None,  # lo risolve cerca_dipendente, riga per riga
                "mansione": None if mansione == "-" else mansione,
                "ore": _importo(match.group(3).strip()),
                "costo_orario": None if costo == "-" else _importo(costo),
            }
        )

    cantiere = re.search(r"Cantiere: (.+)", testo)
    return {
        "query_cantiere": cantiere.group(1).strip() if cantiere else "",
        "query_dipendenti": list(dict.fromkeys(r["nominativo"] for r in righe)),
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

    def _testo_classificazione(self, messages: list[dict[str, Any]]) -> str:
        """Il documento come lo riceve il classificatore: testo nel prompt, o file.

        Col sidecar attivo il classificatore manda il Markdown dentro al prompt
        invece delle pagine come immagini; il fake deve leggere *quello*, sia per
        misurare la strada giusta sia perché su un ``.docx`` non c'è alternativa.
        """
        for messaggio in messages:
            for testo in _testi(messaggio.get("content")):
                match = re.search(r"Documento da classificare: \S+\n\n(.+)", testo, re.S)
                if match:
                    return match.group(1)
        return _testo_documento(self.data_dir / self._doc_path(messages))

    def _classifica(self, model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        testo = self._testo_classificazione(messages).lower()
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
        da_leggere = self._lettura_da_fare(messages, offerti, gia_chiamati, doc)
        if da_leggere:
            return self._risposta_tool(model, da_leggere, {"path": doc})

        lettura = LETTORI[tipo](self._sorgente(messages, doc))
        query_forn = lettura.get("query_fornitore")
        query_cant = lettura.get("query_cantiere")
        if "cerca_fornitore" in offerti and "cerca_fornitore" not in gia_chiamati and query_forn:
            return self._risposta_tool(model, "cerca_fornitore", {"query": query_forn})
        if "cerca_cantiere" in offerti and "cerca_cantiere" not in gia_chiamati and query_cant:
            return self._risposta_tool(model, "cerca_cantiere", {"query": query_cant})
        # Un nominativo per riga, tutte le chiamate in un giro solo: è quello che
        # dice la skill, e il runtime esegue più tool_calls nella stessa risposta.
        query_dip = lettura.get("query_dipendenti") or []
        if "cerca_dipendente" in offerti and "cerca_dipendente" not in gia_chiamati and query_dip:
            return self._risposta_tools(
                model, [("cerca_dipendente", {"query": q}) for q in query_dip]
            )

        dati = dict(lettura["dati"])
        if "fornitore_id" in dati:
            dati["fornitore_id"] = self._miglior_id(messages, "cerca_fornitore")
        if "cantiere_id" in dati:
            dati["cantiere_id"] = self._miglior_id(messages, "cerca_cantiere")
        if query_dip:
            risolti = self._risolti(messages, "cerca_dipendente")
            for riga in dati["righe"]:
                riga["dipendente_id"] = risolti.get(riga["nominativo"])
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
        offerti = self._offerti(tools)
        da_leggere = self._lettura_da_fare(messages, offerti, gia_chiamati, doc)
        if da_leggere:
            return self._risposta_tool(model, da_leggere, {"path": doc})

        campi = _leggi_fattura(self._sorgente(messages, doc))
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
            "destinatario": campi["destinatario"],
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

    def _lettura_da_fare(
        self,
        messages: list[dict[str, Any]],
        offerti: set[str],
        gia_chiamati: set[str],
        doc: str,
    ) -> str | None:
        """Quale tool di lettura chiamare adesso, o ``None`` se il documento è letto.

        Segue la skill alla lettera: ``leggi_documento`` per i formati nati al
        computer, ``ocr_pdf`` per le foto — **uno solo**, e il secondo soltanto se
        il primo non è bastato. Quando il sidecar non è configurato il tool non è
        fra gli offerti e si va su ``ocr_pdf`` come è sempre stato: è per questo
        che i test esistenti continuano a vedere la stessa sequenza di chiamate.
        """
        preferito = (
            "leggi_documento"
            if Path(doc).suffix.lower() in FORMATI_LEGGI_DOCUMENTO
            else "ocr_pdf"
        )
        if preferito in offerti and preferito not in gia_chiamati:
            return preferito
        if "ocr_pdf" not in offerti or "ocr_pdf" in gia_chiamati:
            return None
        if preferito == "ocr_pdf":
            return "ocr_pdf"
        if preferito not in offerti:
            return "ocr_pdf"  # niente sidecar: le pagine come immagini
        # Il sidecar è stato interpellato ed è andato male: si ripiega sulle
        # immagini, che è esattamente ciò che la skill dice di fare.
        esito = self._risultato_tool(messages, "leggi_documento")
        if isinstance(esito, dict) and "errore" in esito:
            return "ocr_pdf"
        return None

    def _sorgente(self, messages: list[dict[str, Any]], doc: str) -> Path | str:
        """Il documento come ce l'ha in mano il modello a questo punto.

        Se ``leggi_documento`` è andato a buon fine, il contenuto è il Markdown che
        ha restituito — e il fake legge quello, non il file su disco: è l'unico
        modo di provare davvero la strada nuova (e l'unico possibile su un
        ``.docx``, che pymupdf non apre).
        """
        letto = self._risultato_tool(messages, "leggi_documento")
        if isinstance(letto, dict) and isinstance(letto.get("markdown"), str):
            return letto["markdown"]
        return self.data_dir / doc

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

    def _risolti(
        self, messages: list[dict[str, Any]], nome_tool: str
    ) -> dict[str, str | None]:
        """Query → id del miglior candidato, ``None`` sotto soglia.

        Serve quando lo stesso tool è chiamato più volte con argomenti diversi
        (un `cerca_dipendente` per riga): ``_miglior_id`` guarda l'ultima
        chiamata e qui non basterebbe.

        La soglia è la stessa della skill, e questo è il punto: un fake che
        collegasse il meno peggio farebbe passare i test proprio dove il modello
        vero sbaglierebbe di più — attribuire ore e costi a un altro.
        """
        per_id = {}
        for messaggio in messages:
            for chiamata in messaggio.get("tool_calls") or []:
                if chiamata["function"]["name"] == nome_tool:
                    argomenti = json.loads(chiamata["function"]["arguments"])
                    per_id[chiamata["id"]] = argomenti.get("query")
        risolti: dict[str, str | None] = {}
        for messaggio in messages:
            query = per_id.get(str(messaggio.get("tool_call_id")))
            if messaggio.get("role") != "tool" or query is None:
                continue
            risultati = json.loads(messaggio["content"]).get("risultati") or []
            migliore = risultati[0] if risultati else None
            risolti[query] = (
                migliore["id"]
                if migliore and migliore["punteggio"] >= SOGLIA_RIFERIMENTO
                else None
            )
        return risolti

    def _risposta_tool(self, model: str, nome: str, argomenti: dict[str, Any]) -> dict[str, Any]:
        return self._risposta_tools(model, [(nome, argomenti)])

    def _risposta_tools(
        self, model: str, chiamate: list[tuple[str, dict[str, Any]]]
    ) -> dict[str, Any]:
        return self._risposta(
            model,
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call_{self.chiamate}_{indice}",
                        "type": "function",
                        "function": {"name": nome, "arguments": json.dumps(argomenti)},
                    }
                    for indice, (nome, argomenti) in enumerate(chiamate)
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
