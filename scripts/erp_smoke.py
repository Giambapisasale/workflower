#!/usr/bin/env python3
"""Smoke test dell'integrazione ERP contro un'istanza ERPNext **reale**.

Verifica end-to-end che deploy e configurazione siano a posto, usando lo stesso
codice della sincronizzazione (client + translator). NON è un test pytest: si lancia
a mano (o in un runbook di deploy) e stampa PASS/FAIL per passo, con exit code != 0
al primo problema bloccante.

Uso:
    export ERP_BASE_URL=https://erp.miosito.it
    export ERP_API_KEY=...            ERP_API_SECRET=...
    export ERP_COMPANY="La Mia Azienda"      # per Cost Center / Purchase Invoice
    export ERP_CONTO_RITENUTA="Ritenute - X" # per il passo --full
    make erp-smoke                # oppure: python scripts/erp_smoke.py
    make erp-smoke ARGS=--full    # include la creazione di una Purchase Invoice

I record creati sono di prova e riconoscibili dal prefisso "WF-SMOKE".
"""

import argparse
import sys

# I messaggi usano frecce ed em-dash: su Windows la console è cp1252 e un print()
# fallirebbe con UnicodeEncodeError proprio mentre stampa un [PASS]. Forziamo UTF-8
# sui flussi dello script prima di scrivere qualsiasi cosa.
for _flusso in (sys.stdout, sys.stderr):
    if hasattr(_flusso, "reconfigure"):
        _flusso.reconfigure(encoding="utf-8", errors="replace")

from app.core.erp import (  # noqa: E402  (dopo la riconfigurazione dei flussi)
    ErpClient,
    ErpConfig,
    ErpError,
    cantiere_a_cost_center,
    conto_costo_predefinito,
    fattura_a_purchase_invoice,
    fornitore_a_supplier,
    radice_cost_center,
)

PREFISSO = "WF-SMOKE"

# Anagrafica e documento sintetici (riconoscibili, ripetibili).
FORNITORE = {"ragione_sociale": f"{PREFISSO} Studio Verifica", "partita_iva": "00000000000"}
CANTIERE = {"nome": f"{PREFISSO} Cantiere Verifica"}
FATTURA = {
    "numero": f"{PREFISSO}-001",
    "data": "2026-01-15",
    "imponibile": 1000.0,
    "iva": 220.0,
    "totale": 1220.0,
    "ritenuta_acconto": 200.0,
    "righe": [{"descrizione": f"{PREFISSO} prestazione", "quantita": None, "importo": 1000.0}],
}

VERDE, ROSSO, GIALLO, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def _ok(nome: str, dettaglio: str = "") -> None:
    print(f"{VERDE}[PASS]{RESET} {nome}" + (f" — {dettaglio}" if dettaglio else ""))


def _ko(nome: str, dettaglio: str) -> None:
    print(f"{ROSSO}[FAIL]{RESET} {nome} — {dettaglio}")


def _skip(nome: str, dettaglio: str) -> None:
    print(f"{GIALLO}[SKIP]{RESET} {nome} — {dettaglio}")


def _upsert(client: ErpClient, doctype: str, filtri: list, payload: dict) -> str:
    esistenti = client.trova_documenti(doctype, filtri)
    if esistenti:
        return esistenti[0]["name"]
    return client.crea_documento(doctype, payload)["name"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test integrazione ERPNext")
    parser.add_argument(
        "--full", action="store_true", help="crea anche una Purchase Invoice (richiede master data)"
    )
    args = parser.parse_args()

    config = ErpConfig.da_env()
    if config is None:
        _ko("configurazione", "ERP_BASE_URL/ERP_API_KEY/ERP_API_SECRET non tutte impostate")
        return 2
    client = ErpClient(config)
    print(f"ERPNext: {config.base_url}  (company={config.company or '—'})\n")

    problemi = 0

    # 1) Connettività + autenticazione
    try:
        corpo = client.richiesta("GET", "/api/method/frappe.auth.get_logged_user")
        utente = corpo.get("message") if isinstance(corpo, dict) else corpo
        _ok("connettività/auth", f"utente: {utente}")
    except ErpError as exc:
        _ko("connettività/auth", str(exc))
        return 1  # senza connettività il resto non ha senso

    # 2) Fornitore -> Supplier (upsert per partita IVA)
    try:
        supplier = _upsert(
            client,
            "Supplier",
            [["tax_id", "=", FORNITORE["partita_iva"]]],
            fornitore_a_supplier(FORNITORE, supplier_group=config.supplier_group),
        )
        _ok("fornitore→Supplier", supplier)
    except ErpError as exc:
        _ko("fornitore→Supplier", str(exc))
        supplier = None
        problemi += 1

    # 3) Cantiere -> Cost Center (richiede company)
    cost_center = None
    if config.company:
        try:
            padre = config.parent_cost_center or radice_cost_center(client, config.company)
            payload = cantiere_a_cost_center(
                CANTIERE, company=config.company, parent_cost_center=padre
            )
            filtri = [
                ["cost_center_name", "=", payload["cost_center_name"]],
                ["company", "=", config.company],
            ]
            cost_center = _upsert(client, "Cost Center", filtri, payload)
            _ok("cantiere→Cost Center", cost_center)
        except ErpError as exc:
            _ko("cantiere→Cost Center", str(exc))
            problemi += 1
    else:
        _skip("cantiere→Cost Center", "ERP_COMPANY non impostata")

    # 4) Fattura con ritenuta -> Purchase Invoice (solo con --full)
    if args.full:
        if not supplier:
            _ko("fattura→Purchase Invoice", "manca il Supplier del passo precedente")
            problemi += 1
        else:
            try:
                conto_costo = config.conto_costo
                if not conto_costo and config.company:
                    conto_costo = conto_costo_predefinito(client, config.company)
                pi = client.crea_documento(
                    "Purchase Invoice",
                    fattura_a_purchase_invoice(
                        FATTURA,
                        supplier=supplier,
                        cost_center=cost_center,
                        conto_ritenuta=config.conto_ritenuta,
                        conto_iva=config.conto_iva,
                        conto_costo=conto_costo,
                    ),
                )
                rit = FATTURA["ritenuta_acconto"]
                _ok("fattura→Purchase Invoice", f"{pi.get('name')} (ritenuta {rit})")
            except ErpError as exc:
                _ko(
                    "fattura→Purchase Invoice",
                    f"{exc}  (spesso è master data ERPNext: item/conti/company)",
                )
                problemi += 1
    else:
        _skip("fattura→Purchase Invoice", "aggiungi --full per crearla")

    # 5) Allegato -> File (frappe.client.attach_file)
    # Ci è costato un guasto silenzioso: i parametri del metodo si chiamano
    # doctype/docname, Frappe scarta i kwargs fuori firma e muore su get_doc(None).
    # Contro il finto non si vedeva: qui sì, a ogni smoke.
    if supplier:
        try:
            import base64

            nome_file = f"{PREFISSO}-verifica.txt"
            client.chiama_metodo(
                "frappe.client.attach_file",
                {
                    "filename": nome_file,
                    "filedata": base64.b64encode(b"WF-SMOKE").decode("ascii"),
                    "doctype": "Supplier",
                    "docname": supplier,
                    "decode_base64": 1,
                    "is_private": 1,
                },
            )
            _ok("allegato→File", f"{nome_file} su Supplier {supplier}")
        except ErpError as exc:
            _ko("allegato→File", str(exc))
            problemi += 1
    else:
        _skip("allegato→File", "manca il Supplier del passo 2")

    print()
    if problemi:
        print(f"{ROSSO}Smoke test: {problemi} problema/i.{RESET}")
        return 1
    print(f"{VERDE}Smoke test: tutto ok.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
