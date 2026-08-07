"""Trasporto ERP finto per i test (nessun ERPNext reale).

Speculare a ``fake_llm.FakeCompleter``: sostituisce il trasporto iniettabile di
``ErpClient`` (firma httpx-compatibile), registra le chiamate fatte e risponde con
corpi/stati predefiniti — così i test verificano header, payload, idempotenza e
gestione degli errori senza rete.
"""

from typing import Any


class RispostaFinta:
    """Minimo indispensabile che ``ErpClient`` si aspetta da una risposta httpx."""

    def __init__(self, status_code: int = 200, corpo: Any | None = None) -> None:
        self.status_code = status_code
        self._corpo = corpo if corpo is not None else {}
        self.text = str(self._corpo)

    def json(self) -> Any:
        return self._corpo


class FakeTrasporto:
    """Trasporto ERP iniettabile.

    - ``risposte``: coda di ``RispostaFinta`` (o dict ``{status_code, corpo}``)
      restituite in ordine; esaurita la coda ritorna ``200 {"data": {}}``.
    - ``errore``: se valorizzato, ogni chiamata solleva quell'eccezione (simula
      un ERP irraggiungibile).
    - ``chiamate``: la lista delle chiamate ricevute, per le asserzioni.
    """

    def __init__(
        self,
        risposte: list[RispostaFinta | dict[str, Any]] | None = None,
        errore: Exception | None = None,
    ) -> None:
        self.chiamate: list[dict[str, Any]] = []
        self._risposte = list(risposte or [])
        self._errore = errore

    def __call__(
        self,
        metodo: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        timeout: float | None = None,
    ) -> RispostaFinta:
        self.chiamate.append(
            {
                "metodo": metodo,
                "url": url,
                "headers": headers or {},
                "json": json,
                "timeout": timeout,
            }
        )
        if self._errore is not None:
            raise self._errore
        if self._risposte:
            prossima = self._risposte.pop(0)
            if isinstance(prossima, RispostaFinta):
                return prossima
            return RispostaFinta(**prossima)
        return RispostaFinta(200, {"data": {}})


# Campi che ERPNext pretende davvero e che un finto troppo gentile lascerebbe
# passare. Sono costati tre bug scoperti solo contro un'istanza reale:
# Cost Center senza padre, righe Purchase Invoice senza conto di costo, righe
# Purchase Receipt senza articolo. Il finto li rifiuta con HTTP 417 come Frappe,
# così il caso è coperto dai test e non torna più.
OBBLIGATORI_TESTATA: dict[str, tuple[str, ...]] = {
    "Cost Center": ("parent_cost_center",),
    "Project": ("project_name",),
    "Address": ("address_title", "address_line1", "city", "country"),
    "Contact": ("first_name",),
    "Supplier Group": ("supplier_group_name",),
    "Asset": ("item_code", "location", "gross_purchase_amount", "purchase_date"),
    "Asset Repair": ("asset", "failure_date"),
    "Item": ("item_code", "item_group"),
    "Item Price": ("item_code", "price_list"),
    "UOM": ("uom_name",),
    "Employee": (
        "first_name",
        "gender",
        "date_of_birth",
        "date_of_joining",
        "status",
        "company",
    ),
    "Activity Type": ("activity_type",),
    "Timesheet": ("employee",),
    "Budget": ("budget_against", "company", "cost_center", "fiscal_year"),
}
# (tabella figlia, campi obbligatori per riga): i Timesheet usano time_logs, i
# documenti d'acquisto items — come i DocType veri.
OBBLIGATORI_RIGHE: dict[str, tuple[str, tuple[str, ...]]] = {
    "Purchase Invoice": ("items", ("expense_account",)),
    "Purchase Receipt": ("items", ("item_code",)),
    "Timesheet": ("time_logs", ("from_time", "hours")),
}

# Firma reale di ``frappe.client.attach_file`` (apps/frappe/frappe/client.py):
# Frappe filtra i kwargs sulla firma, quindi un parametro chiamato col nome
# sbagliato sparisce in silenzio e la funzione prosegue con ``doctype=None``.
PARAMETRI_ATTACH_FILE: tuple[str, ...] = (
    "filename",
    "filedata",
    "doctype",
    "docname",
    "folder",
    "decode_base64",
    "is_private",
    "docfield",
)

# Campo del payload che fa da ``name`` del record creato (come l'autoname Frappe).
_CAMPI_NOME: dict[str, str] = {
    "Supplier": "supplier_name",
    "Cost Center": "cost_center_name",
    "Project": "project_name",
    "Supplier Group": "supplier_group_name",
    "Contact": "first_name",
    "Asset": "asset_name",
    "Item": "item_code",
    "UOM": "uom_name",
    "Activity Type": "activity_type",
}

# Filtri su tabella figlia ([DocType figlio, campo, op, valore]): dove guardare
# dentro al record padre. Come Frappe filtra Address/Contact per Dynamic Link.
_TABELLE_FIGLIE: dict[str, str] = {
    "Dynamic Link": "links",
    "Payment Entry Reference": "references",
}


class ErpServerFinto:
    """Finto server Frappe/ERPNext in memoria, per gli e2e della sincronizzazione.

    Simula il minimo di REST che serve alla Facade: ``POST /api/resource/<DocType>``
    crea un documento con un ``name`` (idempotenza a valle sui filtri), ``GET`` con
    ``filters`` cerca fra i documenti creati. ``errore_su`` fa fallire (HTTP 500) un
    dato DocType, per provare il ramo best-effort (issue + ledger).

    Riproduce anche la **severità** di ERPNext sui campi obbligatori (vedi
    :data:`OBBLIGATORI_TESTATA` / :data:`OBBLIGATORI_RIGHE`): un payload incompleto
    riceve 417 come dall'istanza reale, non un 200 di cortesia. Con ``permissivo=True``
    si torna al comportamento gentile, per i test che non stanno provando il mapping.
    """

    def __init__(
        self,
        errore_su: set[str] | None = None,
        *,
        permissivo: bool = False,
        company: str = "Edile SpA",
        conto_costo: str = "Costi - E",
    ) -> None:
        self.per_doctype: dict[str, list[dict[str, Any]]] = {}
        self.contatori: dict[str, int] = {}
        self.chiamate: list[dict[str, Any]] = []
        self._errore_su = errore_su or set()
        self._permissivo = permissivo
        # Master data che ogni ERPNext configurato possiede e che la Facade legge per
        # derivare padre dei cost center e conto di costo: la Company e il Cost Center
        # radice omonimo. Presenti dall'inizio, come in un'istanza reale.
        self.per_doctype["Company"] = [
            {"name": company, "default_expense_account": conto_costo}
        ]
        self.per_doctype["Cost Center"] = [
            {
                "name": f"{company} - E",
                "company": company,
                "is_group": 1,
                "parent_cost_center": "",
            }
        ]

    def __call__(
        self,
        metodo: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        timeout: float | None = None,
    ) -> RispostaFinta:
        self.chiamate.append({"metodo": metodo, "url": url, "json": json})
        if "/api/method/" in url:
            return self._metodo(url, json or {})
        doctype, nome = self._doctype_e_nome(url)
        if doctype in self._errore_su:
            return RispostaFinta(500, {"exc": f"errore simulato su {doctype}"})
        if metodo == "GET":
            if nome:  # GET /api/resource/<DocType>/<name>
                doc = self._per_nome(doctype, nome)
                if doc is None:
                    return RispostaFinta(404, {"exc": f"{doctype} {nome} non trovato"})
                return RispostaFinta(200, {"data": doc})
            return RispostaFinta(200, {"data": self._filtra(doctype, url)})
        if metodo == "POST":
            mancante = self._campo_mancante(doctype, json or {})
            if mancante:
                return RispostaFinta(
                    417, {"exception": f"ValidationError: {mancante} è obbligatorio"}
                )
            return RispostaFinta(200, {"data": self._crea(doctype, json or {})})
        if metodo == "PUT":
            if not nome:
                return RispostaFinta(405, {"exc": "PUT senza nome documento"})
            doc = self._per_nome(doctype, nome)
            if doc is None:
                return RispostaFinta(404, {"exc": f"{doctype} {nome} non trovato"})
            doc.update(json or {})
            return RispostaFinta(200, {"data": doc})
        return RispostaFinta(405, {"exc": f"metodo {metodo} non gestito"})

    def documenti(self, doctype: str) -> list[dict[str, Any]]:
        return self.per_doctype.get(doctype, [])

    def post_di(self, doctype: str) -> list[dict[str, Any]]:
        """I payload POST ricevuti per un DocType (per le asserzioni degli e2e)."""
        return [
            c["json"]
            for c in self.chiamate
            if c["metodo"] == "POST" and self._doctype_e_nome(c["url"])[0] == doctype
        ]

    def ripristina(self) -> None:
        """L'ERP torna su: azzera i DocType che stavano fallendo (per i test di recupero)."""
        self._errore_su = set()

    def guasta(self, *doctype: str) -> None:
        """Fa fallire (HTTP 500) i DocType indicati, anche dopo che sono stati creati."""
        self._errore_su |= set(doctype)

    def paga_fattura(self, name: str, *, grand_total: float, outstanding: float) -> None:
        """Imposta lo stato di pagamento di una Purchase Invoice creata (per il read-back)."""
        doc = self._per_nome("Purchase Invoice", name)
        if doc is None:
            raise KeyError(f"Purchase Invoice {name} inesistente")
        doc["grand_total"] = grand_total
        doc["outstanding_amount"] = outstanding

    def registra_pagamento(
        self, pi_name: str, posting_date: str, *, docstatus: int = 1
    ) -> dict[str, Any]:
        """Crea un Payment Entry confermato che riferisce la Purchase Invoice.

        È la sorgente della *data* di pagamento nel read-back (M31): la PI porta
        solo importi/outstanding, la data vive sui Payment Entry.
        """
        self.contatori["Payment Entry"] = self.contatori.get("Payment Entry", 0) + 1
        record = {
            "name": f"PE-{self.contatori['Payment Entry']:04d}",
            "docstatus": docstatus,
            "posting_date": posting_date,
            "references": [
                {"reference_doctype": "Purchase Invoice", "reference_name": pi_name}
            ],
        }
        self.per_doctype.setdefault("Payment Entry", []).append(record)
        return record

    def conferma(self, doctype: str, name: str) -> None:
        """Submit del documento (``docstatus`` 1): da qui in poi è nei conti."""
        self._imposta_docstatus(doctype, name, 1)

    def annulla(self, doctype: str, name: str) -> None:
        """Cancel del documento (``docstatus`` 2): la condizione che sblocca lo scarto."""
        self._imposta_docstatus(doctype, name, 2)

    def elimina(self, doctype: str, name: str) -> None:
        """Il documento a valle non c'è più: da qui in poi il GET risponde 404."""
        documenti = self.per_doctype.get(doctype, [])
        self.per_doctype[doctype] = [d for d in documenti if d.get("name") != name]

    def _imposta_docstatus(self, doctype: str, name: str, valore: int) -> None:
        doc = self._per_nome(doctype, name)
        if doc is None:
            raise KeyError(f"{doctype} {name} inesistente")
        doc["docstatus"] = valore

    # ---------------------------------------------------------------- interni

    def _metodo(self, url: str, payload: dict[str, Any]) -> RispostaFinta:
        """I metodi whitelisted Frappe che il client usa (per ora ``attach_file``).

        Severo come il reale su due fronti. Primo: i **nomi dei parametri** sono
        quelli della firma, e i kwargs fuori firma vengono scartati come li scarta
        Frappe — chiamare ``attached_to_doctype`` invece di ``doctype`` non è un
        417 gentile, è il 500 da ``get_doc(None, None)`` che si vede in campo.
        Secondo: allegare a un documento inesistente è un 404, non un 200 di
        cortesia; ``guasta("File")`` simula l'upload che fallisce.
        """
        nome_metodo = url.split("/api/method/", 1)[-1].split("?", 1)[0]
        if nome_metodo != "frappe.client.attach_file":
            return RispostaFinta(404, {"exc": f"metodo {nome_metodo} non gestito dal finto"})
        if "File" in self._errore_su:
            return RispostaFinta(500, {"exc": "errore simulato su File"})
        argomenti = {k: v for k, v in payload.items() if k in PARAMETRI_ATTACH_FILE}
        if not argomenti.get("doctype") or not argomenti.get("docname"):
            return RispostaFinta(
                500,
                {
                    "exception": "ValueError: First non keyword argument must be a string or dict",
                    "exc_type": "ValueError",
                },
            )
        if not argomenti.get("filename"):
            return RispostaFinta(417, {"exception": "ValidationError: filename è obbligatorio"})
        if self._per_nome(argomenti["doctype"], argomenti["docname"]) is None:
            return RispostaFinta(
                404,
                {"exc": f"{argomenti['doctype']} {argomenti['docname']} non trovato"},
            )
        self.contatori["File"] = self.contatori.get("File", 0) + 1
        record = {
            "name": f"FILE-{self.contatori['File']:04d}",
            "file_name": argomenti["filename"],
            # sul DocType File i campi si chiamano così; i parametri del metodo no
            "attached_to_doctype": argomenti["doctype"],
            "attached_to_name": argomenti["docname"],
            "is_private": argomenti.get("is_private", 0),
        }
        self.per_doctype.setdefault("File", []).append(record)
        return RispostaFinta(200, {"message": record})

    @staticmethod
    def _doctype_e_nome(url: str) -> tuple[str, str | None]:
        """Estrae (DocType, name) da un URL ``/api/resource/<DocType>[/<name>][?...]``."""
        from urllib.parse import unquote

        coda = url.split("/api/resource/", 1)[-1].split("?", 1)[0]
        parti = coda.split("/", 1)
        doctype = parti[0]
        nome = unquote(parti[1]) if len(parti) > 1 and parti[1] else None
        return doctype, nome

    def _campo_mancante(self, doctype: str, payload: dict[str, Any]) -> str | None:
        """Il primo campo obbligatorio assente, come lo rifiuterebbe ERPNext."""
        if self._permissivo:
            return None
        for campo in OBBLIGATORI_TESTATA.get(doctype, ()):
            if not payload.get(campo):
                return campo
        tabella, campi = OBBLIGATORI_RIGHE.get(doctype, ("items", ()))
        for campo in campi:
            for riga in payload.get(tabella) or []:
                if not riga.get(campo):
                    return f"{tabella}.{campo}"
        return None

    def _per_nome(self, doctype: str, nome: str) -> dict[str, Any] | None:
        for rec in self.per_doctype.get(doctype, []):
            if rec.get("name") == nome:
                return rec
        return None

    def _crea(self, doctype: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.contatori[doctype] = self.contatori.get(doctype, 0) + 1
        if doctype == "Address" and payload.get("address_title"):
            # Frappe nomina gli Address "titolo-tipo" (es. "Rossi Srl-Billing").
            nome = f"{payload['address_title']}-{payload.get('address_type', 'Billing')}"
        else:
            campo_nome = _CAMPI_NOME.get(doctype)
            nome = (payload.get(campo_nome) if campo_nome else None) or (
                f"{doctype}-{self.contatori[doctype]:04d}"
            )
        # Come Frappe: un POST senza ``docstatus`` crea una **bozza** (0), non un
        # documento confermato. Workflower non fa submit, quindi è ciò che accade
        # davvero a valle — verificato contro l'istanza reale.
        record = {"docstatus": 0, **payload, "name": nome}
        self.per_doctype.setdefault(doctype, []).append(record)
        return record

    def _filtra(self, doctype: str, url: str) -> list[dict[str, Any]]:
        import json as _json
        from urllib.parse import parse_qs, urlparse

        q = parse_qs(urlparse(url).query)
        # [campo, op, valore] sul record; [DocType figlio, campo, op, valore] sulla
        # tabella figlia (es. Dynamic Link, Payment Entry Reference) — come Frappe.
        filtri = _json.loads(q.get("filters", ["[]"])[0])
        # Come Frappe: senza `fields` torna il solo name, altrimenti i campi chiesti.
        campi = _json.loads(q.get("fields", ["[]"])[0]) or ["name"]
        trovati = []
        for rec in self.per_doctype.get(doctype, []):
            if all(self._filtro_passa(rec, f) for f in filtri):
                trovati.append({c: rec.get(c) for c in campi})
        return trovati

    @staticmethod
    def _filtro_passa(rec: dict[str, Any], filtro: list[Any]) -> bool:
        if len(filtro) == 4:
            figlio, campo, op, valore = filtro
            chiave = _TABELLE_FIGLIE.get(figlio)
            if chiave is None:
                return False
            righe = rec.get(chiave) or []
            return op == "=" and any(r.get(campo) == valore for r in righe)
        campo, op, valore = filtro
        return op != "=" or rec.get(campo) == valore
