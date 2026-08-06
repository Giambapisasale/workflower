"""Fascia A, M30: documenti a valle più ricchi. Copre gli AC della milestone:

il cantiere diventa **Project** (date, budget, cost center) e finisce su testata e
righe di Purchase Invoice/Receipt; il Supplier nuovo nasce col corredo (gruppo dalla
categoria, **Address**, **Contact**); il blob di ``meta.origine`` viene **allegato**
al documento a valle via ``frappe.client.attach_file``; ogni pezzo di corredo è
best-effort e non fa mai fallire la sincronizzazione. Nessun ERPNext reale.
"""

from pathlib import Path

import pytest
from aiuti import accedi
from fake_erp import ErpServerFinto

from app.core.dal import DAL
from app.core.erp import ErpClient, ErpConfig
from app.models.envelope import Meta

pytestmark = pytest.mark.erp

CONFIG = ErpConfig(
    base_url="http://erp.test",
    api_key="k",
    api_secret="s",
    company="Edile SpA",
    conto_ritenuta="Ritenute - E",
    item_ddt="MATERIALE-GENERICO",
)


def _bozza_fattura(dati_rw: Path, *, origine: str | None = None) -> "object":
    """Una bozza fattura dal seed, con blob d'origine opzionale."""
    dal = DAL(dati_rw)
    seed = next(e for e in dal.list_all("fattura") if e.dati.get("fornitore_id"))
    meta = Meta(origine=origine) if origine else None
    return dal.crea_progressivo("fattura", dict(seed.dati), stato="bozza", meta=meta)


# ------------------------------------------------------------------ project (A2)


def test_validate_crea_project_del_cantiere(crea_client, dati_rw: Path) -> None:
    bozza = _bozza_fattura(dati_rw)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.json()["erp"]["esito"] == "ok"

    cantiere = DAL(dati_rw).read("cantiere", bozza.dati["cantiere_id"]).dati
    progetto = server.post_di("Project")[0]
    assert progetto["project_name"] == cantiere["nome"]
    assert progetto["expected_start_date"] == cantiere["data_inizio"]
    assert progetto["estimated_costing"] == cantiere["budget"]
    assert progetto["company"] == "Edile SpA"
    # il Project è ancorato al Cost Center del cantiere
    assert progetto["cost_center"] == cantiere["nome"]

    pi = server.post_di("Purchase Invoice")[0]
    assert pi["project"] == cantiere["nome"]
    assert all(i["project"] == cantiere["nome"] for i in pi["items"])


def test_project_riusato_fra_documenti_dello_stesso_cantiere(crea_client, dati_rw: Path) -> None:
    b1 = _bozza_fattura(dati_rw)
    b2 = _bozza_fattura(dati_rw)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    client.post(f"/api/review/{b1.id}/validate", headers=admin)
    client.post(f"/api/review/{b2.id}/validate", headers=admin)
    assert len(server.post_di("Project")) == 1  # upsert per project_name


def test_ddt_porta_il_project_sulle_righe(crea_client, dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    seed = next(e for e in dal.list_all("ddt") if e.dati.get("fornitore_id"))
    bozza = dal.crea_progressivo("ddt", dict(seed.dati), stato="bozza")
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.json()["erp"]["esito"] == "ok"
    pr = server.post_di("Purchase Receipt")[0]
    nome_cantiere = DAL(dati_rw).read("cantiere", bozza.dati["cantiere_id"]).dati["nome"]
    assert all(i["project"] == nome_cantiere for i in pr["items"])


def test_fattura_senza_cantiere_niente_project(crea_client, dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    seed = next(e for e in dal.list_all("fattura") if e.dati.get("fornitore_id"))
    bozza = dal.crea_progressivo("fattura", dict(seed.dati, cantiere_id=None), stato="bozza")
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.json()["erp"]["esito"] == "ok"
    assert not server.post_di("Project")


def test_project_che_fallisce_non_blocca_la_fattura(crea_client, dati_rw: Path) -> None:
    """Il Project è corredo: se non passa, la PI arriva lo stesso (senza project)."""
    bozza = _bozza_fattura(dati_rw)
    server = ErpServerFinto(errore_su={"Project"})
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.json()["erp"]["esito"] == "ok"
    pi = server.post_di("Purchase Invoice")[0]
    assert "project" not in pi
    assert DAL(dati_rw).read("fattura", bozza.id).meta.erp_id


# ------------------------------------------------------------ corredo fornitore (A3)


def test_supplier_nuovo_nasce_col_corredo(crea_client, dati_rw: Path) -> None:
    """Il fornitore del seed ha categoria, indirizzo, PEC e telefono: a valle nascono
    Supplier Group, Address e Contact collegati."""
    bozza = _bozza_fattura(dati_rw)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.json()["erp"]["esito"] == "ok"

    forn = DAL(dati_rw).read("fornitore", bozza.dati["fornitore_id"]).dati
    supplier = server.post_di("Supplier")[0]
    assert supplier["supplier_group"] == forn["categoria"]  # gruppo dalla categoria
    assert server.post_di("Supplier Group")[0]["supplier_group_name"] == forn["categoria"]

    indirizzo = server.post_di("Address")[0]
    assert indirizzo["address_line1"] == forn["indirizzo"]
    assert indirizzo["city"] == forn["comune"]
    assert indirizzo["country"] == "Italy"
    assert indirizzo["links"] == [
        {"link_doctype": "Supplier", "link_name": forn["ragione_sociale"]}
    ]

    contatto = server.post_di("Contact")[0]
    assert contatto["email_ids"][0]["email_id"] == forn["pec"]
    assert contatto["phone_nos"][0]["phone"] == forn["telefono"]


def test_corredo_non_duplicato_su_secondo_documento(crea_client, dati_rw: Path) -> None:
    b1 = _bozza_fattura(dati_rw)
    b2 = _bozza_fattura(dati_rw)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    client.post(f"/api/review/{b1.id}/validate", headers=admin)
    client.post(f"/api/review/{b2.id}/validate", headers=admin)
    # il Supplier esiste già alla seconda fattura: nessun nuovo corredo
    assert len(server.post_di("Address")) == 1
    assert len(server.post_di("Contact")) == 1


def test_corredo_che_fallisce_non_blocca_la_fattura(crea_client, dati_rw: Path) -> None:
    server = ErpServerFinto(errore_su={"Address", "Contact", "Supplier Group"})
    bozza = _bozza_fattura(dati_rw)
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.json()["erp"]["esito"] == "ok"
    # gruppo degradato al default, niente Address/Contact, ma la PI è passata
    assert server.post_di("Supplier")[0]["supplier_group"] == "All Supplier Groups"
    assert len(server.post_di("Purchase Invoice")) == 1


# ------------------------------------------------------------------ allegato (A1)


def test_il_blob_originale_viene_allegato(crea_client, dati_rw: Path) -> None:
    blob = dati_rw / "blobs" / "2026" / "fattura-test.pdf"
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(b"%PDF-1.4 finto")
    bozza = _bozza_fattura(dati_rw, origine="blobs/2026/fattura-test.pdf")
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.json()["erp"]["esito"] == "ok"
    assert resp.json()["erp"]["allegato"] == "fattura-test.pdf"

    erp_id = DAL(dati_rw).read("fattura", bozza.id).meta.erp_id
    allegati = server.documenti("File")
    assert len(allegati) == 1
    assert allegati[0]["attached_to_doctype"] == "Purchase Invoice"
    assert allegati[0]["attached_to_name"] == erp_id
    assert allegati[0]["file_name"] == "fattura-test.pdf"
    assert allegati[0]["is_private"] == 1


def test_senza_blob_nessun_tentativo_di_allegato(crea_client, dati_rw: Path) -> None:
    bozza = _bozza_fattura(dati_rw)  # fattura del seed: meta.origine assente
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.json()["erp"]["esito"] == "ok"
    assert resp.json()["erp"]["allegato"] is None
    assert not any("/api/method/" in c["url"] for c in server.chiamate)


def test_allegato_fallito_non_blocca_la_sincronizzazione(crea_client, dati_rw: Path) -> None:
    blob = dati_rw / "blobs" / "2026" / "fattura-test.pdf"
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(b"%PDF-1.4 finto")
    bozza = _bozza_fattura(dati_rw, origine="blobs/2026/fattura-test.pdf")
    server = ErpServerFinto()
    server.guasta("File")
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    corpo = resp.json()
    assert corpo["erp"]["esito"] == "ok"  # l'allegato è corredo, non contabilità
    assert corpo["erp"]["allegato"] is None
    assert DAL(dati_rw).read("fattura", bozza.id).meta.erp_id
    assert server.documenti("File") == []
