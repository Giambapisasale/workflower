#!/usr/bin/env python3
"""Prepara un'istanza ERPNext **di sviluppo** per la verifica dell'integrazione.

Gira *dentro* al container `backend` di `docker-compose.erpnext.yml` (usa l'ambiente
Frappe del bench, non quello di Workflower). Lo si lancia con:

    make erp-dev-setup

Rende ripetibile ciò che altrimenti va fatto a mano nella UI di ERPNext prima di
poter eseguire `make erp-smoke`, ed è **idempotente** (rilanciarlo non duplica nulla):

1. completa il *setup wizard* se non esiste una Company (crea piano dei conti,
   anno fiscale, cost center radice, magazzini);
2. crea il conto **Ritenute** (la ritenuta d'acconto entra come riga in detrazione);
3. crea un **articolo generico non di magazzino** per le righe di Purchase Receipt,
   che ERPNext pretende sui DDT (Workflower non ha anagrafica articoli);
4. genera le **API key** dell'Administrator e stampa le `ERP_*` da esportare.

Solo per sviluppo/PoC: usa una company di prova e la password admin del compose.
In produzione si segue la procedura ERPNext (setup wizard dalla UI, utente API
dedicato con i soli permessi necessari).

Parametri opzionali via ambiente: ``WF_COMPANY``, ``WF_ABBR``, ``WF_COUNTRY``,
``WF_CURRENCY``, ``WF_SITE``.
"""

import os
import sys

import frappe

AZIENDA = os.environ.get("WF_COMPANY", "Aitho Costruzioni")
SIGLA = os.environ.get("WF_ABBR", "AC")
PAESE = os.environ.get("WF_COUNTRY", "Italy")
VALUTA = os.environ.get("WF_CURRENCY", "EUR")
SITO = os.environ.get("WF_SITE", "frontend")

CONTO_RITENUTA = "Ritenute"
ITEM_DDT = "WF-MATERIALE-CANTIERE"

passi: list[str] = []


def _nota(testo: str) -> None:
    passi.append(testo)
    print(f"  - {testo}")


def prepara_azienda() -> None:
    """Setup wizard (una volta sola): Company, piano dei conti, anno fiscale."""
    if frappe.get_all("Company", limit=1):
        _nota(f"Company già presente ({frappe.get_all('Company', pluck='name')[0]})")
        return
    from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

    frappe.flags.in_setup_wizard = True
    setup_complete(
        {
            "language": "English",
            "country": PAESE,
            "timezone": "Europe/Rome",
            "currency": VALUTA,
            "company_name": AZIENDA,
            "company_abbr": SIGLA,
            "chart_of_accounts": "Standard",
            "fy_start_date": "2026-01-01",
            "fy_end_date": "2026-12-31",
            "setup_demo": 0,
            "full_name": "Administrator",
            "email": "admin@example.com",
        }
    )
    frappe.db.commit()
    _nota(f"Company creata: {AZIENDA} ({SIGLA}) — piano dei conti {PAESE}")


def prepara_conto_ritenuta() -> str | None:
    """Conto della ritenuta d'acconto, sotto i conti d'imposta della Company."""
    sigla = frappe.get_value("Company", AZIENDA, "abbr") or SIGLA
    atteso = f"{CONTO_RITENUTA} - {sigla}"
    if frappe.db.exists("Account", atteso):
        _nota(f"conto ritenuta già presente: {atteso}")
        return atteso
    padre = f"Duties and Taxes - {sigla}"
    if not frappe.db.exists("Account", padre):
        _nota(f"ATTENZIONE: manca il gruppo '{padre}': conto ritenuta non creato")
        return None
    conto = frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": CONTO_RITENUTA,
            "parent_account": padre,
            "company": AZIENDA,
            "account_type": "Tax",
            "root_type": "Liability",
            "is_group": 0,
        }
    )
    conto.insert(ignore_permissions=True)
    frappe.db.commit()
    _nota(f"conto ritenuta creato: {conto.name}")
    return conto.name


def prepara_item_ddt() -> str:
    """Articolo generico NON di magazzino per le righe di Purchase Receipt.

    La Purchase Receipt è un documento di magazzino e ERPNext rifiuta la riga a
    testo libero; con ``is_stock_item=0`` non si movimenta il magazzino e la
    descrizione vera del DDT resta sulla riga.
    """
    if frappe.db.exists("Item", ITEM_DDT):
        _nota(f"articolo DDT già presente: {ITEM_DDT}")
        return ITEM_DDT
    gruppi = frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name")
    articolo = frappe.get_doc(
        {
            "doctype": "Item",
            "item_code": ITEM_DDT,
            "item_name": "Materiale di cantiere (generico)",
            "item_group": gruppi[0],
            "stock_uom": "Nos",
            "is_stock_item": 0,
            "is_purchase_item": 1,
        }
    )
    articolo.insert(ignore_permissions=True)
    frappe.db.commit()
    _nota(f"articolo DDT creato: {articolo.name} (non di magazzino)")
    return articolo.name


def prepara_chiavi() -> tuple[str, str]:
    """API key/secret dell'Administrator (il secret è visibile solo qui)."""
    utente = frappe.get_doc("User", "Administrator")
    if not utente.api_key:
        utente.api_key = frappe.generate_hash(length=15)
    segreto = frappe.generate_hash(length=15)
    utente.api_secret = segreto
    utente.save(ignore_permissions=True)
    frappe.db.commit()
    _nota("API key rigenerate per Administrator")
    return utente.api_key, segreto


def main() -> int:
    frappe.init(site=SITO)
    frappe.connect()
    try:
        print(f"Preparazione ERPNext (sito {SITO}) — solo sviluppo/PoC\n")
        prepara_azienda()
        conto_ritenuta = prepara_conto_ritenuta()
        item_ddt = prepara_item_ddt()
        chiave, segreto = prepara_chiavi()
        sigla = frappe.get_value("Company", AZIENDA, "abbr") or SIGLA
        conto_iva = f"IVA 22% - {sigla}"
        if not frappe.db.exists("Account", conto_iva):
            conto_iva = ""

        # L'URL cambia con CHI chiama: dall'host è localhost, dal container no
        # (dentro al container "localhost" è il container stesso).
        righe = [
            ("ERP_API_KEY", chiave),
            ("ERP_API_SECRET", segreto),
            ("ERP_COMPANY", AZIENDA),
            ("ERP_CONTO_RITENUTA", conto_ritenuta or ""),
            ("ERP_CONTO_IVA", conto_iva),
            ("ERP_ITEM_DDT", item_ddt),
        ]
        coppie = [(n, v) for n, v in righe if v]

        print("\n" + "=" * 72)
        print("1) INCOLLA NEL FILE .env  (serve all'app in container: senza queste")
        print("   righe l'integrazione parte SPENTA, in silenzio)")
        print("=" * 72)
        print("ERP_BASE_URL=http://host.docker.internal:8080")
        for nome, valore in coppie:
            print(f"{nome}={valore}")

        # Dall'host l'URL è localhost. La sintassi NON è intercambiabile fra le
        # shell: in cmd.exe `set X="v"` mette le virgolette dentro al valore, e
        # l'URL non viene più riconosciuto come tale.
        host = [("ERP_BASE_URL", "http://localhost:8080"), *coppie]
        formati = [
            ("PowerShell", '$env:{n} = "{v}"'),
            ("cmd.exe (niente virgolette: finirebbero DENTRO al valore)", "set {n}={v}"),
            ("bash / zsh", 'export {n}="{v}"'),
        ]

        print("\n" + "=" * 72)
        print("2) IMPOSTA NELLA SHELL  (serve agli script dall'host: erp-smoke, pytest)")
        print("   Usa SOLO il blocco della tua shell.")
        print("=" * 72)
        for etichetta, modello in formati:
            print(f"\n--- {etichetta} ---")
            for nome, valore in host:
                print(modello.format(n=nome, v=valore))

        print("\nOgni esecuzione RIGENERA il secret (Frappe non lo rilegge): le")
        print("ERP_API_SECRET copiate prima smettono di valere. Lancialo una volta")
        print("e conserva i valori; rilancialo solo per rifarli.")
        print("\nPoi:  make erp-smoke ARGS=--full")
        print("La scrivania ERPNext è su http://localhost:8080/app (non la radice).")
        return 0
    finally:
        frappe.destroy()


if __name__ == "__main__":
    sys.exit(main())
