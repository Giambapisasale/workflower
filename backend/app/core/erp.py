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

from app.core.logbook import ottieni_logger

_log = ottieni_logger("erp")

# Trasporto: (metodo, url, *, headers, json, timeout) -> risposta con .status_code e .json().
# Firma volutamente httpx-compatibile, così il default è un thin wrapper e il finto
# dei test è banale (vedi tests/fake_erp.py).
Transport = Callable[..., Any]

# Timeout corto: l'ERP è a valle e best-effort; non deve mai rallentare la validazione.
TIMEOUT_DEFAULT = 10.0


class ErpError(Exception):
    """Errore verso ERPNext: trasporto irraggiungibile, HTTP >= 400 o corpo non JSON."""


@dataclass(frozen=True)
class ErpConfig:
    """Coordinate dell'istanza ERPNext, lette dall'ambiente (mai hard-coded)."""

    base_url: str
    api_key: str
    api_secret: str

    @classmethod
    def da_env(cls) -> "ErpConfig | None":
        """La config se ``ERP_BASE_URL``/``ERP_API_KEY``/``ERP_API_SECRET`` sono tutte
        presenti, altrimenti ``None`` (ERP non configurato → sync no-op)."""
        base = os.environ.get("ERP_BASE_URL")
        key = os.environ.get("ERP_API_KEY")
        secret = os.environ.get("ERP_API_SECRET")
        if not (base and key and secret):
            return None
        return cls(base_url=base, api_key=key, api_secret=secret)


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
        try:
            risposta = self._transport(
                metodo, url, headers=headers, json=json, timeout=self.timeout
            )
        except ErpError:
            raise
        except Exception as exc:  # trasporto irraggiungibile / timeout
            raise ErpError(f"ERP non raggiungibile ({metodo} {percorso}): {exc}") from exc

        stato = getattr(risposta, "status_code", None)
        if stato is None or stato >= 400:
            raise ErpError(
                f"ERP ha risposto {stato} a {metodo} {percorso}: {_corpo_sicuro(risposta)}"
            )
        try:
            return risposta.json()
        except Exception as exc:
            raise ErpError(f"risposta ERP non JSON a {metodo} {percorso}: {exc}") from exc


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

# Gruppo Supplier di default (radice ERPNext); la Facade può passarne uno più specifico.
SUPPLIER_GROUP_DEFAULT = "All Supplier Groups"


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


def cantiere_a_cost_center(dati: dict[str, Any], *, company: str) -> dict[str, Any]:
    """`cantiere` → payload DocType **Cost Center** (per imputare i costi al cantiere)."""
    return {
        "cost_center_name": dati["nome"],
        "company": company,
        "is_group": 0,
    }


def _riga_a_item(riga: dict[str, Any], cost_center: str | None) -> dict[str, Any]:
    """Una riga fattura → una riga **Purchase Invoice Item**.

    La riga Workflower porta l'`importo` (totale riga = quantità × prezzo), non un
    prezzo unitario: si ricava `rate` = importo/qty così che qty×rate == importo.
    I campi interni di Workflower (`voce_computo_id`, `mezzo_id`, `tipo_costo`) sono
    per il cost-control di WF e **non** vengono spinti nell'ERP (confine dell'analisi).
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
    return item


def fattura_a_purchase_invoice(
    dati: dict[str, Any],
    *,
    supplier: str,
    cost_center: str | None = None,
    conto_ritenuta: str | None = None,
    conto_iva: str | None = None,
) -> dict[str, Any]:
    """`fattura` → payload DocType **Purchase Invoice** (+ items + taxes).

    - ``supplier``/``cost_center``: nomi già risolti dalla Facade (M25).
    - **Ritenuta d'acconto** (lo scenario M5, non negoziabile): se presente e c'è un
      conto ritenuta configurato, entra come riga di *Purchase Taxes and Charges* in
      **detrazione** con l'importo esatto estratto da Workflower; senza conto si
      ricade su ``apply_tds=1`` (ERPNext la calcola dalla categoria del Supplier).
    - **IVA**: se presente e c'è un conto IVA configurato, entra come riga in aggiunta
      con l'importo esatto; altrimenti si lascia che l'ERP la derivi dai template.
    """
    payload: dict[str, Any] = {
        "supplier": supplier,
        "bill_no": dati["numero"],
        "bill_date": dati["data"],
        "items": [_riga_a_item(r, cost_center) for r in dati.get("righe", [])],
    }

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
