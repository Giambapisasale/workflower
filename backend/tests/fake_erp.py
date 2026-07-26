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


class ErpServerFinto:
    """Finto server Frappe/ERPNext in memoria, per gli e2e della sincronizzazione.

    Simula il minimo di REST che serve alla Facade: ``POST /api/resource/<DocType>``
    crea un documento con un ``name`` (idempotenza a valle sui filtri), ``GET`` con
    ``filters`` cerca fra i documenti creati. ``errore_su`` fa fallire (HTTP 500) un
    dato DocType, per provare il ramo best-effort (issue + ledger).
    """

    def __init__(self, errore_su: set[str] | None = None) -> None:
        self.per_doctype: dict[str, list[dict[str, Any]]] = {}
        self.contatori: dict[str, int] = {}
        self.chiamate: list[dict[str, Any]] = []
        self._errore_su = errore_su or set()

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
            return RispostaFinta(200, {"data": self._crea(doctype, json or {})})
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

    # ---------------------------------------------------------------- interni

    @staticmethod
    def _doctype_e_nome(url: str) -> tuple[str, str | None]:
        """Estrae (DocType, name) da un URL ``/api/resource/<DocType>[/<name>][?...]``."""
        from urllib.parse import unquote

        coda = url.split("/api/resource/", 1)[-1].split("?", 1)[0]
        parti = coda.split("/", 1)
        doctype = parti[0]
        nome = unquote(parti[1]) if len(parti) > 1 and parti[1] else None
        return doctype, nome

    def _per_nome(self, doctype: str, nome: str) -> dict[str, Any] | None:
        for rec in self.per_doctype.get(doctype, []):
            if rec.get("name") == nome:
                return rec
        return None

    def _crea(self, doctype: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.contatori[doctype] = self.contatori.get(doctype, 0) + 1
        nome = (
            payload.get("supplier_name")
            or payload.get("cost_center_name")
            or f"{doctype}-{self.contatori[doctype]:04d}"
        )
        record = {**payload, "name": nome}
        self.per_doctype.setdefault(doctype, []).append(record)
        return record

    def _filtra(self, doctype: str, url: str) -> list[dict[str, Any]]:
        import json as _json
        from urllib.parse import parse_qs, urlparse

        q = parse_qs(urlparse(url).query)
        filtri = _json.loads(q.get("filters", ["[]"])[0])  # coppie [campo, op, valore]
        trovati = []
        for rec in self.per_doctype.get(doctype, []):
            if all(rec.get(campo) == valore for campo, op, valore in filtri if op == "="):
                trovati.append({"name": rec["name"]})
        return trovati
