"""SAL → avanzamento del Project e Budget "Warn" opt-in (M36, B5+C1). Copre gli AC:

il SAL validato aggiorna ``percent_complete`` del Project del cantiere (PUT, non
contabile — il ciclo attivo resta un non-goal); un SAL senza cantiere apre una
issue parlante e la validazione regge; con ``ERP_BUDGET_WARN`` il carico
anagrafiche crea il Budget annuale "Warn" sul Cost Center (mai "Stop"), senza
l'opt-in non ne crea. Nessun ERPNext reale.
"""

from dataclasses import replace
from pathlib import Path

import pytest
from aiuti import accedi
from fake_erp import ErpServerFinto

from app.core.dal import DAL
from app.core.erp import ErpClient, ErpConfig, sincronizza

pytestmark = pytest.mark.erp

CONFIG = ErpConfig(
    base_url="http://erp.test", api_key="k", api_secret="s", company="Edile SpA"
)


def _bozza_sal(dati_rw: Path, **override) -> "object":
    dal = DAL(dati_rw)
    seed = next(e for e in dal.list_all("sal") if e.dati.get("cantiere_id"))
    return dal.crea_progressivo("sal", dict(seed.dati, **override), stato="bozza")


# ------------------------------------------------------------------ SAL (B5)


def test_validate_sal_aggiorna_l_avanzamento_del_project(crea_client, dati_rw: Path) -> None:
    bozza = _bozza_sal(dati_rw)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.status_code == 200, resp.text
    esito = resp.json()["erp"]
    assert esito["esito"] == "ok"
    assert esito["doctype"] == "Project"
    assert esito["percentuale"] == bozza.dati["percentuale_avanzamento"]

    nome_cantiere = DAL(dati_rw).read("cantiere", bozza.dati["cantiere_id"]).dati["nome"]
    progetto = next(p for p in server.documenti("Project") if p["name"] == nome_cantiere)
    assert progetto["percent_complete"] == bozza.dati["percentuale_avanzamento"]
    assert progetto["percent_complete_method"] == "Manual"
    # nessuna fattura attiva: il ciclo attivo resta fuori
    assert not server.post_di("Sales Invoice")
    assert DAL(dati_rw).read("sal", bozza.id).meta.erp_id == nome_cantiere


def test_sal_senza_cantiere_apre_issue_parlante(crea_client, dati_rw: Path) -> None:
    bozza = _bozza_sal(dati_rw, cantiere_id=None)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    resp = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert resp.json()["stato"] == "validato"  # la validazione regge
    assert resp.json()["erp"]["esito"] == "errore"
    assert "cantiere" in resp.json()["erp"]["errore"].lower()
    assert any(i.entity_id == bozza.id for i in DAL(dati_rw).list_issues())


def test_sal_sincronizzazione_idempotente(crea_client, dati_rw: Path) -> None:
    bozza = _bozza_sal(dati_rw)
    server = ErpServerFinto()
    erp = ErpClient(config=CONFIG, transport=server)
    client = crea_client(erp=erp)
    admin = accedi(client, "giovanna")

    client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    aggiornamenti = [c for c in server.chiamate if c["metodo"] == "PUT"]
    env = DAL(dati_rw).read("sal", bozza.id)
    esito = sincronizza(DAL(dati_rw), env, erp)
    assert esito["esito"] == "gia_sincronizzato"
    assert [c for c in server.chiamate if c["metodo"] == "PUT"] == aggiornamenti


def test_due_sal_dello_stesso_cantiere_aggiornano_lo_stesso_project(
    crea_client, dati_rw: Path
) -> None:
    """Ogni SAL è un envelope suo: il secondo porta la percentuale più avanti."""
    b1 = _bozza_sal(dati_rw, numero="SAL-90", percentuale_avanzamento=40.0)
    b2 = _bozza_sal(dati_rw, numero="SAL-91", percentuale_avanzamento=55.0)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    client.post(f"/api/review/{b1.id}/validate", headers=admin)
    client.post(f"/api/review/{b2.id}/validate", headers=admin)
    assert len(server.post_di("Project")) == 1  # un solo Project, riusato
    progetto = server.documenti("Project")[0]
    assert progetto["percent_complete"] == 55.0  # l'ultimo SAL vince


# ------------------------------------------------------------------ Budget (C1)


def test_carico_con_budget_warn_crea_i_budget(crea_client, dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    con_budget = [
        c for c in dal.list_all("cantiere") if c.dati.get("budget") and c.dati.get("data_inizio")
    ]
    server = ErpServerFinto()
    config = replace(CONFIG, budget_warn=True)
    client = crea_client(erp=ErpClient(config=config, transport=server))
    admin = accedi(client, "giovanna")

    r = client.post("/api/erp/carica-anagrafiche", headers=admin).json()
    assert r["per_tipo"]["cantiere"]["errori"] == 0

    budgets = server.post_di("Budget")
    assert len(budgets) == len(con_budget)
    primo = budgets[0]
    assert primo["action_if_annual_budget_exceeded"] == "Warn"  # mai "Stop"
    assert primo["budget_against"] == "Cost Center"
    importi = {b["accounts"][0]["budget_amount"] for b in budgets}
    assert importi == {c.dati["budget"] for c in con_budget}
    # l'anno fiscale viene dalla data di inizio del cantiere
    anni = {b["fiscal_year"] for b in budgets}
    assert anni == {str(c.dati["data_inizio"])[:4] for c in con_budget}


def test_carico_budget_idempotente(crea_client, dati_rw: Path) -> None:
    server = ErpServerFinto()
    config = replace(CONFIG, budget_warn=True)
    client = crea_client(erp=ErpClient(config=config, transport=server))
    admin = accedi(client, "giovanna")

    client.post("/api/erp/carica-anagrafiche", headers=admin)
    prima = len(server.post_di("Budget"))
    client.post("/api/erp/carica-anagrafiche", headers=admin)
    assert len(server.post_di("Budget")) == prima  # chiave: cost center + anno


def test_senza_opt_in_nessun_budget(crea_client, dati_rw: Path) -> None:
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")

    client.post("/api/erp/carica-anagrafiche", headers=admin)
    assert not server.post_di("Budget")  # il Budget a valle è una scelta, non un default