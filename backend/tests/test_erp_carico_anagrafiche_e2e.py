"""Carico anagrafiche in blocco (Fascia A, M31/A5). Copre gli AC della milestone:

le anagrafiche non passano dalla revisione, quindi senza questo carico arrivano a
valle solo se citate da un documento. `POST /api/erp/carica-anagrafiche` fa l'upsert
di tutti i fornitori (Supplier + gruppo + Address/Contact, anche a completamento di
un Supplier nato altrove) e cantieri (Cost Center + Project), con backref
`meta.erp_id`, ledger, idempotenza e conteggio degli errori. Nessun ERPNext reale.
"""

from dataclasses import replace
from pathlib import Path

import pytest
from aiuti import accedi
from fake_erp import ErpServerFinto

from app.core.dal import DAL
from app.core.dataset import leggi_sync_erp
from app.core.erp import ErpClient, ErpConfig

pytestmark = pytest.mark.erp

CONFIG = ErpConfig(
    base_url="http://erp.test", api_key="k", api_secret="s", company="Edile SpA"
)
# Con il master data dei cespiti (M33): articolo cespite + location configurati.
CONFIG_CESPITI = replace(CONFIG, asset_item="WF-MEZZO", asset_location="Sede")


def test_carico_porta_fornitori_e_cantieri(crea_client, dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    n_forn = len(dal.list_all("fornitore"))
    n_cant = len(dal.list_all("cantiere"))
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    r = client.post("/api/erp/carica-anagrafiche", headers=admin).json()
    assert r["esito"] == "ok"
    assert r["per_tipo"]["fornitore"]["inviate"] == n_forn
    assert r["per_tipo"]["fornitore"]["errori"] == 0
    assert r["per_tipo"]["cantiere"]["inviate"] == n_cant

    assert len(server.post_di("Supplier")) == n_forn
    assert len(server.post_di("Address")) == n_forn  # il seed ha sempre indirizzo+comune
    assert len(server.post_di("Contact")) == n_forn
    assert len(server.post_di("Cost Center")) == n_cant
    assert len(server.post_di("Project")) == n_cant

    # backref su ogni anagrafica + riga ok nel ledger (fornitori, cantieri e
    # materiali; mezzi/manutenzioni saltano: CONFIG non ha il master data cespiti)
    dal = DAL(dati_rw)
    assert all(e.meta.erp_id for e in dal.list_all("fornitore"))
    assert all(e.meta.erp_id for e in dal.list_all("cantiere"))
    ok_ledger = [x for x in leggi_sync_erp(dati_rw) if x["esito"] == "ok"]
    assert len(ok_ledger) == n_forn + n_cant + len(dal.list_all("materiale"))


def test_carico_idempotente(crea_client, dati_rw: Path) -> None:
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    client.post("/api/erp/carica-anagrafiche", headers=admin)
    prima = len(leggi_sync_erp(dati_rw))
    n_supplier = len(server.post_di("Supplier"))

    r = client.post("/api/erp/carica-anagrafiche", headers=admin).json()
    assert r["per_tipo"]["fornitore"]["inviate"] == 0
    assert r["per_tipo"]["fornitore"]["gia_allineate"] > 0
    assert r["per_tipo"]["cantiere"]["inviate"] == 0
    assert len(server.post_di("Supplier")) == n_supplier  # nessun doppione a valle
    assert len(leggi_sync_erp(dati_rw)) == prima  # niente ledger per il "già allineato"


def test_carico_completa_un_supplier_nato_altrove(crea_client, dati_rw: Path) -> None:
    """Un Supplier creato a mano in ERP (solo nome e P.IVA) viene completato:
    gruppo dalla categoria via PUT, Address e Contact mancanti, backref in WF."""
    dal = DAL(dati_rw)
    forn = dal.list_all("fornitore")[0]
    server = ErpServerFinto()
    server.per_doctype.setdefault("Supplier", []).append(
        {
            "name": forn.dati["ragione_sociale"],
            "tax_id": forn.dati["partita_iva"],
            "supplier_group": "All Supplier Groups",
        }
    )
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    r = client.post("/api/erp/carica-anagrafiche", headers=admin).json()
    assert r["esito"] == "ok"
    record = server.per_doctype["Supplier"][0]
    assert record["supplier_group"] == forn.dati["categoria"]  # completato via PUT
    indirizzi = [
        a
        for a in server.documenti("Address")
        if any(l["link_name"] == record["name"] for l in a.get("links", []))
    ]
    assert len(indirizzi) == 1
    assert DAL(dati_rw).read("fornitore", forn.id).meta.erp_id == record["name"]


def test_carico_conta_gli_errori_senza_fermarsi(crea_client, dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    n_forn = len(dal.list_all("fornitore"))
    n_cant = len(dal.list_all("cantiere"))
    server = ErpServerFinto(errore_su={"Supplier"})
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    r = client.post("/api/erp/carica-anagrafiche", headers=admin).json()
    assert r["esito"] == "ok"  # il giro finisce comunque
    assert r["per_tipo"]["fornitore"]["errori"] == n_forn
    assert r["per_tipo"]["cantiere"]["inviate"] == n_cant  # i cantieri passano
    errori_ledger = [x for x in leggi_sync_erp(dati_rw) if x["esito"] == "errore"]
    assert len(errori_ledger) == n_forn


def test_carico_senza_company_cantieri_come_solo_project(crea_client, dati_rw: Path) -> None:
    """Senza ERP_COMPANY il Cost Center non è creabile: resta il Project come àncora."""
    config = ErpConfig(base_url="http://erp.test", api_key="k", api_secret="s")
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=config, transport=server))
    admin = accedi(client, "giovanna")

    r = client.post("/api/erp/carica-anagrafiche", headers=admin).json()
    assert r["per_tipo"]["cantiere"]["errori"] == 0
    assert not server.post_di("Cost Center")
    assert len(server.post_di("Project")) == len(DAL(dati_rw).list_all("cantiere"))
    assert all(e.meta.erp_id for e in DAL(dati_rw).list_all("cantiere"))


def test_carico_materiali_come_listino(crea_client, dati_rw: Path) -> None:
    """M34: ogni materiale diventa Item (non di magazzino) con prezzo su Standard
    Buying e fornitore abituale; senza codice si usa l'id entità."""
    dal = DAL(dati_rw)
    materiali = dal.list_all("materiale")
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    r = client.post("/api/erp/carica-anagrafiche", headers=admin).json()
    assert r["per_tipo"]["materiale"]["inviate"] == len(materiali)
    assert r["per_tipo"]["materiale"]["errori"] == 0

    articoli = server.post_di("Item")
    codici = {a["item_code"] for a in articoli}
    # i codici di listino quando ci sono, l'id entità come fallback
    for m in materiali:
        assert (m.dati.get("codice") or m.id) in codici
    assert all(a["is_stock_item"] == 0 for a in articoli)

    prezzi = server.post_di("Item Price")
    con_prezzo = [m for m in materiali if m.dati.get("prezzo_unitario") is not None]
    assert len(prezzi) == len(con_prezzo)
    assert all(p["price_list"] == "Standard Buying" for p in prezzi)

    # il fornitore abituale è agganciato all'Item (Item Supplier alla creazione)
    con_fornitore = [m for m in materiali if m.dati.get("fornitore_id")]
    agganciati = [a for a in articoli if a.get("supplier_items")]
    assert len(agganciati) == len(con_fornitore)

    # le unità di misura di cantiere esistono a valle come UOM
    unita_attese = {m.dati["unita_misura"] for m in materiali if m.dati.get("unita_misura")}
    assert {u["uom_name"] for u in server.post_di("UOM")} == unita_attese

    assert all(e.meta.erp_id for e in DAL(dati_rw).list_all("materiale"))


def test_carico_materiali_aggiorna_il_prezzo(crea_client, dati_rw: Path) -> None:
    """Un listino che invecchia è un listino sbagliato: al secondo carico il prezzo
    cambiato in Workflower aggiorna l'Item Price a valle (PUT), senza doppioni."""
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    client.post("/api/erp/carica-anagrafiche", headers=admin)
    n_item = len(server.post_di("Item"))
    n_prezzi = len(server.post_di("Item Price"))

    dal = DAL(dati_rw)
    materiale = next(m for m in dal.list_all("materiale") if m.dati.get("prezzo_unitario"))
    materiale.dati["prezzo_unitario"] = 999.99
    dal.update(materiale)

    client.post("/api/erp/carica-anagrafiche", headers=admin)
    assert len(server.post_di("Item")) == n_item  # nessun articolo duplicato
    assert len(server.post_di("Item Price")) == n_prezzi  # aggiornato, non ricreato
    codice = materiale.dati.get("codice") or materiale.id
    prezzo_a_valle = next(
        p for p in server.documenti("Item Price") if p["item_code"] == codice
    )
    assert prezzo_a_valle["price_list_rate"] == 999.99


def test_carico_mezzi_e_manutenzioni_come_cespiti(crea_client, dati_rw: Path) -> None:
    """M33: il mezzo di proprietà diventa Asset con ammortamento, le sue manutenzioni
    Asset Repair documentali; i mezzi a noleggio si saltano (non sono cespiti)."""
    dal = DAL(dati_rw)
    propri = [m for m in dal.list_all("mezzo") if m.dati.get("proprieta") == "proprio"]
    noleggi = [m for m in dal.list_all("mezzo") if m.dati.get("proprieta") != "proprio"]
    n_manutenzioni = len(dal.list_all("manutenzione"))
    assert propri and noleggi and n_manutenzioni  # il seed copre tutti i casi

    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG_CESPITI, transport=server))
    admin = accedi(client, "giovanna")

    r = client.post("/api/erp/carica-anagrafiche", headers=admin).json()
    assert r["per_tipo"]["mezzo"]["inviate"] == len(propri)
    assert r["per_tipo"]["mezzo"]["saltate"] == len(noleggi)
    assert r["per_tipo"]["mezzo"]["errori"] == 0
    assert r["per_tipo"]["manutenzione"]["inviate"] == n_manutenzioni

    cespiti = server.post_di("Asset")
    assert len(cespiti) == len(propri)
    assert cespiti[0]["calculate_depreciation"] == 1  # MEZ-001 ha la vita utile
    assert cespiti[0]["item_code"] == "WF-MEZZO"

    riparazioni = server.post_di("Asset Repair")
    assert len(riparazioni) == n_manutenzioni
    assert all(rep["asset"] == cespiti[0]["asset_name"] for rep in riparazioni)
    assert all(rep["capitalize_repair_cost"] == 0 for rep in riparazioni)

    dal = DAL(dati_rw)
    assert all(m.meta.erp_id for m in dal.list_all("manutenzione"))
    assert dal.read("mezzo", propri[0].id).meta.erp_id
    assert all(not m.meta.erp_id for m in dal.list_all("mezzo") if m.dati.get("proprieta") != "proprio")


def test_carico_manutenzioni_idempotente(crea_client, dati_rw: Path) -> None:
    """L'Asset Repair non ha chiave naturale: il backref evita il doppione."""
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG_CESPITI, transport=server))
    admin = accedi(client, "giovanna")

    client.post("/api/erp/carica-anagrafiche", headers=admin)
    prima = len(server.post_di("Asset Repair"))
    r = client.post("/api/erp/carica-anagrafiche", headers=admin).json()
    assert len(server.post_di("Asset Repair")) == prima  # nessun doppione
    assert r["per_tipo"]["manutenzione"]["inviate"] == 0
    assert r["per_tipo"]["manutenzione"]["gia_allineate"] == prima
    assert len(server.post_di("Asset")) == len(
        [m for m in DAL(dati_rw).list_all("mezzo") if m.dati.get("proprieta") == "proprio"]
    )


def test_carico_senza_config_cespiti_salta_senza_errori(crea_client, dati_rw: Path) -> None:
    """Chi non vuole i cespiti a valle non deve trovare il carico pieno di rossi:
    senza ERP_ASSET_ITEM/ERP_ASSET_LOCATION mezzi e manutenzioni si saltano."""
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    r = client.post("/api/erp/carica-anagrafiche", headers=admin).json()
    assert r["per_tipo"]["mezzo"]["errori"] == 0
    assert r["per_tipo"]["mezzo"]["inviate"] == 0
    assert r["per_tipo"]["mezzo"]["saltate"] == len(DAL(dati_rw).list_all("mezzo"))
    assert r["per_tipo"]["manutenzione"]["saltate"] == len(DAL(dati_rw).list_all("manutenzione"))
    assert not server.post_di("Asset")
    assert not server.post_di("Asset Repair")


def test_carico_erp_non_configurato(
    crea_client, dati_rw: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for v in ("ERP_BASE_URL", "ERP_API_KEY", "ERP_API_SECRET"):
        monkeypatch.delenv(v, raising=False)
    client = crea_client()
    admin = accedi(client, "giovanna")
    r = client.post("/api/erp/carica-anagrafiche", headers=admin).json()
    assert r["esito"] == "erp_non_configurato"
    assert leggi_sync_erp(dati_rw) == []


def test_carico_riservato_all_ufficio(crea_client, dati_rw: Path) -> None:
    """Come le altre azioni ERP: operatore fuori, solo admin."""
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    operatore = accedi(client, "salvo")  # operatore di cantiere, non ufficio
    resp = client.post("/api/erp/carica-anagrafiche", headers=operatore)
    assert resp.status_code == 403
    assert server.chiamate == []