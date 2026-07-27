"""Osservabilità e re-sync ERP (Integrazione ERP, M28). Copre gli AC:

le fatture/DDT non sincronizzati sono elencabili (``GET /erp/stato``) e ri-inviabili
(``POST /erp/risincronizza`` e ``/erp/risincronizza/{id}``); un ERP giù non blocca
Workflower e il batch si ferma dopo N errori consecutivi invece di martellare.
Nessun ERPNext reale: trasporto finto.
"""

from pathlib import Path

import pytest
from aiuti import accedi
from fake_erp import ErpServerFinto

from app.core.dal import DAL
from app.core.erp import ErpClient, ErpConfig

pytestmark = pytest.mark.erp

CONFIG = ErpConfig(
    base_url="http://erp.test",
    api_key="k",
    api_secret="s",
    company="Edile SpA",
    item_ddt="MATERIALE-GENERICO",
)


def _fattura_validata(dati_rw: Path) -> "object":
    """Una fattura già validata ma NON ancora sincronizzata (meta.erp_id assente)."""
    dal = DAL(dati_rw)
    seed = next(e for e in dal.list_all("fattura") if e.dati.get("fornitore_id"))
    return dal.crea_progressivo("fattura", dict(seed.dati), stato="validato")


def test_stato_elenca_le_da_sincronizzare(crea_client, dati_rw: Path) -> None:
    ft = _fattura_validata(dati_rw)
    client = crea_client(erp=ErpClient(config=CONFIG, transport=ErpServerFinto()))
    admin = accedi(client, "giovanna")

    stato = client.get("/api/erp/stato", headers=admin).json()
    assert stato["erp_attivo"] is True
    assert ft.id in {d["id"] for d in stato["da_sincronizzare"]}
    assert stato["per_tipo"]["fattura"]["da_sincronizzare"] >= 1


def test_risincronizza_recupera_le_mancanti(crea_client, dati_rw: Path) -> None:
    ft = _fattura_validata(dati_rw)
    client = crea_client(erp=ErpClient(config=CONFIG, transport=ErpServerFinto()))
    admin = accedi(client, "giovanna")

    r = client.post("/api/erp/risincronizza", headers=admin).json()
    assert r["esito"] == "ok" and r["ok"] >= 1
    assert DAL(dati_rw).read("fattura", ft.id).meta.erp_id  # ora sincronizzata

    stato = client.get("/api/erp/stato", headers=admin).json()
    assert ft.id not in {d["id"] for d in stato["da_sincronizzare"]}


def test_risincronizza_singola(crea_client, dati_rw: Path) -> None:
    ft = _fattura_validata(dati_rw)
    client = crea_client(erp=ErpClient(config=CONFIG, transport=ErpServerFinto()))
    admin = accedi(client, "giovanna")

    r = client.post(f"/api/erp/risincronizza/{ft.id}", headers=admin).json()
    assert r["esito"] == "ok"
    assert DAL(dati_rw).read("fattura", ft.id).meta.erp_id


def test_risincronizza_si_ferma_se_erp_giu(crea_client, dati_rw: Path) -> None:
    for _ in range(6):
        _fattura_validata(dati_rw)
    server = ErpServerFinto(errore_su={"Purchase Invoice"})
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    r = client.post("/api/erp/risincronizza", headers=admin).json()
    assert r["interrotto"] is True
    assert r["errori"] >= 5  # si ferma dopo i fallimenti consecutivi, non martella


def test_risincronizza_singola_inesistente_404(crea_client, dati_rw: Path) -> None:
    client = crea_client(erp=ErpClient(config=CONFIG, transport=ErpServerFinto()))
    admin = accedi(client, "giovanna")
    resp = client.post("/api/erp/risincronizza/FT-2099-9999", headers=admin)
    assert resp.status_code == 404


def test_risincronizza_singola_tipo_non_sincronizzabile(crea_client, dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    sal = dal.crea_progressivo("sal", dict(next(iter(dal.list_all("sal"))).dati), stato="validato")
    client = crea_client(erp=ErpClient(config=CONFIG, transport=ErpServerFinto()))
    admin = accedi(client, "giovanna")
    r = client.post(f"/api/erp/risincronizza/{sal.id}", headers=admin).json()
    assert r["esito"] == "saltato"


def test_stato_e_risincronizza_erp_non_configurato(crea_client, dati_rw: Path, monkeypatch) -> None:
    for v in ("ERP_BASE_URL", "ERP_API_KEY", "ERP_API_SECRET"):
        monkeypatch.delenv(v, raising=False)
    client = crea_client()  # ErpClient() inattivo
    admin = accedi(client, "giovanna")
    assert client.get("/api/erp/stato", headers=admin).json()["erp_attivo"] is False
    r = client.post("/api/erp/risincronizza", headers=admin).json()
    assert r["esito"] == "erp_non_configurato"


def test_recupero_dopo_ripristino_erp(crea_client, dati_rw: Path) -> None:
    """ERP giù alla validazione → recupero via re-sync quando l'ERP torna su."""
    server = ErpServerFinto(errore_su={"Purchase Invoice"})
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    dal = DAL(dati_rw)
    seed = next(e for e in dal.list_all("fattura") if e.dati.get("fornitore_id"))
    bozza = dal.crea_progressivo("fattura", dict(seed.dati), stato="bozza")

    # 1. validazione con ERP giù: resta validato ma non sincronizzato + issue
    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.json()["erp"]["esito"] == "errore"
    assert DAL(dati_rw).read("fattura", bozza.id).meta.erp_id is None
    stato = client.get("/api/erp/stato", headers=admin).json()
    assert bozza.id in {d["id"] for d in stato["da_sincronizzare"]}

    # 2. l'ERP torna su → il re-sync recupera
    server.ripristina()
    r = client.post(f"/api/erp/risincronizza/{bozza.id}", headers=admin).json()
    assert r["esito"] == "ok"
    assert DAL(dati_rw).read("fattura", bozza.id).meta.erp_id
