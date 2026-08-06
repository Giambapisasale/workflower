"""Rapportini → Timesheet alla validazione (Fascia B4, M35). Copre gli AC:

il rapportino validato diventa un Timesheet per dipendente collegato (time log con
ore, attività, project), con backref e ledger; le righe di terzi/squadre si contano
e si dichiarano; un rapportino di soli terzi resta "saltato" con motivo — un invito
a collegare, non un errore (niente issue) — e non fa scattare l'early-abort del
re-sync. L'Employee nasce coi valori di cortesia dichiarati. Nessun ERPNext reale.
"""

from pathlib import Path

import pytest
from aiuti import accedi
from fake_erp import ErpServerFinto

from app.core.dal import DAL
from app.core.dataset import leggi_sync_erp
from app.core.erp import ErpClient, ErpConfig, sincronizza

pytestmark = pytest.mark.erp

CONFIG = ErpConfig(
    base_url="http://erp.test", api_key="k", api_secret="s", company="Edile SpA"
)


def _bozza_rapportino(dati_rw: Path, *, righe=None) -> "object":
    dal = DAL(dati_rw)
    seed = next(
        e
        for e in dal.list_all("rapportino")
        if any(r.get("dipendente_id") for r in e.dati["righe"])
    )
    dati = dict(seed.dati)
    if righe is not None:
        dati["righe"] = righe
    return dal.crea_progressivo("rapportino", dati, stato="bozza")


def test_validate_rapportino_crea_timesheet(crea_client, dati_rw: Path) -> None:
    bozza = _bozza_rapportino(dati_rw)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.status_code == 200, resp.text
    esito = resp.json()["erp"]
    assert esito["esito"] == "ok"
    assert esito["doctype"] == "Timesheet"

    collegate = [r for r in bozza.dati["righe"] if r.get("dipendente_id")]
    non_collegate = [r for r in bozza.dati["righe"] if not r.get("dipendente_id")]
    assert esito["righe_saltate"] == len(non_collegate)  # dichiarate, mai zero silenzioso

    timesheets = server.post_di("Timesheet")
    assert len(timesheets) == len({r["dipendente_id"] for r in collegate})
    ore_a_valle = sum(log["hours"] for ts in timesheets for log in ts["time_logs"])
    assert ore_a_valle == sum(r["ore"] for r in collegate)

    # il backref elenca i Timesheet creati; il ledger ha la riga ok
    env = DAL(dati_rw).read("rapportino", bozza.id)
    assert env.meta.erp_id
    assert any(
        x["entity_id"] == bozza.id and x["esito"] == "ok" for x in leggi_sync_erp(dati_rw)
    )


def test_employee_nasce_coi_valori_di_cortesia(crea_client, dati_rw: Path) -> None:
    bozza = _bozza_rapportino(dati_rw)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    dipendente_id = next(r["dipendente_id"] for r in bozza.dati["righe"] if r.get("dipendente_id"))
    dipendente = DAL(dati_rw).read("dipendente", dipendente_id).dati

    employee = server.post_di("Employee")[0]
    assert employee["employee_name"] == f"{dipendente['nome']} {dipendente['cognome']}"
    assert employee["gender"] == "Prefer not to say"  # segnaposto dichiarato
    assert employee["date_of_birth"] == "1900-01-01"
    # la tariffa oraria gestionale resta in Workflower
    assert "tariffa" not in str(employee)


def test_employee_non_duplicato_su_due_rapportini(crea_client, dati_rw: Path) -> None:
    b1 = _bozza_rapportino(dati_rw)
    b2 = _bozza_rapportino(dati_rw)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    client.post(f"/api/review/{b1.id}/validate", headers=admin)
    client.post(f"/api/review/{b2.id}/validate", headers=admin)
    assert len(server.post_di("Employee")) == 1  # riusato per nome+company
    assert len(server.post_di("Timesheet")) == 2


def test_rapportino_di_soli_terzi_resta_saltato(crea_client, dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    seed = next(iter(dal.list_all("rapportino")))
    righe = [dict(r, dipendente_id=None) for r in seed.dati["righe"]]
    bozza = _bozza_rapportino(dati_rw, righe=righe)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.status_code == 200
    esito = resp.json()["erp"]
    assert esito["esito"] == "saltato"
    assert "collega" in esito["motivo"]

    assert not server.post_di("Timesheet")
    env = DAL(dati_rw).read("rapportino", bozza.id)
    assert env.stato == "validato"  # la validazione regge
    assert env.meta.erp_id is None  # resta fra i "rimasti indietro": un invito
    # ledger: riga "saltato" col motivo; nessuna issue (non è un errore)
    riga = next(x for x in leggi_sync_erp(dati_rw) if x["entity_id"] == bozza.id)
    assert riga["esito"] == "saltato"
    assert not any(i.entity_id == bozza.id for i in DAL(dati_rw).list_issues())


def test_rapportino_saltato_non_interrompe_il_re_sync(crea_client, dati_rw: Path) -> None:
    """I saltati non contano come fallimenti: l'early-abort è per l'ERP giù."""
    dal = DAL(dati_rw)
    seed = next(iter(dal.list_all("rapportino")))
    for _ in range(6):  # più del MAX_ERRORI_CONSECUTIVI (5)
        righe = [dict(r, dipendente_id=None) for r in seed.dati["righe"]]
        dal.crea_progressivo("rapportino", dict(seed.dati, righe=righe), stato="validato")
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    r = client.post("/api/erp/risincronizza", headers=admin).json()
    assert r["interrotto"] is False
    assert r["saltate"] >= 6
    assert r["esito"] == "ok"


def test_rapportino_sincronizzazione_idempotente(crea_client, dati_rw: Path) -> None:
    bozza = _bozza_rapportino(dati_rw)
    server = ErpServerFinto()
    erp = ErpClient(config=CONFIG, transport=server)
    client = crea_client(erp=erp)
    admin = accedi(client, "giovanna")

    client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    prima = len(server.post_di("Timesheet"))
    env = DAL(dati_rw).read("rapportino", bozza.id)
    esito = sincronizza(DAL(dati_rw), env, erp)
    assert esito["esito"] == "gia_sincronizzato"
    assert len(server.post_di("Timesheet")) == prima


def test_rapportino_senza_company_apre_issue(crea_client, dati_rw: Path) -> None:
    """Senza ERP_COMPANY l'Employee non è creabile: errore parlante, validazione salva."""
    config = ErpConfig(base_url="http://erp.test", api_key="k", api_secret="s")
    bozza = _bozza_rapportino(dati_rw)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=config, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.json()["stato"] == "validato"
    assert resp.json()["erp"]["esito"] == "errore"
    assert "ERP_COMPANY" in resp.json()["erp"]["errore"]
    assert any(i.entity_id == bozza.id for i in DAL(dati_rw).list_issues())