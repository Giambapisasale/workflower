"""Translator envelope→DocType (Integrazione ERP, M24). Copre gli AC della milestone:

mapping puro e testabile `fornitore→Supplier`, `cantiere→Cost Center`,
`fattura→Purchase Invoice + items + taxes`, con il caso **ritenuta d'acconto**
(→ riga in detrazione) e l'invariante `totale ≈ imponibile + iva`. Nessun I/O.
"""

from pathlib import Path

import pytest

from app.core.dal import DAL
from app.core.erp import (
    cantiere_a_cost_center,
    cantiere_a_project,
    ddt_a_purchase_receipt,
    fattura_a_purchase_invoice,
    fattura_coerente,
    fornitore_a_address,
    fornitore_a_contact,
    fornitore_a_supplier,
    manutenzione_a_asset_repair,
    materiale_a_item,
    mezzo_a_asset,
    nome_asset,
)

pytestmark = pytest.mark.erp

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


def test_fornitore_senza_partita_iva() -> None:
    payload = fornitore_a_supplier({"ragione_sociale": "Ditta Senza IVA"})
    assert payload["supplier_name"] == "Ditta Senza IVA"
    assert "tax_id" not in payload  # nessuna partita IVA → campo assente


def test_cantiere_a_cost_center() -> None:
    payload = cantiere_a_cost_center(CANTIERE, company="Edile SpA")
    assert payload == {
        "cost_center_name": "Cantiere Via Roma",
        "company": "Edile SpA",
        "is_group": 0,
    }


def test_cantiere_a_cost_center_con_padre() -> None:
    # ERPNext tiene i Cost Center ad albero e RIFIUTA un figlio senza padre
    # ("Please enter parent cost center"): il padre deve arrivare nel payload.
    payload = cantiere_a_cost_center(
        CANTIERE, company="Edile SpA", parent_cost_center="Edile SpA - E"
    )
    assert payload["parent_cost_center"] == "Edile SpA - E"


# ------------------------------------------------------------ project / address / contact (M30)

CANTIERE_COMPLETO = {
    "nome": "Residenza Le Palme",
    "indirizzo": "Via delle Palme 12",
    "comune": "Catania",
    "committente": "Immobiliare Mediterranea S.r.l.",
    "budget": 1850000.0,
    "data_inizio": "2026-01-12",
    "data_fine_prevista": "2027-06-30",
}


def test_cantiere_a_project() -> None:
    payload = cantiere_a_project(
        CANTIERE_COMPLETO, company="Edile SpA", cost_center="Residenza Le Palme - E"
    )
    assert payload["project_name"] == "Residenza Le Palme"
    assert payload["company"] == "Edile SpA"
    assert payload["cost_center"] == "Residenza Le Palme - E"
    assert payload["expected_start_date"] == "2026-01-12"
    assert payload["expected_end_date"] == "2027-06-30"
    assert payload["estimated_costing"] == 1850000.0
    # il committente NON passa: il ciclo attivo (Customer) è un non-goal
    assert "customer" not in payload


def test_cantiere_a_project_minimo() -> None:
    payload = cantiere_a_project({"nome": "Cantiere X", "data_inizio": "2026-01-01"})
    assert payload["project_name"] == "Cantiere X"
    assert payload["expected_start_date"] == "2026-01-01"
    assert "expected_end_date" not in payload
    assert "estimated_costing" not in payload
    assert "company" not in payload


def test_fornitore_a_address() -> None:
    forn = dict(FORNITORE, indirizzo="Via Etnea 100", comune="Catania")
    payload = fornitore_a_address(forn, supplier="Studio Bianchi")
    assert payload == {
        "address_title": "Studio Bianchi",
        "address_type": "Billing",
        "address_line1": "Via Etnea 100",
        "city": "Catania",
        "country": "Italy",  # l'Address di ERPNext pretende il paese
        "links": [{"link_doctype": "Supplier", "link_name": "Studio Bianchi"}],
    }


def test_fornitore_a_address_paese_configurabile() -> None:
    forn = dict(FORNITORE, indirizzo="Hauptstrasse 1", comune="Bolzano")
    payload = fornitore_a_address(forn, supplier="Studio Bianchi", paese="Austria")
    assert payload["country"] == "Austria"


def test_fornitore_senza_indirizzo_niente_address() -> None:
    # Meglio nessun indirizzo che un indirizzo inventato: senza via E comune → None.
    assert fornitore_a_address(dict(FORNITORE, indirizzo="Via X"), supplier="S") is None
    assert fornitore_a_address(dict(FORNITORE, comune="Catania"), supplier="S") is None


def test_fornitore_a_contact() -> None:
    forn = dict(FORNITORE, pec="bianchi@pec.it", telefono="095 123456")
    payload = fornitore_a_contact(forn, supplier="Studio Bianchi")
    assert payload["first_name"] == "Studio Bianchi"
    assert payload["email_ids"] == [{"email_id": "bianchi@pec.it", "is_primary": 1}]
    assert payload["phone_nos"] == [{"phone": "095 123456", "is_primary_phone": 1}]
    assert payload["links"] == [{"link_doctype": "Supplier", "link_name": "Studio Bianchi"}]


def test_fornitore_solo_telefono_contact_senza_email() -> None:
    payload = fornitore_a_contact(dict(FORNITORE, telefono="095 1"), supplier="S")
    assert payload is not None
    assert "email_ids" not in payload


def test_fornitore_senza_recapiti_niente_contact() -> None:
    assert fornitore_a_contact(FORNITORE, supplier="S") is None


def test_project_su_testata_e_righe_della_fattura() -> None:
    payload = fattura_a_purchase_invoice(
        FATT_SENZA_RITENUTA, supplier="Studio Bianchi", project="Residenza Le Palme"
    )
    assert payload["project"] == "Residenza Le Palme"
    assert all(i["project"] == "Residenza Le Palme" for i in payload["items"])


def test_senza_project_ne_testata_ne_righe() -> None:
    payload = fattura_a_purchase_invoice(FATT_SENZA_RITENUTA, supplier="Studio Bianchi")
    assert "project" not in payload
    assert all("project" not in i for i in payload["items"])


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


def test_senza_cost_center_le_righe_non_lo_riportano() -> None:
    payload = fattura_a_purchase_invoice(FATT_SENZA_RITENUTA, supplier="Studio Bianchi")
    assert all("cost_center" not in i for i in payload["items"])


def test_conto_costo_sulle_righe() -> None:
    # Le righe non portano `item_code`: senza `expense_account` ERPNext rifiuta la
    # Purchase Invoice ("Expense account is mandatory for item ...").
    payload = fattura_a_purchase_invoice(
        FATT_SENZA_RITENUTA, supplier="Studio Bianchi", conto_costo="Costi - E"
    )
    assert all(i["expense_account"] == "Costi - E" for i in payload["items"])


def test_senza_conto_costo_le_righe_non_lo_riportano() -> None:
    payload = fattura_a_purchase_invoice(FATT_SENZA_RITENUTA, supplier="Studio Bianchi")
    assert all("expense_account" not in i for i in payload["items"])


def test_senza_conti_configurati_nessuna_riga_tax() -> None:
    # senza conto_iva né ritenuta: nessuna sezione taxes (l'ERP deriva dai template)
    payload = fattura_a_purchase_invoice(FATT_SENZA_RITENUTA, supplier="Studio Bianchi")
    assert "taxes" not in payload


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


def test_scadenza_pagamento_diventa_due_date() -> None:
    # È il buco dello scadenziario (M32): senza due_date ERPNext mette
    # scadenza = data fattura e l'Accounts Payable racconta il falso.
    fatt = dict(FATT_SENZA_RITENUTA, scadenza_pagamento="2026-03-03")
    payload = fattura_a_purchase_invoice(fatt, supplier="Studio Bianchi")
    assert payload["due_date"] == "2026-03-03"


def test_senza_scadenza_niente_due_date() -> None:
    payload = fattura_a_purchase_invoice(FATT_SENZA_RITENUTA, supplier="Studio Bianchi")
    assert "due_date" not in payload
    # anche con la chiave a null esplicito (come la produce l'estrazione)
    fatt = dict(FATT_SENZA_RITENUTA, scadenza_pagamento=None)
    assert "due_date" not in fattura_a_purchase_invoice(fatt, supplier="S")


def test_scadenza_precedente_alla_data_viene_ignorata() -> None:
    # Una scadenza prima dell'emissione è una lettura sbagliata: meglio ometterla
    # che farsi rifiutare la PI ("Due Date cannot be before Posting/Supplier Invoice Date").
    fatt = dict(FATT_SENZA_RITENUTA, scadenza_pagamento="2026-01-15")  # data: 2026-02-01
    payload = fattura_a_purchase_invoice(fatt, supplier="Studio Bianchi")
    assert "due_date" not in payload


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


def test_ddt_righe_con_articolo_generico() -> None:
    # La Purchase Receipt è un documento di magazzino: ERPNext pretende un
    # `item_code` esistente e rifiuta la riga a testo libero ("Item None does not
    # exist"). Workflower non ha anagrafica articoli → articolo generico configurato.
    payload = ddt_a_purchase_receipt(
        DDT, supplier="Ferramenta Rossi", item_code="MATERIALE-GENERICO"
    )
    assert all(i["item_code"] == "MATERIALE-GENERICO" for i in payload["items"])
    # la descrizione vera resta sulla riga: l'articolo generico non la sostituisce
    assert payload["items"][0]["description"] == "Tondino acciaio"


def test_ddt_righe_senza_articolo_non_lo_riportano() -> None:
    payload = ddt_a_purchase_receipt(DDT, supplier="Ferramenta Rossi")
    assert all("item_code" not in i for i in payload["items"])


def test_ddt_project_sulle_righe() -> None:
    payload = ddt_a_purchase_receipt(
        DDT, supplier="Ferramenta Rossi", project="Residenza Le Palme"
    )
    assert all(i["project"] == "Residenza Le Palme" for i in payload["items"])


# ------------------------------------------------------------ materiali / listino (M34)

MATERIALE = {
    "codice": "CLS-C2530",
    "descrizione": "Calcestruzzo C25/30",
    "unita_misura": "mc",
    "prezzo_unitario": 105.0,
    "categoria": "strutture",
    "fornitore_id": "FRN-001",
}


def test_materiale_a_item() -> None:
    payload = materiale_a_item(MATERIALE, item_group="Materiali di cantiere")
    assert payload["item_code"] == "CLS-C2530"
    assert payload["item_name"] == "Calcestruzzo C25/30"
    assert payload["item_group"] == "Materiali di cantiere"
    assert payload["stock_uom"] == "mc"
    assert payload["is_stock_item"] == 0  # niente giacenze: WF non fa magazzino
    assert payload["is_purchase_item"] == 1


def test_materiale_senza_codice_usa_l_id_entita() -> None:
    senza = dict(MATERIALE, codice=None)
    payload = materiale_a_item(senza, item_code="MAT-003")
    assert payload["item_code"] == "MAT-003"  # il codice a valle resta rintracciabile


def test_materiale_senza_unita_niente_stock_uom() -> None:
    payload = materiale_a_item(dict(MATERIALE, unita_misura=None))
    assert "stock_uom" not in payload  # l'ERP userà la sua unità di default


# ------------------------------------------------------------ mezzi / cespiti (M33)

MEZZO_PROPRIO = {
    "descrizione": "Escavatore cingolato 20 t",
    "tipo": "escavatore",
    "targa": "EK123AB",
    "anno": 2019,
    "proprieta": "proprio",
    "valore_acquisto": 145000.0,
    "vita_utile_anni": 8,
}


def test_mezzo_proprio_a_asset_con_ammortamento() -> None:
    payload = mezzo_a_asset(
        MEZZO_PROPRIO, item_code="WF-MEZZO", location="Sede", company="Edile SpA"
    )
    assert payload["asset_name"] == "Escavatore cingolato 20 t (EK123AB)"
    assert payload["item_code"] == "WF-MEZZO"
    assert payload["location"] == "Sede"
    assert payload["is_existing_asset"] == 1  # già in azienda: nessun doc d'acquisto
    assert payload["gross_purchase_amount"] == 145000.0
    assert payload["purchase_date"] == "2019-01-01"
    assert payload["calculate_depreciation"] == 1
    libro = payload["finance_books"][0]
    assert libro["depreciation_method"] == "Straight Line"
    assert libro["total_number_of_depreciations"] == 8  # una quota per anno di vita
    assert libro["frequency_of_depreciation"] == 12


def test_mezzo_senza_vita_utile_niente_ammortamento() -> None:
    mezzo = {k: v for k, v in MEZZO_PROPRIO.items() if k != "vita_utile_anni"}
    payload = mezzo_a_asset(mezzo, item_code="WF-MEZZO", location="Sede")
    assert payload is not None
    assert "calculate_depreciation" not in payload
    assert "finance_books" not in payload


def test_mezzo_a_noleggio_non_e_un_cespite() -> None:
    # Il costo del noleggio arriva già come fattura del noleggiatore: iscriverlo
    # a cespite lo conterebbe due volte e ammortizzerebbe roba non nostra.
    noleggio = dict(MEZZO_PROPRIO, proprieta="noleggio")
    assert mezzo_a_asset(noleggio, item_code="WF-MEZZO", location="Sede") is None


def test_mezzo_senza_valore_o_anno_non_si_iscrive() -> None:
    # Senza valore o anno d'acquisto il cespite sarebbe inventato: meglio niente.
    assert mezzo_a_asset(dict(MEZZO_PROPRIO, valore_acquisto=None), item_code="I", location="L") is None
    assert mezzo_a_asset(dict(MEZZO_PROPRIO, anno=None), item_code="I", location="L") is None


def test_nome_asset_preferisce_targa_poi_matricola() -> None:
    assert nome_asset({"descrizione": "Gru", "targa": "AB1", "matricola": "M9"}) == "Gru (AB1)"
    assert nome_asset({"descrizione": "Gru", "matricola": "M9"}) == "Gru (M9)"
    assert nome_asset({"descrizione": "Gru"}) == "Gru"


def test_manutenzione_a_asset_repair_documentale() -> None:
    manutenzione = {
        "mezzo_id": "MEZ-001",
        "data": "2026-04-18",
        "tipo": "tagliando",
        "descrizione": "Tagliando 2000 ore",
        "costo": 1250.0,
    }
    payload = manutenzione_a_asset_repair(manutenzione, asset="Escavatore (EK123AB)")
    assert payload["asset"] == "Escavatore (EK123AB)"
    assert payload["failure_date"] == "2026-04-18"
    assert payload["completion_date"] == "2026-04-18"
    assert payload["repair_status"] == "Completed"
    assert payload["repair_cost"] == 1250.0
    # documentale: il costo vero arriva già dalla fattura dell'officina
    assert payload["capitalize_repair_cost"] == 0
    assert payload["description"] == "tagliando: Tagliando 2000 ore"


def test_manutenzione_senza_costo_ne_descrizione() -> None:
    payload = manutenzione_a_asset_repair(
        {"mezzo_id": "MEZ-001", "data": "2026-01-01", "tipo": "revisione"}, asset="Gru"
    )
    assert payload["description"] == "revisione"
    assert "repair_cost" not in payload


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
