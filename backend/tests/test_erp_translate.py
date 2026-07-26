"""Translator envelope→DocType (Integrazione ERP, M24). Copre gli AC della milestone:

mapping puro e testabile `fornitore→Supplier`, `cantiere→Cost Center`,
`fattura→Purchase Invoice + items + taxes`, con il caso **ritenuta d'acconto**
(→ riga in detrazione) e l'invariante `totale ≈ imponibile + iva`. Nessun I/O.
"""

from pathlib import Path

from app.core.dal import DAL
from app.core.erp import (
    cantiere_a_cost_center,
    ddt_a_purchase_receipt,
    fattura_a_purchase_invoice,
    fattura_coerente,
    fornitore_a_supplier,
)

# ------------------------------------------------------------------ fixture dati

FORNITORE = {
    "ragione_sociale": "Studio Bianchi",
    "partita_iva": "01234567890",
    "categoria": "Servizi",
}

CANTIERE = {"nome": "Cantiere Via Roma", "indirizzo": "Via Roma 1", "comune": "Milano"}

# Fattura materiali senza ritenuta: imponibile 1000 + iva 220 = totale 1220.
FATT_SENZA_RITENUTA = {
    "numero": "45/2026",
    "data": "2026-02-01",
    "imponibile": 1000.0,
    "iva": 220.0,
    "totale": 1220.0,
    "ritenuta_acconto": None,
    "righe": [
        {"descrizione": "Cemento", "quantita": 10, "unita_misura": "sacchi", "importo": 1000.0},
    ],
}

# Parcella professionale con ritenuta: imponibile 4000 + iva 880 = totale 4880;
# ritenuta d'acconto 800 (a parte, riduce il netto a pagare).
FATT_CON_RITENUTA = {
    "numero": "12/2026",
    "data": "2026-03-10",
    "imponibile": 4000.0,
    "iva": 880.0,
    "totale": 4880.0,
    "ritenuta_acconto": 800.0,
    "righe": [
        {"descrizione": "Prestazione professionale", "quantita": None, "importo": 4000.0},
    ],
}


# ------------------------------------------------------------------ anagrafiche


def test_fornitore_a_supplier() -> None:
    payload = fornitore_a_supplier(FORNITORE)
    assert payload["supplier_name"] == "Studio Bianchi"
    assert payload["tax_id"] == "01234567890"
    assert payload["supplier_type"] == "Company"
    assert payload["supplier_group"] == "All Supplier Groups"


def test_fornitore_a_supplier_gruppo_personalizzato() -> None:
    payload = fornitore_a_supplier(FORNITORE, supplier_group="Servizi")
    assert payload["supplier_group"] == "Servizi"


def test_cantiere_a_cost_center() -> None:
    payload = cantiere_a_cost_center(CANTIERE, company="Edile SpA")
    assert payload == {
        "cost_center_name": "Cantiere Via Roma",
        "company": "Edile SpA",
        "is_group": 0,
    }


# ------------------------------------------------------------------ righe / items


def test_riga_con_quantita_ricava_rate() -> None:
    payload = fattura_a_purchase_invoice(FATT_SENZA_RITENUTA, supplier="Studio Bianchi")
    item = payload["items"][0]
    assert item["qty"] == 10
    assert item["rate"] == 100.0  # 1000 / 10
    assert item["qty"] * item["rate"] == 1000.0


def test_riga_senza_quantita_usa_uno() -> None:
    payload = fattura_a_purchase_invoice(FATT_CON_RITENUTA, supplier="Studio Bianchi")
    item = payload["items"][0]
    assert item["qty"] == 1
    assert item["rate"] == 4000.0


def test_items_sommano_all_imponibile() -> None:
    payload = fattura_a_purchase_invoice(FATT_SENZA_RITENUTA, supplier="Studio Bianchi")
    somma = sum(i["qty"] * i["rate"] for i in payload["items"])
    assert abs(somma - FATT_SENZA_RITENUTA["imponibile"]) < 0.01


def test_cost_center_sulle_righe() -> None:
    payload = fattura_a_purchase_invoice(
        FATT_SENZA_RITENUTA, supplier="Studio Bianchi", cost_center="Cantiere Via Roma - E"
    )
    assert all(i["cost_center"] == "Cantiere Via Roma - E" for i in payload["items"])


# ------------------------------------------------------------------ testata / taxes


def test_purchase_invoice_testata() -> None:
    payload = fattura_a_purchase_invoice(FATT_SENZA_RITENUTA, supplier="Studio Bianchi")
    assert payload["supplier"] == "Studio Bianchi"
    assert payload["bill_no"] == "45/2026"
    assert payload["bill_date"] == "2026-02-01"


def test_iva_come_riga_in_aggiunta_se_conto() -> None:
    payload = fattura_a_purchase_invoice(
        FATT_SENZA_RITENUTA, supplier="Studio Bianchi", conto_iva="IVA ns credito - E"
    )
    iva = [t for t in payload["taxes"] if t["description"] == "IVA"]
    assert len(iva) == 1
    assert iva[0]["add_deduct_tax"] == "Add"
    assert iva[0]["tax_amount"] == 220.0


def test_senza_ritenuta_nessuna_riga_ne_tds() -> None:
    payload = fattura_a_purchase_invoice(FATT_SENZA_RITENUTA, supplier="Studio Bianchi")
    assert "apply_tds" not in payload
    assert not any(
        t.get("description") == "Ritenuta d'acconto" for t in payload.get("taxes", [])
    )


def test_ritenuta_come_riga_in_detrazione_con_conto() -> None:
    payload = fattura_a_purchase_invoice(
        FATT_CON_RITENUTA, supplier="Studio Bianchi", conto_ritenuta="Ritenute - E"
    )
    ritenute = [t for t in payload["taxes"] if t["description"] == "Ritenuta d'acconto"]
    assert len(ritenute) == 1
    assert ritenute[0]["add_deduct_tax"] == "Deduct"
    assert ritenute[0]["tax_amount"] == 800.0
    assert ritenute[0]["account_head"] == "Ritenute - E"
    assert "apply_tds" not in payload  # importo esatto, non delega alla categoria


def test_ritenuta_ricade_su_tds_senza_conto() -> None:
    payload = fattura_a_purchase_invoice(FATT_CON_RITENUTA, supplier="Studio Bianchi")
    assert payload["apply_tds"] == 1


# ------------------------------------------------------------------ ddt → receipt

DDT = {
    "numero": "DDT-99",
    "data": "2026-04-01",
    "causale": "Vendita",
    "riferimento_ordine": "ORD-7",
    "righe": [
        {"descrizione": "Tondino acciaio", "quantita": 500, "unita_misura": "kg"},
        {"descrizione": "Rete elettrosaldata", "quantita": None, "unita_misura": None},
    ],
}


def test_ddt_a_purchase_receipt_testata() -> None:
    payload = ddt_a_purchase_receipt(DDT, supplier="Ferramenta Rossi")
    assert payload["supplier"] == "Ferramenta Rossi"
    assert payload["posting_date"] == "2026-04-01"
    assert payload["supplier_delivery_note"] == "DDT-99"


def test_ddt_a_purchase_receipt_righe() -> None:
    payload = ddt_a_purchase_receipt(DDT, supplier="Ferramenta Rossi", cost_center="Cantiere - E")
    assert len(payload["items"]) == 2
    assert payload["items"][0]["qty"] == 500
    assert payload["items"][1]["qty"] == 1  # quantità assente → 1
    assert all(i["cost_center"] == "Cantiere - E" for i in payload["items"])
    # il DDT non porta importi: nessun rate/amount nelle righe
    assert "rate" not in payload["items"][0]


# ------------------------------------------------------------------ coerenza


def test_fattura_coerente() -> None:
    assert fattura_coerente(FATT_SENZA_RITENUTA) is True
    assert fattura_coerente(FATT_CON_RITENUTA) is True


def test_fattura_incoerente() -> None:
    rotta = dict(FATT_SENZA_RITENUTA, totale=9999.0)
    assert fattura_coerente(rotta) is False


# ------------------------------------------------------------------ dati reali del seed

# Lega il mapping alla regressione ritenuta d'acconto (M5): la fattura del seed con
# ritenuta in calce deve tradursi in una riga in detrazione con l'importo estratto.
def test_seed_fattura_ritenuta_si_traduce(dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    ritenute = [
        e for e in dal.list_all("fattura") if e.dati.get("ritenuta_acconto")
    ]
    assert ritenute, "atteso almeno una fattura con ritenuta nel seed"
    entita = ritenute[0]
    assert fattura_coerente(entita.dati)
    payload = fattura_a_purchase_invoice(
        entita.dati, supplier="Fornitore X", conto_ritenuta="Ritenute - E"
    )
    riga = next(t for t in payload["taxes"] if t["description"] == "Ritenuta d'acconto")
    assert riga["tax_amount"] == entita.dati["ritenuta_acconto"]
    assert riga["tax_amount"] > 0
