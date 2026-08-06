"""Client ERP: unico punto di accesso a ERPNext (anti-corruption layer).

Workflower è il system-of-record dei *documenti* (estrazione + validazione umana);
ERPNext è quello *contabile* a valle. La sincronizzazione è mono-direzionale
(WF→ERP), best-effort, e vive come effetto della validazione (piano ERP, M25) —
mai in ``runtime.py``/``gateway.py``, mai esposta al modello (ADR-4).

Questo modulo è solo la **cornice di accesso** (piano ERP, M23):

- **Config da env**, mai hard-coded (stesso principio dei tier LLM del Gateway):
  ``ERP_BASE_URL`` / ``ERP_API_KEY`` / ``ERP_API_SECRET``. Se una manca,
  :func:`erp_attivo` è falso e la sincronizzazione è un no-op silenzioso — come
  ``Gateway.t3_attivo`` per il tier locale.
- **Client HTTP con trasporto iniettabile** (come ``Gateway(completer=...)``): il
  default usa ``httpx``; i test iniettano un trasporto finto e non toccano mai un
  ERPNext reale.

La costruzione non fa I/O: parlare con l'ERP avviene solo quando si chiama
:meth:`ErpClient.richiesta`. Il *Translator* (envelope→DocType) e la *Facade*
(``sincronizza``) arrivano in M24/M25 e si appoggeranno a questo client.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.dataset import leggi_sync_erp, registra_sync_erp
from app.core.logbook import ottieni_logger
from app.models.envelope import now_iso

_log = ottieni_logger("erp")

# Fallimenti consecutivi oltre i quali il re-sync batch si ferma (ERP verosimilmente
# giù): meglio interrompere che martellare centinaia di documenti a vuoto.
MAX_ERRORI_CONSECUTIVI = 5

# Trasporto: (metodo, url, *, headers, json, timeout) -> risposta con .status_code e .json().
# Firma volutamente httpx-compatibile, così il default è un thin wrapper e il finto
# dei test è banale (vedi tests/fake_erp.py).
Transport = Callable[..., Any]

# Timeout corto: l'ERP è a valle e best-effort; non deve mai rallentare la validazione.
TIMEOUT_DEFAULT = 10.0

# Gruppo Supplier di default (radice ERPNext); la config può passarne uno più specifico.
SUPPLIER_GROUP_DEFAULT = "All Supplier Groups"

# Paese di default degli indirizzi (l'Address di ERPNext lo pretende): i fornitori
# di cantiere sono italiani salvo config contraria (ERP_PAESE).
PAESE_DEFAULT = "Italy"

# Tipi di documento Workflower che vengono riflessi nell'ERP (ciclo passivo).
TIPI_SINCRONIZZABILI = ("fattura", "ddt")


class ErpError(Exception):
    """Errore verso ERPNext: trasporto irraggiungibile, HTTP >= 400 o corpo non JSON.

    ``stato`` porta il codice HTTP quando c'è stata una risposta, ``None`` quando
    non si è arrivati a parlare col server. Distinguere serve: un 404 su un
    documento a valle significa "non c'è più", mentre un trasporto giù significa
    "non lo so" — due decisioni diverse per chi chiama (vedi ``api/scarti.py``).
    """

    def __init__(self, messaggio: str, stato: int | None = None) -> None:
        super().__init__(messaggio)
        self.stato = stato


@dataclass(frozen=True)
class ErpConfig:
    """Coordinate dell'istanza ERPNext + mapping fiscale, letti dall'ambiente.

    ``base_url``/``api_key``/``api_secret`` sono obbligatorie (senza, l'ERP è
    spento). Il resto guida il *Translator* lato Facade e resta opzionale:
    ``company`` (obbligatoria per creare Cost Center e Purchase Invoice reali),
    ``conto_ritenuta``/``conto_iva`` (account_head delle righe tax), ``supplier_group``.

    ``parent_cost_center`` e ``conto_costo`` sono **override**: ERPNext li pretende
    (un Cost Center vuole un padre, una riga senza ``item_code`` vuole un conto di
    costo) ma sono derivabili dalla Company, quindi se non impostati la Facade li
    risolve dall'istanza — vedi :func:`radice_cost_center` e
    :func:`conto_costo_predefinito`.
    """

    base_url: str
    api_key: str
    api_secret: str
    company: str | None = None
    conto_ritenuta: str | None = None
    conto_iva: str | None = None
    supplier_group: str = SUPPLIER_GROUP_DEFAULT
    parent_cost_center: str | None = None
    conto_costo: str | None = None
    item_ddt: str | None = None
    paese: str = PAESE_DEFAULT
    asset_item: str | None = None
    asset_location: str | None = None

    @classmethod
    def da_env(cls) -> "ErpConfig | None":
        """La config se ``ERP_BASE_URL``/``ERP_API_KEY``/``ERP_API_SECRET`` sono tutte
        presenti, altrimenti ``None`` (ERP non configurato → sync no-op)."""
        base = os.environ.get("ERP_BASE_URL")
        key = os.environ.get("ERP_API_KEY")
        secret = os.environ.get("ERP_API_SECRET")
        if not (base and key and secret):
            return None
        return cls(
            base_url=base,
            api_key=key,
            api_secret=secret,
            company=os.environ.get("ERP_COMPANY"),
            conto_ritenuta=os.environ.get("ERP_CONTO_RITENUTA"),
            conto_iva=os.environ.get("ERP_CONTO_IVA"),
            supplier_group=os.environ.get("ERP_SUPPLIER_GROUP") or SUPPLIER_GROUP_DEFAULT,
            parent_cost_center=os.environ.get("ERP_PARENT_COST_CENTER"),
            conto_costo=os.environ.get("ERP_CONTO_COSTO"),
            item_ddt=os.environ.get("ERP_ITEM_DDT"),
            paese=os.environ.get("ERP_PAESE") or PAESE_DEFAULT,
            asset_item=os.environ.get("ERP_ASSET_ITEM"),
            asset_location=os.environ.get("ERP_ASSET_LOCATION"),
        )


def erp_attivo() -> bool:
    """Vero se l'integrazione ERP è cablata (tutte le env ``ERP_*`` presenti).

    Interruttore analogo a ``Gateway.t3_attivo``: finché è spento, la
    sincronizzazione verso l'ERP è un no-op silenzioso e Workflower funziona
    esattamente come prima.
    """
    return ErpConfig.da_env() is not None


def _trasporto_httpx(
    metodo: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json: Any | None = None,
    timeout: float = TIMEOUT_DEFAULT,
) -> httpx.Response:
    """Trasporto reale: una singola richiesta HTTP con ``httpx``."""
    return httpx.request(metodo, url, headers=headers, json=json, timeout=timeout)


class ErpClient:
    """Accesso REST a ERPNext (Frappe). Costruzione senza I/O.

    ``config`` default = :meth:`ErpConfig.da_env`; ``transport`` default = ``httpx``.
    Entrambi iniettabili per i test. Le chiamate falliscono con :class:`ErpError`,
    così il chiamante (la sync best-effort in revisione) può aprire una issue senza
    far cadere la validazione.
    """

    def __init__(
        self,
        config: ErpConfig | None = None,
        transport: Transport | None = None,
        timeout: float = TIMEOUT_DEFAULT,
    ) -> None:
        # Nota: se ``config`` è None si tenta l'env, ma resta None se non configurato.
        self.config = config if config is not None else ErpConfig.da_env()
        self._transport = transport or _trasporto_httpx
        self.timeout = timeout
        # Master data derivato dalla Company (radice dei Cost Center, conto di costo):
        # non cambia durante un giro di sincronizzazione, si legge una volta sola.
        self._master: dict[str, str | None] = {}

    def attivo(self) -> bool:
        return self.config is not None

    def richiesta(
        self, metodo: str, percorso: str, *, json: Any | None = None
    ) -> Any:
        """Una chiamata REST a ERPNext; ritorna il JSON decodificato.

        Frappe autentica con header ``Authorization: token <key>:<secret>`` ed
        espone ogni DocType come risorsa REST. Qualsiasi problema (non configurato,
        trasporto giù, HTTP >= 400, corpo non JSON) diventa :class:`ErpError`.
        """
        if self.config is None:
            raise ErpError(
                "ERP non configurato (ERP_BASE_URL/ERP_API_KEY/ERP_API_SECRET assenti)"
            )
        url = self.config.base_url.rstrip("/") + "/" + percorso.lstrip("/")
        headers = {
            "Authorization": f"token {self.config.api_key}:{self.config.api_secret}",
            "Accept": "application/json",
        }
        # Gli errori qui sotto riportano l'URL **intero**, non solo il percorso: un
        # "timed out" sul solo percorso non distingue «ERP spento» da «indirizzo
        # sbagliato», e il secondo caso è il più frequente in sviluppo (una
        # ERP_BASE_URL ereditata dalla shell vince sul .env — load_dotenv non
        # sovrascrive ciò che è già nell'ambiente).
        _log.debug("%s %s (timeout %ss)", metodo, url, self.timeout)
        try:
            risposta = self._transport(
                metodo, url, headers=headers, json=json, timeout=self.timeout
            )
        except ErpError:
            raise
        except Exception as exc:  # trasporto irraggiungibile / timeout
            raise ErpError(f"ERP non raggiungibile ({metodo} {url}): {exc}") from exc

        stato = getattr(risposta, "status_code", None)
        if stato is None or stato >= 400:
            raise ErpError(
                f"ERP ha risposto {stato} a {metodo} {url}: {_corpo_sicuro(risposta)}",
                stato=stato,
            )
        try:
            return risposta.json()
        except Exception as exc:
            raise ErpError(f"risposta ERP non JSON a {metodo} {url}: {exc}") from exc

    # ------------------------------------------------------------- REST DocType

    def crea_documento(self, doctype: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST di un nuovo DocType; ritorna il record creato (il ``data`` di Frappe)."""
        corpo = self.richiesta("POST", f"/api/resource/{doctype}", json=payload)
        return corpo.get("data", corpo) if isinstance(corpo, dict) else corpo

    def aggiorna_documento(
        self, doctype: str, nome: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """PUT su un DocType esistente; ritorna il record aggiornato.

        Serve al carico anagrafiche (M31): completare un record già a valle — ad es.
        il gruppo di un Supplier nato senza categoria — senza crearne un doppione.
        """
        from urllib.parse import quote

        corpo = self.richiesta("PUT", f"/api/resource/{doctype}/{quote(nome)}", json=payload)
        return corpo.get("data", corpo) if isinstance(corpo, dict) else corpo

    def trova_documenti(
        self,
        doctype: str,
        filtri: list[list[Any]],
        *,
        limite: int = 1,
        campi: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """GET con ``filters`` Frappe; ritorna la lista ``data`` (vuota se nulla).

        Senza ``campi`` Frappe restituisce il solo ``name``; passarli serve quando
        occorre discriminare fra più risultati (es. la radice dei Cost Center).
        """
        import json as _json
        from urllib.parse import urlencode

        parametri: dict[str, Any] = {
            "filters": _json.dumps(filtri),
            "limit_page_length": limite,
        }
        if campi:
            parametri["fields"] = _json.dumps(campi)
        query = urlencode(parametri)
        corpo = self.richiesta("GET", f"/api/resource/{doctype}?{query}")
        dati = corpo.get("data") if isinstance(corpo, dict) else None
        return dati or []

    def chiama_metodo(self, nome: str, payload: dict[str, Any]) -> Any:
        """POST a un metodo whitelisted Frappe (``/api/method/<nome>``).

        Serve dove il REST sui DocType non basta — ad es. ``frappe.client.attach_file``
        per allegare il documento originale al record contabile. Frappe incapsula il
        ritorno in ``message``.
        """
        corpo = self.richiesta("POST", f"/api/method/{nome}", json=payload)
        return corpo.get("message", corpo) if isinstance(corpo, dict) else corpo


def _corpo_sicuro(risposta: Any, limite: int = 500) -> str:
    """Estrae il corpo della risposta per il messaggio d'errore, senza mai sollevare."""
    try:
        testo = getattr(risposta, "text", None)
        if testo is None:
            testo = str(risposta.json())
    except Exception:
        testo = "<corpo non leggibile>"
    return testo[:limite]


# ======================================================================
# Translator: envelope (dati Workflower) -> payload DocType ERPNext
# ======================================================================
# Funzioni PURE: nessun I/O, nessun DAL. Il modello ERPNext non "trapela" negli
# schemi di /data e viceversa: qui vive tutta e sola la conoscenza di come un
# documento Workflower diventa un DocType Frappe. Le referenze già risolte (nome
# del fornitore, cost center del cantiere) arrivano come argomenti — la
# risoluzione FRN-.../CNT-... la fa la Facade (M25) che ha il DAL. Così il mapping
# resta dato testabile con test tabellari.


def fornitore_a_supplier(
    dati: dict[str, Any], *, supplier_group: str = SUPPLIER_GROUP_DEFAULT
) -> dict[str, Any]:
    """`fornitore` → payload DocType **Supplier**.

    Mappa solo i campi che esistono nativamente sul Supplier; l'indirizzo in
    ERPNext è un DocType separato (Address) e resta fuori da qui.
    """
    payload: dict[str, Any] = {
        "supplier_name": dati["ragione_sociale"],
        "supplier_type": "Company",
        "supplier_group": supplier_group,
    }
    if dati.get("partita_iva"):
        payload["tax_id"] = dati["partita_iva"]
    return payload


def cantiere_a_cost_center(
    dati: dict[str, Any], *, company: str, parent_cost_center: str | None = None
) -> dict[str, Any]:
    """`cantiere` → payload DocType **Cost Center** (per imputare i costi al cantiere).

    ERPNext organizza i Cost Center ad albero e pretende un padre: ``parent_cost_center``
    è la radice della Company (la risolve la Facade, vedi :func:`radice_cost_center`).
    """
    payload: dict[str, Any] = {
        "cost_center_name": dati["nome"],
        "company": company,
        "is_group": 0,
    }
    if parent_cost_center:
        payload["parent_cost_center"] = parent_cost_center
    return payload


def cantiere_a_project(
    dati: dict[str, Any], *, company: str | None = None, cost_center: str | None = None
) -> dict[str, Any]:
    """`cantiere` → payload DocType **Project** (M30, A2).

    Il Cost Center imputa i costi, il Project li *racconta*: date attese, budget
    (``estimated_costing``) e — quando le righe dei documenti portano ``project`` —
    l'aggregato nativo del costo d'acquisto per cantiere. Il ``committente`` resta
    fuori finché il ciclo attivo è un non-goal (niente Customer).
    """
    payload: dict[str, Any] = {"project_name": dati["nome"]}
    if company:
        payload["company"] = company
    if cost_center:
        payload["cost_center"] = cost_center
    if dati.get("data_inizio"):
        payload["expected_start_date"] = dati["data_inizio"]
    if dati.get("data_fine_prevista"):
        payload["expected_end_date"] = dati["data_fine_prevista"]
    if dati.get("budget") is not None:
        payload["estimated_costing"] = dati["budget"]
    return payload


def fornitore_a_address(
    dati: dict[str, Any], *, supplier: str, paese: str = PAESE_DEFAULT
) -> dict[str, Any] | None:
    """`fornitore` → payload DocType **Address** collegato al Supplier (M30, A3).

    ERPNext pretende ``address_line1``, ``city`` e ``country``: senza indirizzo *e*
    comune estratti non c'è un Address legittimo da creare → ``None`` (meglio nessun
    indirizzo che un indirizzo inventato). Il legame col Supplier è la tabella
    ``links`` (Dynamic Link), come fa la UI di ERPNext.
    """
    if not (dati.get("indirizzo") and dati.get("comune")):
        return None
    return {
        "address_title": dati["ragione_sociale"],
        "address_type": "Billing",
        "address_line1": dati["indirizzo"],
        "city": dati["comune"],
        "country": paese,
        "links": [{"link_doctype": "Supplier", "link_name": supplier}],
    }


def fornitore_a_contact(dati: dict[str, Any], *, supplier: str) -> dict[str, Any] | None:
    """`fornitore` → payload DocType **Contact** collegato al Supplier (M30, A3).

    Porta PEC e telefono; senza almeno uno dei due non c'è nulla da registrare
    (``None``). Il nome del contatto è la ragione sociale: i documenti di cantiere
    non riportano una persona.
    """
    pec = dati.get("pec")
    telefono = dati.get("telefono")
    if not (pec or telefono):
        return None
    payload: dict[str, Any] = {
        "first_name": dati["ragione_sociale"][:140],
        "links": [{"link_doctype": "Supplier", "link_name": supplier}],
    }
    if pec:
        payload["email_ids"] = [{"email_id": pec, "is_primary": 1}]
    if telefono:
        payload["phone_nos"] = [{"phone": telefono, "is_primary_phone": 1}]
    return payload


def nome_asset(dati: dict[str, Any]) -> str:
    """Il nome del cespite a valle: descrizione + targa/matricola per l'unicità."""
    identificativo = dati.get("targa") or dati.get("matricola")
    if identificativo:
        return f"{dati['descrizione']} ({identificativo})"[:140]
    return dati["descrizione"][:140]


def mezzo_a_asset(
    dati: dict[str, Any],
    *,
    item_code: str,
    location: str,
    company: str | None = None,
) -> dict[str, Any] | None:
    """`mezzo` di proprietà → payload DocType **Asset** (M33, B3).

    Il registro cespiti è materia fiscale: spetta all'ERP. Solo i mezzi *propri*
    con valore e anno d'acquisto — il noleggio non è un cespite (il suo costo
    arriva già come fattura del noleggiatore) e senza valore/anno non c'è un
    cespite legittimo da iscrivere → ``None``, mai valori inventati.

    ``is_existing_asset=1``: il mezzo è già in azienda, non c'è un documento
    d'acquisto da riconciliare. Con ``vita_utile_anni`` si chiede l'ammortamento
    a quote costanti, una quota l'anno — le *scritture* le genera ERPNext.
    Il TCO gestionale (``v_mezzi_tco``) resta di Workflower.
    """
    if dati.get("proprieta") != "proprio":
        return None
    valore = dati.get("valore_acquisto")
    anno = dati.get("anno")
    if not valore or not anno:
        return None
    acquisto = f"{anno}-01-01"
    payload: dict[str, Any] = {
        "item_code": item_code,
        "asset_name": nome_asset(dati),
        "location": location,
        "is_existing_asset": 1,
        "gross_purchase_amount": valore,
        "purchase_date": acquisto,
        "available_for_use_date": acquisto,
    }
    if company:
        payload["company"] = company
    vita = dati.get("vita_utile_anni")
    if vita:
        payload["calculate_depreciation"] = 1
        payload["finance_books"] = [
            {
                "depreciation_method": "Straight Line",
                "frequency_of_depreciation": 12,  # in mesi: una quota l'anno
                "total_number_of_depreciations": int(vita),
            }
        ]
    return payload


def manutenzione_a_asset_repair(dati: dict[str, Any], *, asset: str) -> dict[str, Any]:
    """`manutenzione` → payload DocType **Asset Repair** (M33, B3).

    **Documentale** (``capitalize_repair_cost=0``): niente scritture contabili —
    il costo vero dell'intervento arriva già dalla fattura dell'officina, e
    capitalizzarlo qui lo conterebbe due volte. Resta lo storico interventi
    agganciato al cespite, con il costo a corredo.
    """
    descrizione = dati.get("descrizione") or ""
    testo = f"{dati['tipo']}: {descrizione}" if descrizione else dati["tipo"]
    payload: dict[str, Any] = {
        "asset": asset,
        "failure_date": dati["data"],
        "repair_status": "Completed",
        "completion_date": dati["data"],
        "capitalize_repair_cost": 0,
        "description": testo,
    }
    if dati.get("costo") is not None:
        payload["repair_cost"] = dati["costo"]
    return payload


def _riga_a_item(
    riga: dict[str, Any],
    cost_center: str | None,
    conto_costo: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    """Una riga fattura → una riga **Purchase Invoice Item**.

    La riga Workflower porta l'`importo` (totale riga = quantità × prezzo), non un
    prezzo unitario: si ricava `rate` = importo/qty così che qty×rate == importo.
    I campi interni di Workflower (`voce_computo_id`, `mezzo_id`, `tipo_costo`) sono
    per il cost-control di WF e **non** vengono spinti nell'ERP (confine dell'analisi).

    Le righe non portano ``item_code`` (i documenti di cantiere descrivono a testo,
    non a codice articolo): ERPNext non può quindi derivare il conto di costo
    dall'articolo e lo pretende esplicito — è ``conto_costo``, risolto dalla Facade
    dalla Company (vedi :func:`conto_costo_predefinito`).
    """
    importo = riga["importo"]
    quantita = riga.get("quantita")
    qty = quantita if quantita not in (None, 0) else 1
    item: dict[str, Any] = {
        "item_name": riga["descrizione"][:140],
        "description": riga["descrizione"],
        "qty": qty,
        "rate": importo / qty,
    }
    if cost_center:
        item["cost_center"] = cost_center
    if conto_costo:
        item["expense_account"] = conto_costo
    if project:
        item["project"] = project
    return item


def fattura_a_purchase_invoice(
    dati: dict[str, Any],
    *,
    supplier: str,
    cost_center: str | None = None,
    conto_ritenuta: str | None = None,
    conto_iva: str | None = None,
    conto_costo: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    """`fattura` → payload DocType **Purchase Invoice** (+ items + taxes).

    - ``supplier``/``cost_center``: nomi già risolti dalla Facade (M25).
    - ``conto_costo``: ``expense_account`` delle righe, obbligatorio in ERPNext
      quando la riga non porta ``item_code`` (è il nostro caso).
    - **Ritenuta d'acconto** (lo scenario M5, non negoziabile): se presente e c'è un
      conto ritenuta configurato, entra come riga di *Purchase Taxes and Charges* in
      **detrazione** con l'importo esatto estratto da Workflower; senza conto si
      ricade su ``apply_tds=1`` (ERPNext la calcola dalla categoria del Supplier).
    - **IVA**: se presente e c'è un conto IVA configurato, entra come riga in aggiunta
      con l'importo esatto; altrimenti si lascia che l'ERP la derivi dai template.
    - **Scadenza di pagamento** (M32): ``scadenza_pagamento`` diventa la ``due_date``
      — è ciò che rende vero lo scadenziario fornitori a valle. Difensivo: una
      scadenza *precedente* alla data fattura è un errore di lettura e si omette
      (ERPNext la rifiuterebbe: "Due Date cannot be before Posting Date").
    """
    payload: dict[str, Any] = {
        "supplier": supplier,
        "bill_no": dati["numero"],
        "bill_date": dati["data"],
        "items": [
            _riga_a_item(r, cost_center, conto_costo, project) for r in dati.get("righe", [])
        ],
    }
    if project:
        payload["project"] = project
    scadenza = dati.get("scadenza_pagamento")
    if scadenza and str(scadenza) >= str(dati["data"]):
        payload["due_date"] = scadenza

    taxes: list[dict[str, Any]] = []
    iva = dati.get("iva")
    if iva and conto_iva:
        taxes.append(
            {
                "charge_type": "Actual",
                "account_head": conto_iva,
                "description": "IVA",
                "add_deduct_tax": "Add",
                "category": "Total",
                "tax_amount": iva,
            }
        )

    ritenuta = dati.get("ritenuta_acconto")
    if ritenuta:
        if conto_ritenuta:
            taxes.append(
                {
                    "charge_type": "Actual",
                    "account_head": conto_ritenuta,
                    "description": "Ritenuta d'acconto",
                    "add_deduct_tax": "Deduct",
                    "category": "Total",
                    "tax_amount": ritenuta,
                }
            )
        else:
            payload["apply_tds"] = 1

    if taxes:
        payload["taxes"] = taxes
    return payload


def _riga_ddt_a_item(
    riga: dict[str, Any],
    cost_center: str | None,
    item_code: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    """Una riga DDT → una riga **Purchase Receipt Item**.

    Il DDT non porta importi (la merce si valorizza in fattura): si mappano
    descrizione e quantità; il costo cade sul cost center del cantiere.

    La Purchase Receipt è un documento di **magazzino**: a differenza della
    Purchase Invoice, ERPNext pretende un ``item_code`` esistente e rifiuta la riga
    "a testo libero". Workflower non ha un'anagrafica articoli (i DDT di cantiere
    descrivono a parole), quindi si usa un articolo generico configurato —
    ``ERP_ITEM_DDT`` — e la descrizione vera resta in ``description``.
    """
    quantita = riga.get("quantita")
    qty = quantita if quantita not in (None, 0) else 1
    item: dict[str, Any] = {
        "item_name": riga["descrizione"][:140],
        "description": riga["descrizione"],
        "qty": qty,
    }
    if item_code:
        item["item_code"] = item_code
    if cost_center:
        item["cost_center"] = cost_center
    if project:
        item["project"] = project
    return item


def ddt_a_purchase_receipt(
    dati: dict[str, Any],
    *,
    supplier: str,
    cost_center: str | None = None,
    item_code: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    """`ddt` → payload DocType **Purchase Receipt** (merce ricevuta, senza importi)."""
    payload: dict[str, Any] = {
        "supplier": supplier,
        "posting_date": dati["data"],
        "items": [
            _riga_ddt_a_item(r, cost_center, item_code, project) for r in dati.get("righe", [])
        ],
    }
    if dati.get("numero"):
        payload["supplier_delivery_note"] = dati["numero"]
    return payload


def fattura_coerente(dati: dict[str, Any], tolleranza: float = 0.01) -> bool:
    """Vero se ``totale ≈ imponibile + iva`` (stessa invariante della regola di manifest).

    Predicato puro, usato dai test e come guardia difensiva prima di sincronizzare.
    """
    try:
        imponibile = float(dati["imponibile"])
        iva = float(dati.get("iva") or 0)
        totale = float(dati["totale"])
    except (KeyError, TypeError, ValueError):
        return False
    return abs(totale - (imponibile + iva)) <= tolleranza


# ======================================================================
# Facade: sincronizzazione di un documento validato verso ERPNext
# ======================================================================
# Orchestrazione delle chiamate REST (upsert Supplier → Purchase Invoice),
# mono-direzionale e idempotente. NON scrive sull'envelope né sul ledger: ritorna
# l'esito e il chiamante (la revisione) persiste backref + ledger, best-effort.
# Qui la Facade ha il DAL solo per *leggere* le anagrafiche referenziate.


def radice_cost_center(erp: "ErpClient", company: str) -> str | None:
    """Il Cost Center **radice** della Company (padre dei cantieri), o ``None``.

    ERPNext crea per ogni Company un Cost Center di gruppo omonimo, radice
    dell'albero: è il padre naturale dei cantieri. Lo si cerca fra i gruppi della
    Company scegliendo quello **senza padre**. Il risultato è memorizzato sul client:
    è master data, non cambia durante un giro di sincronizzazione.
    """
    chiave = f"radice_cc:{company}"
    if chiave not in erp._master:
        gruppi = erp.trova_documenti(
            "Cost Center",
            [["company", "=", company], ["is_group", "=", 1]],
            limite=20,
            campi=["name", "parent_cost_center"],
        )
        radici = [g for g in gruppi if not g.get("parent_cost_center")]
        scelti = radici or gruppi
        erp._master[chiave] = scelti[0]["name"] if scelti else None
    return erp._master[chiave]


def conto_costo_predefinito(erp: "ErpClient", company: str) -> str | None:
    """Il conto di costo predefinito della Company (``default_expense_account``).

    Serve come ``expense_account`` delle righe, che ERPNext pretende quando la riga
    non porta ``item_code``. Memorizzato sul client come gli altri master data.
    """
    chiave = f"conto_costo:{company}"
    if chiave not in erp._master:
        from urllib.parse import quote

        try:
            corpo = erp.richiesta("GET", f"/api/resource/Company/{quote(company)}")
            dati = corpo.get("data", corpo) if isinstance(corpo, dict) else {}
            erp._master[chiave] = dati.get("default_expense_account") or None
        except ErpError:
            # Master data non leggibile: si prosegue senza: ERPNext dirà cosa manca
            # e l'errore finisce in issue + ledger come ogni altro problema di sync.
            erp._master[chiave] = None
    return erp._master[chiave]


def _risolvi_supplier_group(erp: "ErpClient", categoria: Any, config: ErpConfig) -> str:
    """Il gruppo Supplier per una ``categoria`` di fornitore: trovato, creato o default.

    La categoria merceologica di Workflower diventa un Supplier Group figlio della
    radice; qualunque intoppo (categoria assente, radice mancante, errore ERP)
    degrada al gruppo di default — il gruppo è tassonomia, non contabilità.
    """
    if not categoria:
        return config.supplier_group
    try:
        esistenti = erp.trova_documenti("Supplier Group", [["name", "=", categoria]])
        if esistenti:
            return esistenti[0]["name"]
        creato = erp.crea_documento(
            "Supplier Group",
            {
                "supplier_group_name": categoria,
                "parent_supplier_group": SUPPLIER_GROUP_DEFAULT,
                "is_group": 0,
            },
        )
        return creato["name"]
    except ErpError as exc:
        _log.warning("gruppo fornitore '%s' non creabile, uso il default: %s", categoria, exc)
        return config.supplier_group


def _arricchisci_supplier(
    erp: "ErpClient", forn: dict[str, Any], supplier: str, config: ErpConfig
) -> None:
    """Crea Address e Contact del Supplier, se i dati estratti li permettono (A3).

    Best-effort: l'anagrafica di corredo non deve mai far fallire la sincronizzazione
    del documento — un indirizzo che non passa è un warning nel logbook, non una issue.
    Idempotente per Dynamic Link: se il Supplier ha già un Address/Contact collegato,
    non se ne creano di nuovi.
    """
    filtro_link = [
        ["Dynamic Link", "link_doctype", "=", "Supplier"],
        ["Dynamic Link", "link_name", "=", supplier],
    ]
    try:
        indirizzo = fornitore_a_address(forn, supplier=supplier, paese=config.paese)
        if indirizzo and not erp.trova_documenti("Address", filtro_link):
            erp.crea_documento("Address", indirizzo)
        contatto = fornitore_a_contact(forn, supplier=supplier)
        if contatto and not erp.trova_documenti("Contact", filtro_link):
            erp.crea_documento("Contact", contatto)
    except ErpError as exc:
        _log.warning(
            "anagrafica di corredo del Supplier %s non completata: %s", supplier, exc
        )


def _upsert_supplier(
    erp: "ErpClient",
    forn: dict[str, Any],
    config: ErpConfig,
    *,
    completa_esistente: bool = False,
) -> str:
    """Il Supplier per un fornitore: trovato per partita IVA o creato col corredo.

    Con ``completa_esistente`` (carico anagrafiche, M31) anche il Supplier già a
    valle viene completato: gruppo dalla categoria (via PUT, se diverso) e
    Address/Contact mancanti. Alla validazione resta ``False``: il percorso del
    documento non si carica di chiamate per anagrafiche già a posto.
    """
    piva = forn.get("partita_iva")
    esistente: dict[str, Any] | None = None
    if piva:
        trovati = erp.trova_documenti(
            "Supplier", [["tax_id", "=", piva]], campi=["name", "supplier_group"]
        )
        esistente = trovati[0] if trovati else None
    if esistente is None:
        gruppo = _risolvi_supplier_group(erp, forn.get("categoria"), config)
        creato = erp.crea_documento(
            "Supplier", fornitore_a_supplier(forn, supplier_group=gruppo)
        )
        _arricchisci_supplier(erp, forn, creato["name"], config)
        return creato["name"]
    nome = esistente["name"]
    if completa_esistente:
        categoria = forn.get("categoria")
        if categoria and esistente.get("supplier_group") != categoria:
            gruppo = _risolvi_supplier_group(erp, categoria, config)
            if gruppo == categoria:  # il gruppo esiste davvero: aggancialo
                erp.aggiorna_documento("Supplier", nome, {"supplier_group": gruppo})
        _arricchisci_supplier(erp, forn, nome, config)
    return nome


def _risolvi_supplier(dal: Any, erp: "ErpClient", fornitore_id: Any, config: ErpConfig) -> str:
    """Nome ERPNext del Supplier per un ``FRN-...``: lo trova per partita IVA o lo crea."""
    if not fornitore_id:
        raise ErpError("fattura senza fornitore_id: impossibile creare la Purchase Invoice")
    forn = dal.read("fornitore", fornitore_id).dati
    return _upsert_supplier(erp, forn, config)


def _upsert_cost_center(
    erp: "ErpClient", cant: dict[str, Any], config: ErpConfig
) -> str | None:
    """Il Cost Center per un cantiere: trovato o creato; ``None`` senza ``company``."""
    if not config.company:
        return None
    padre = config.parent_cost_center or radice_cost_center(erp, config.company)
    payload = cantiere_a_cost_center(cant, company=config.company, parent_cost_center=padre)
    esistenti = erp.trova_documenti(
        "Cost Center",
        [["cost_center_name", "=", payload["cost_center_name"]], ["company", "=", config.company]],
    )
    if esistenti:
        return esistenti[0]["name"]
    creato = erp.crea_documento("Cost Center", payload)
    return creato["name"]


def _risolvi_cost_center(
    dal: Any, erp: "ErpClient", cantiere_id: Any, config: ErpConfig
) -> str | None:
    """Nome ERPNext del Cost Center per un ``CNT-...``: trovato o creato.

    Senza ``company`` configurata il Cost Center non è creabile: si degrada a
    ``None`` (le righe non portano cost center) invece di far fallire la sync.
    """
    if not cantiere_id or not config.company:
        return None
    cant = dal.read("cantiere", cantiere_id).dati
    return _upsert_cost_center(erp, cant, config)


def _upsert_project(
    erp: "ErpClient",
    cant: dict[str, Any],
    config: ErpConfig,
    cost_center: str | None = None,
) -> str:
    """Il Project per un cantiere: trovato o creato (solleva su errore ERP)."""
    payload = cantiere_a_project(cant, company=config.company, cost_center=cost_center)
    esistenti = erp.trova_documenti("Project", [["project_name", "=", payload["project_name"]]])
    if esistenti:
        return esistenti[0]["name"]
    creato = erp.crea_documento("Project", payload)
    return creato["name"]


def _risolvi_project(
    dal: Any,
    erp: "ErpClient",
    cantiere_id: Any,
    config: ErpConfig,
    cost_center: str | None = None,
) -> str | None:
    """Nome ERPNext del Project per un ``CNT-...``: trovato o creato (M30, A2).

    Best-effort come il resto del corredo: se il Project non passa, il documento si
    sincronizza lo stesso (senza ``project`` sulle righe) — l'imputazione contabile
    resta garantita dal Cost Center.
    """
    if not cantiere_id:
        return None
    try:
        cant = dal.read("cantiere", cantiere_id).dati
        return _upsert_project(erp, cant, config, cost_center)
    except ErpError as exc:
        _log.warning("Project del cantiere %s non risolto: %s", cantiere_id, exc)
        return None


def _allega_originale(
    dal: Any, erp: "ErpClient", envelope: Any, doctype: str, erp_id: str
) -> str | None:
    """Allega il blob di ``meta.origine`` al documento a valle (M30, A1).

    Il documento originale (PDF/scansione) è la pezza d'appoggio del record
    contabile: passa via ``frappe.client.attach_file`` in base64 (JSON puro, nessun
    multipart). Best-effort: un allegato fallito è un warning, la sincronizzazione
    resta valida — l'allegato è corredo, non contabilità. Ritorna il nome file
    allegato, o ``None`` se non c'era un blob o non è passato.
    """
    origine = getattr(envelope.meta, "origine", None)
    if not origine:
        return None
    percorso = dal.data_dir / origine
    if not percorso.is_file():
        return None
    import base64

    nome_file = percorso.name
    try:
        erp.chiama_metodo(
            "frappe.client.attach_file",
            {
                "filename": nome_file,
                "filedata": base64.b64encode(percorso.read_bytes()).decode("ascii"),
                "attached_to_doctype": doctype,
                "attached_to_name": erp_id,
                "decode_base64": 1,
                "is_private": 1,
            },
        )
        return nome_file
    except ErpError as exc:
        _log.warning(
            "allegato %s non caricato su %s %s: %s",
            nome_file,
            doctype,
            erp_id,
            exc,
            extra={"entity_id": envelope.id},
        )
        return None


def sincronizza(
    dal: Any, envelope: Any, erp: "ErpClient", *, config: ErpConfig | None = None
) -> dict[str, Any]:
    """Riflette un documento validato in ERPNext (upsert Supplier → Purchase Invoice).

    - **Mono-direzionale** (WF→ERP) e **idempotente**: se ``envelope.meta.erp_id`` è
      già valorizzato non fa nulla (evita doppioni su ri-sincronizzazioni/re-sync M28).
    - Solo i tipi in :data:`TIPI_SINCRONIZZABILI` (per ora ``fattura``); gli altri
      ritornano ``esito="saltato"``.
    - Solleva :class:`ErpError` sui problemi verso l'ERP: il chiamante (revisione)
      apre l'issue e registra il ledger, senza far cadere la validazione.
    """
    if envelope.tipo not in TIPI_SINCRONIZZABILI:
        return {"esito": "saltato", "motivo": f"tipo {envelope.tipo} non sincronizzato"}
    if envelope.meta.erp_id:
        return {"esito": "gia_sincronizzato", "erp_id": envelope.meta.erp_id}
    cfg = config if config is not None else erp.config
    if cfg is None:
        raise ErpError("ERP non configurato")

    dati = envelope.dati
    supplier = _risolvi_supplier(dal, erp, dati.get("fornitore_id"), cfg)
    cost_center = _risolvi_cost_center(dal, erp, dati.get("cantiere_id"), cfg)
    project = _risolvi_project(dal, erp, dati.get("cantiere_id"), cfg, cost_center)

    if envelope.tipo == "fattura":
        doctype = "Purchase Invoice"
        conto_costo = cfg.conto_costo
        if not conto_costo and cfg.company:
            conto_costo = conto_costo_predefinito(erp, cfg.company)
        payload = fattura_a_purchase_invoice(
            dati,
            supplier=supplier,
            cost_center=cost_center,
            conto_ritenuta=cfg.conto_ritenuta,
            conto_iva=cfg.conto_iva,
            conto_costo=conto_costo,
            project=project,
        )
    else:  # ddt (TIPI_SINCRONIZZABILI garantisce che sia uno di questi)
        doctype = "Purchase Receipt"
        if not cfg.item_ddt:
            # Meglio un errore che dica cosa configurare del "Item None does not
            # exist" che risponderebbe ERPNext: questo testo finisce nell'issue.
            raise ErpError(
                "DDT non sincronizzabile: ERPNext richiede un articolo sulle righe di "
                "Purchase Receipt. Configura ERP_ITEM_DDT con il codice di un articolo "
                "generico (consigliato: non di magazzino, is_stock_item=0)."
            )
        payload = ddt_a_purchase_receipt(
            dati,
            supplier=supplier,
            cost_center=cost_center,
            item_code=cfg.item_ddt,
            project=project,
        )

    creato = erp.crea_documento(doctype, payload)
    erp_id = creato.get("name")
    if not erp_id:
        raise ErpError(f"ERPNext non ha restituito il name del/della {doctype}")
    allegato = _allega_originale(dal, erp, envelope, doctype, erp_id)
    return {
        "esito": "ok",
        "erp_id": erp_id,
        "doctype": doctype,
        "supplier": supplier,
        "cost_center": cost_center,
        "project": project,
        "allegato": allegato,
    }


# ======================================================================
# Read-back: stato di pagamento ERPNext -> entità `pagamento` (sola lettura)
# ======================================================================
# Unico flusso ERP→WF: rilegge lo stato di pagamento delle fatture sincronizzate e
# lo riflette in WF come entità `pagamento` (puro dato). Nessuna scrittura di WF
# come "master" dentro l'ERP: qui si legge soltanto.


def _stato_pagamento(pi: dict[str, Any]) -> tuple[str, float]:
    """Deriva (stato, importo_pagato) dallo stato ERPNext di una Purchase Invoice."""
    grand = float(pi.get("grand_total") or 0)
    grezzo = pi.get("outstanding_amount")
    outstanding = float(grezzo) if grezzo is not None else grand
    pagato = round(grand - outstanding, 2)
    if grand > 0 and outstanding <= 0.005:
        return "pagato", pagato
    if pagato > 0:
        return "parziale", pagato
    return "non_pagato", pagato


def _data_ultimo_pagamento(erp: "ErpClient", erp_id: str) -> str | None:
    """La ``posting_date`` più recente dei Payment Entry confermati sulla PI (M31, A4).

    Frappe filtra sulle tabelle figlie col DocType figlio come primo elemento:
    ``["Payment Entry Reference", "reference_name", "=", <PI>]``. Se la lettura
    fallisce si torna ``None`` — la data è corredo dello stato, non lo blocca.
    """
    try:
        confermati = erp.trova_documenti(
            "Payment Entry",
            [
                ["Payment Entry Reference", "reference_name", "=", erp_id],
                ["docstatus", "=", 1],
            ],
            limite=50,
            campi=["name", "posting_date"],
        )
    except ErpError as exc:
        _log.warning("Payment Entry non leggibili per %s: %s", erp_id, exc)
        return None
    date = [str(pe["posting_date"]) for pe in confermati if pe.get("posting_date")]
    return max(date) if date else None


def rileggi_pagamenti(dal: Any, erp: "ErpClient") -> dict[str, Any]:
    """Rilegge da ERPNext lo stato di pagamento delle fatture sincronizzate.

    Per ogni ``fattura`` con ``meta.erp_id`` interroga la Purchase Invoice a valle e
    crea/aggiorna un'entità ``pagamento`` (idempotente per ``fattura_id``). No-op se
    l'ERP non è configurato. Errori di lettura non fanno cadere il ciclo: si contano.
    """
    if not erp.attivo():
        return {"esito": "erp_non_configurato", "creati": 0, "aggiornati": 0, "errori": 0}
    from urllib.parse import quote

    esistenti = {e.dati.get("fattura_id"): e for e in dal.list_all("pagamento")}
    creati = aggiornati = errori = 0
    for ft in dal.list_all("fattura"):
        erp_id = ft.meta.erp_id
        if not erp_id:
            continue
        try:
            corpo = erp.richiesta("GET", f"/api/resource/Purchase Invoice/{quote(erp_id)}")
        except ErpError as exc:
            _log.warning(
                "stato pagamento non leggibile per %s (ERP %s): %s",
                ft.id,
                erp_id,
                exc,
                extra={"entity_id": ft.id},
            )
            errori += 1
            continue
        pi = corpo.get("data", corpo) if isinstance(corpo, dict) else {}
        stato, pagato = _stato_pagamento(pi)
        # La data del pagamento vive sui Payment Entry, non sulla PI: la si chiede
        # solo quando c'è un pagamento di cui datare (mai per le non pagate).
        data = _data_ultimo_pagamento(erp, erp_id) if stato != "non_pagato" else None
        dati = {
            "fattura_id": ft.id,
            "stato": stato,
            "importo_pagato": pagato,
            "data": data,
            "erp_id": erp_id,
        }
        prec = esistenti.get(ft.id)
        if prec is not None:
            prec.dati.update(dati)
            dal.update(prec)
            aggiornati += 1
        else:
            esistenti[ft.id] = dal.crea_progressivo("pagamento", dati, stato="validato")
            creati += 1
    _log.info(
        "read-back pagamenti: creati %d, aggiornati %d, errori %d", creati, aggiornati, errori
    )
    return {"esito": "ok", "creati": creati, "aggiornati": aggiornati, "errori": errori}


# ======================================================================
# Carico anagrafiche (M31, A5): upsert in blocco delle anagrafiche a valle
# ======================================================================
# Le anagrafiche non passano dalla revisione (nessuna "validazione" che faccia da
# trigger): senza questo carico nascerebbero a valle solo se citate da un documento.
# Il registro è il punto di estensione delle milestone successive (mezzi, materiali,
# dipendenti…): una riga per tipo, la cornice non cambia.


def _carica_fornitore(dal: Any, erp: "ErpClient", envelope: Any, config: ErpConfig) -> str:
    """Upsert completo del fornitore: Supplier + gruppo + Address/Contact mancanti."""
    return _upsert_supplier(erp, envelope.dati, config, completa_esistente=True)


def _carica_cantiere(dal: Any, erp: "ErpClient", envelope: Any, config: ErpConfig) -> str:
    """Upsert del cantiere: Cost Center (con ``company``) + Project ancorato.

    Il backref è il Cost Center — l'àncora contabile — quando esiste; senza
    ``company`` resta il Project (che non la pretende).
    """
    cost_center = _upsert_cost_center(erp, envelope.dati, config)
    progetto = _upsert_project(erp, envelope.dati, config, cost_center)
    return cost_center or progetto


def _upsert_asset(erp: "ErpClient", mezzo: dict[str, Any], config: ErpConfig) -> str | None:
    """L'Asset per un mezzo: trovato per nome o creato; ``None`` se non cespitabile."""
    payload = mezzo_a_asset(
        mezzo,
        item_code=config.asset_item or "",
        location=config.asset_location or "",
        company=config.company,
    )
    if payload is None:
        return None
    esistenti = erp.trova_documenti("Asset", [["asset_name", "=", payload["asset_name"]]])
    if esistenti:
        return esistenti[0]["name"]
    creato = erp.crea_documento("Asset", payload)
    return creato["name"]


def _cespiti_configurati(config: ErpConfig, envelope: Any) -> bool:
    """Vero se le env dei cespiti ci sono; altrimenti warning azionabile e salto.

    Stesso spirito di ``ERP_ITEM_DDT``: meglio un messaggio che dice cosa
    configurare del "Item None does not exist" di ERPNext — ma qui nel logbook,
    non come errore: chi non vuole i cespiti a valle non deve trovare il carico
    anagrafiche pieno di rossi.
    """
    if config.asset_item and config.asset_location:
        return True
    _log.warning(
        "%s saltato: i cespiti richiedono un articolo e una Location in ERPNext. "
        "Configura ERP_ASSET_ITEM e ERP_ASSET_LOCATION (make erp-dev-setup li "
        "prepara e li stampa).",
        envelope.id,
        extra={"entity_id": envelope.id},
    )
    return False


def _carica_mezzo(dal: Any, erp: "ErpClient", envelope: Any, config: ErpConfig) -> str | None:
    """Upsert del mezzo di proprietà come Asset; i noleggi restano fuori (saltati)."""
    if not _cespiti_configurati(config, envelope):
        return None
    return _upsert_asset(erp, envelope.dati, config)


def _carica_manutenzione(
    dal: Any, erp: "ErpClient", envelope: Any, config: ErpConfig
) -> str | None:
    """La manutenzione come Asset Repair del cespite (documentale, mai contabile).

    L'Asset Repair non ha una chiave naturale: l'idempotenza è il backref
    ``meta.erp_id`` (una manutenzione già a valle non si reinvia). Manutenzioni
    di mezzi a noleggio: saltate — quel costo vive nella fattura dell'officina.
    """
    if envelope.meta.erp_id:
        return envelope.meta.erp_id
    if not _cespiti_configurati(config, envelope):
        return None
    mezzo = dal.read("mezzo", envelope.dati["mezzo_id"]).dati
    asset = _upsert_asset(erp, mezzo, config)
    if asset is None:
        return None
    creato = erp.crea_documento(
        "Asset Repair", manutenzione_a_asset_repair(envelope.dati, asset=asset)
    )
    return creato["name"]


# (tipo entità, upsert): l'ordine conta — i fornitori prima di chi li referenzia,
# i mezzi prima delle manutenzioni che vi si agganciano.
ANAGRAFICHE_CARICABILI: tuple[tuple[str, Any], ...] = (
    ("fornitore", _carica_fornitore),
    ("cantiere", _carica_cantiere),
    ("mezzo", _carica_mezzo),
    ("manutenzione", _carica_manutenzione),
)


def carica_anagrafiche(dal: Any, erp: "ErpClient") -> dict[str, Any]:
    """Porta a valle tutte le anagrafiche del registro (idempotente, best-effort).

    Per ogni anagrafica non scartata: upsert per chiave naturale, backref
    ``meta.erp_id`` quando cambia (con riga di ledger), errore contato e tracciato
    senza fermare il giro. Un secondo carico con tutto allineato non scrive nulla.
    """
    if not erp.attivo():
        return {"esito": "erp_non_configurato", "per_tipo": {}}
    cfg = erp.config
    per_tipo: dict[str, dict[str, int]] = {}
    for tipo, upsert in ANAGRAFICHE_CARICABILI:
        conta = {"inviate": 0, "gia_allineate": 0, "saltate": 0, "errori": 0}
        for envelope in dal.list_all(tipo):
            if envelope.stato == "scartato":
                continue
            try:
                erp_id = upsert(dal, erp, envelope, cfg)
            except ErpError as exc:
                conta["errori"] += 1
                _log.warning(
                    "carico anagrafiche: %s non passato: %s",
                    envelope.id,
                    exc,
                    extra={"entity_id": envelope.id},
                )
                registra_sync_erp(dal, entity_id=envelope.id, esito="errore", errore=str(exc))
                continue
            if not erp_id:
                conta["saltate"] += 1  # es. cantiere senza company configurata
                continue
            if envelope.meta.erp_id == erp_id:
                conta["gia_allineate"] += 1
                continue
            envelope.meta.erp_id = erp_id
            envelope.meta.erp_synced = now_iso()
            dal.update(envelope)
            registra_sync_erp(dal, entity_id=envelope.id, esito="ok", erp_id=erp_id)
            conta["inviate"] += 1
        per_tipo[tipo] = conta
    _log.info(
        "carico anagrafiche: %s",
        ", ".join(f"{t}: {c['inviate']} inviate, {c['errori']} errori" for t, c in per_tipo.items()),
    )
    return {"esito": "ok", "per_tipo": per_tipo}


# ======================================================================
# Orchestrazione best-effort + osservabilità / re-sync (M28)
# ======================================================================


def applica_sincronizzazione(dal: Any, envelope: Any, erp: "ErpClient") -> dict[str, Any] | None:
    """Sincronizza un documento e **persiste l'esito**: backref, ledger, issue.

    È l'orchestrazione best-effort usata sia dalla revisione (alla validazione) sia
    dal re-sync manuale (M28). Un fallimento non propaga: apre una issue e registra
    la riga d'errore nel ledger. No-op (``None``) se l'ERP è spento o il tipo non è
    sincronizzabile.
    """
    if not erp.attivo() or envelope.tipo not in TIPI_SINCRONIZZABILI:
        return None
    try:
        esito = sincronizza(dal, envelope, erp)
    except ErpError as exc:
        # Il logbook è la superficie diagnostica dell'ufficio (pagina "Log") e
        # l'ingresso della diagnosi automatica: un fallimento verso l'ERP deve
        # comparire lì, non solo come issue e riga di ledger.
        _log.error(
            "sincronizzazione ERP fallita per %s: %s",
            envelope.id,
            exc,
            exc_info=exc,
            extra={"run_id": envelope.meta.run_id, "entity_id": envelope.id},
        )
        dal.crea_issue(
            "auto",
            f"Sincronizzazione ERP fallita per {envelope.id}: {exc}",
            run_id=envelope.meta.run_id,
            entity_id=envelope.id,
        )
        registra_sync_erp(
            dal, entity_id=envelope.id, esito="errore", errore=str(exc), run_id=envelope.meta.run_id
        )
        return {"esito": "errore", "errore": str(exc)}
    if esito.get("esito") == "ok":
        _log.info(
            "documento %s sincronizzato su ERP come %s %s",
            envelope.id,
            esito.get("doctype"),
            esito["erp_id"],
            extra={"run_id": envelope.meta.run_id, "entity_id": envelope.id},
        )
        envelope.meta.erp_id = esito["erp_id"]
        envelope.meta.erp_synced = now_iso()
        dal.update(envelope, run_id=envelope.meta.run_id)
        registra_sync_erp(
            dal,
            entity_id=envelope.id,
            esito="ok",
            erp_id=esito["erp_id"],
            run_id=envelope.meta.run_id,
        )
    return esito


def stato_sincronizzazione(dal: Any, erp: "ErpClient") -> dict[str, Any]:
    """Riepilogo dello stato di sincronizzazione ERP (per il pannello admin).

    Per ogni tipo sincronizzabile conta i documenti validati e quanti sono già a
    valle (``meta.erp_id``); elenca quelli **da sincronizzare** e gli ultimi
    tentativi dal ledger.
    """
    per_tipo: dict[str, dict[str, int]] = {}
    da_sincronizzare: list[dict[str, str]] = []
    for tipo in TIPI_SINCRONIZZABILI:
        validate = sincronizzate = 0
        for e in dal.list_all(tipo):
            if e.stato != "validato":
                continue
            validate += 1
            if e.meta.erp_id:
                sincronizzate += 1
            else:
                da_sincronizzare.append({"id": e.id, "tipo": tipo})
        per_tipo[tipo] = {
            "validate": validate,
            "sincronizzate": sincronizzate,
            "da_sincronizzare": validate - sincronizzate,
        }
    return {
        "erp_attivo": erp.attivo(),
        "per_tipo": per_tipo,
        "da_sincronizzare": da_sincronizzare,
        "ultimi_tentativi": leggi_sync_erp(dal.data_dir)[-20:],
    }


def risincronizza_mancanti(
    dal: Any, erp: "ErpClient", *, max_errori: int = MAX_ERRORI_CONSECUTIVI
) -> dict[str, Any]:
    """Ri-sincronizza le entità validate rimaste senza backref ERP (recupero, M28).

    Best-effort per documento; si **ferma** dopo ``max_errori`` fallimenti
    consecutivi (ERP verosimilmente giù) per non martellare. Idempotente: le entità
    già sincronizzate vengono saltate.
    """
    if not erp.attivo():
        return {
            "esito": "erp_non_configurato",
            "tentate": 0,
            "ok": 0,
            "errori": 0,
            "interrotto": False,
        }
    tentate = ok = errori = 0
    consecutivi = 0
    interrotto = False
    for tipo in TIPI_SINCRONIZZABILI:
        for e in dal.list_all(tipo):
            if e.stato != "validato" or e.meta.erp_id:
                continue
            tentate += 1
            esito = applica_sincronizzazione(dal, e, erp)
            if esito and esito.get("esito") == "ok":
                ok += 1
                consecutivi = 0
            else:
                errori += 1
                consecutivi += 1
                if consecutivi >= max_errori:
                    interrotto = True
                    _log.warning(
                        "re-sync interrotto dopo %d fallimenti consecutivi: ERP "
                        "verosimilmente giù (tentate %d, ok %d)",
                        consecutivi,
                        tentate,
                        ok,
                    )
                    break
        if interrotto:
            break
    if tentate:
        _log.info("re-sync ERP: tentate %d, ok %d, errori %d", tentate, ok, errori)
    return {"esito": "ok", "tentate": tentate, "ok": ok, "errori": errori, "interrotto": interrotto}
