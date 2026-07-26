"""Sincronizzazione ERP alla validazione (Integrazione ERP, M25). Copre gli AC:

dopo `validate` la fattura compare in ERPNext come Purchase Invoice, con backref
`meta.erp_id`, riga nel ledger `erp_sync.jsonl` e commit git; la ri-sincronizzazione
è idempotente; su errore ERP la validazione **regge** (issue + riga ledger errore);
ERP non configurato = no-op. Nessun ERPNext reale: trasporto finto (fake_erp).
"""

from pathlib import Path

import pytest
from aiuti import accedi
from fake_erp import ErpServerFinto
from git import Repo

from app.core.dal import DAL
from app.core.dataset import leggi_sync_erp
from app.core.erp import ErpClient, ErpConfig, sincronizza

pytestmark = pytest.mark.erp

CONFIG = ErpConfig(
    base_url="http://erp.test",
    api_key="k",
    api_secret="s",
    company="Edile SpA",
    conto_ritenuta="Ritenute - E",
    conto_iva="IVA ns credito - E",
)


def _bozza_da_seed(dati_rw: Path, *, con_ritenuta: bool) -> "object":
    """Crea una bozza fattura copiando i dati di una fattura del seed.

    Filtra per presenza/assenza di ritenuta e per fornitore_id valorizzato (serve
    alla risoluzione del Supplier).
    """
    dal = DAL(dati_rw)
    sorgente = next(
        e
        for e in dal.list_all("fattura")
        if e.dati.get("fornitore_id") and bool(e.dati.get("ritenuta_acconto")) == con_ritenuta
    )
    return dal.crea_progressivo("fattura", dict(sorgente.dati), stato="bozza")


def _commit(data_dir: Path) -> int:
    return sum(1 for _ in Repo(data_dir).iter_commits())


def test_validate_sincronizza_purchase_invoice(crea_client, dati_rw: Path) -> None:
    bozza = _bozza_da_seed(dati_rw, con_ritenuta=False)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    prima = _commit(dati_rw)
    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["stato"] == "validato"
    assert corpo["erp"]["esito"] == "ok"

    # backref persistito + almeno un nuovo commit (update meta + ledger)
    env = DAL(dati_rw).read("fattura", bozza.id)
    assert env.meta.erp_id
    assert env.meta.erp_synced
    assert _commit(dati_rw) > prima

    # una Purchase Invoice creata a valle e riga ok nel ledger
    assert len(server.post_di("Purchase Invoice")) == 1
    righe = leggi_sync_erp(dati_rw)
    assert any(r["entity_id"] == bozza.id and r["esito"] == "ok" for r in righe)


def test_purchase_invoice_riporta_la_ritenuta(crea_client, dati_rw: Path) -> None:
    bozza = _bozza_da_seed(dati_rw, con_ritenuta=True)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.json()["erp"]["esito"] == "ok"

    payload = server.post_di("Purchase Invoice")[0]
    ritenuta = next(t for t in payload["taxes"] if t["description"] == "Ritenuta d'acconto")
    assert ritenuta["add_deduct_tax"] == "Deduct"
    assert ritenuta["tax_amount"] == bozza.dati["ritenuta_acconto"]


def test_sincronizzazione_idempotente(crea_client, dati_rw: Path) -> None:
    bozza = _bozza_da_seed(dati_rw, con_ritenuta=False)
    server = ErpServerFinto()
    erp = ErpClient(config=CONFIG, transport=server)
    client = crea_client(erp=erp)
    admin = accedi(client, "giovanna")

    client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert len(server.post_di("Purchase Invoice")) == 1

    # ri-sincronizzare lo stesso documento (ormai con erp_id) non crea doppioni
    env = DAL(dati_rw).read("fattura", bozza.id)
    esito = sincronizza(DAL(dati_rw), env, erp)
    assert esito["esito"] == "gia_sincronizzato"
    assert len(server.post_di("Purchase Invoice")) == 1


def test_errore_erp_non_blocca_validazione(crea_client, dati_rw: Path) -> None:
    bozza = _bozza_da_seed(dati_rw, con_ritenuta=False)
    server = ErpServerFinto(errore_su={"Purchase Invoice"})
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["stato"] == "validato"  # la validazione regge nonostante l'ERP giù
    assert corpo["erp"]["esito"] == "errore"

    env = DAL(dati_rw).read("fattura", bozza.id)
    assert env.stato == "validato"
    assert env.meta.erp_id is None  # nessun backref su fallimento

    dal = DAL(dati_rw)
    assert any(i.entity_id == bozza.id for i in dal.list_issues())  # issue automatica
    righe = leggi_sync_erp(dati_rw)
    assert any(r["entity_id"] == bozza.id and r["esito"] == "errore" for r in righe)


def test_validate_ddt_crea_purchase_receipt(crea_client, dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    seed = next(e for e in dal.list_all("ddt") if e.dati.get("fornitore_id"))
    bozza = dal.crea_progressivo("ddt", dict(seed.dati), stato="bozza")
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["erp"]["esito"] == "ok"
    assert len(server.post_di("Purchase Receipt")) == 1
    assert DAL(dati_rw).read("ddt", bozza.id).meta.erp_id


def test_fornitore_non_duplicato(crea_client, dati_rw: Path) -> None:
    """Due fatture dello stesso fornitore → un solo Supplier creato a valle."""
    dal = DAL(dati_rw)
    seed = next(e for e in dal.list_all("fattura") if e.dati.get("fornitore_id"))
    b1 = dal.crea_progressivo("fattura", dict(seed.dati), stato="bozza")
    b2 = dal.crea_progressivo("fattura", dict(seed.dati), stato="bozza")
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    client.post(f"/api/review/{b1.id}/validate", headers=admin)
    client.post(f"/api/review/{b2.id}/validate", headers=admin)
    assert len(server.post_di("Supplier")) == 1  # riusato per partita IVA
    assert len(server.post_di("Purchase Invoice")) == 2


def test_fattura_senza_cantiere_niente_cost_center(crea_client, dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    seed = next(e for e in dal.list_all("fattura") if e.dati.get("fornitore_id"))
    dati = dict(seed.dati, cantiere_id=None)
    bozza = dal.crea_progressivo("fattura", dati, stato="bozza")
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.json()["erp"]["esito"] == "ok"
    payload = server.post_di("Purchase Invoice")[0]
    assert all("cost_center" not in i for i in payload["items"])
    assert not server.post_di("Cost Center")  # nessun cantiere → nessun cost center


def test_fattura_senza_fornitore_apre_issue(crea_client, dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    seed = next(e for e in dal.list_all("fattura") if e.dati.get("fornitore_id"))
    dati = dict(seed.dati, fornitore_id=None)
    bozza = dal.crea_progressivo("fattura", dati, stato="bozza")
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.json()["stato"] == "validato"  # la validazione regge
    assert resp.json()["erp"]["esito"] == "errore"
    assert DAL(dati_rw).read("fattura", bozza.id).meta.erp_id is None
    assert any(i.entity_id == bozza.id for i in DAL(dati_rw).list_issues())


def test_ddt_sincronizzazione_idempotente(crea_client, dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    seed = next(e for e in dal.list_all("ddt") if e.dati.get("fornitore_id"))
    bozza = dal.crea_progressivo("ddt", dict(seed.dati), stato="bozza")
    server = ErpServerFinto()
    erp = ErpClient(config=CONFIG, transport=server)
    client = crea_client(erp=erp)
    admin = accedi(client, "giovanna")

    client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    env = DAL(dati_rw).read("ddt", bozza.id)
    esito = sincronizza(DAL(dati_rw), env, erp)
    assert esito["esito"] == "gia_sincronizzato"
    assert len(server.post_di("Purchase Receipt")) == 1


def test_tipo_non_sincronizzabile_nessun_effetto(crea_client, dati_rw: Path) -> None:
    """Validare un SAL (non nel ciclo passivo) non tocca l'ERP."""
    dal = DAL(dati_rw)
    seed = next(iter(dal.list_all("sal")))
    bozza = dal.crea_progressivo("sal", dict(seed.dati), stato="bozza")
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json()["erp"] is None  # SAL non è sincronizzabile
    assert server.chiamate == []


def test_erp_non_configurato_nessun_effetto(
    crea_client, dati_rw: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for v in ("ERP_BASE_URL", "ERP_API_KEY", "ERP_API_SECRET"):
        monkeypatch.delenv(v, raising=False)
    bozza = _bozza_da_seed(dati_rw, con_ritenuta=False)
    client = crea_client()  # erp=None -> ErpClient() inattivo
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.status_code == 200
    assert resp.json()["erp"] is None
    assert leggi_sync_erp(dati_rw) == []
