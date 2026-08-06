"""Read-back stato pagamento + entità `pagamento` (Integrazione ERP, M27).

L'entità `pagamento` è puro dato (schema + riga ENTITY_TYPES + vista, nessun
workflow). Il read-back rilegge la Purchase Invoice a valle e crea/aggiorna un
`pagamento` per fattura (sola lettura ERP→WF), idempotente per `fattura_id`.
"""

from pathlib import Path

import pytest
from aiuti import accedi
from fake_erp import ErpServerFinto

from app.core.dal import DAL
from app.core.erp import ErpClient, ErpConfig
from app.core.views import query

pytestmark = pytest.mark.erp

CONFIG = ErpConfig(
    base_url="http://erp.test", api_key="k", api_secret="s", company="Edile SpA"
)


def _valida_una_fattura(client, dati_rw: Path, admin: dict[str, str]) -> str:
    dal = DAL(dati_rw)
    seed = next(
        e
        for e in dal.list_all("fattura")
        if e.dati.get("fornitore_id") and not e.dati.get("ritenuta_acconto")
    )
    bozza = dal.crea_progressivo("fattura", dict(seed.dati), stato="bozza")
    client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    return bozza.id


def test_pagamento_entita_puro_dato(dati_rw: Path) -> None:
    """Creabile via DAL e visibile nella vista v_pagamenti (zero codice nel runtime)."""
    dal = DAL(dati_rw)
    seed_ft = next(iter(dal.list_all("fattura")))
    pag = dal.crea_progressivo(
        "pagamento",
        {"fattura_id": seed_ft.id, "stato": "pagato", "importo_pagato": 100.0},
        stato="validato",
    )
    assert pag.id.startswith("PAG-")

    righe = query(dati_rw, "SELECT fattura_id, stato_pagamento, importo_pagato FROM v_pagamenti")
    assert {
        "fattura_id": seed_ft.id,
        "stato_pagamento": "pagato",
        "importo_pagato": 100.0,
    } in righe


def test_rileggi_pagamenti_crea_e_aggiorna(crea_client, dati_rw: Path) -> None:
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")
    ft_id = _valida_una_fattura(client, dati_rw, admin)
    pi_name = DAL(dati_rw).read("fattura", ft_id).meta.erp_id
    assert pi_name

    # ERP: fattura interamente pagata → nasce un pagamento "pagato"
    server.paga_fattura(pi_name, grand_total=1000.0, outstanding=0.0)
    r = client.post("/api/erp/rileggi-pagamenti", headers=admin).json()
    assert r["esito"] == "ok" and r["creati"] == 1
    pagamenti = [p for p in DAL(dati_rw).list_all("pagamento") if p.dati["fattura_id"] == ft_id]
    assert len(pagamenti) == 1 and pagamenti[0].dati["stato"] == "pagato"

    # ERP: ora parzialmente pagata → aggiorna lo stesso pagamento (nessun doppione)
    server.paga_fattura(pi_name, grand_total=1000.0, outstanding=400.0)
    r2 = client.post("/api/erp/rileggi-pagamenti", headers=admin).json()
    assert r2["aggiornati"] == 1 and r2["creati"] == 0
    pagamenti = [p for p in DAL(dati_rw).list_all("pagamento") if p.dati["fattura_id"] == ft_id]
    assert len(pagamenti) == 1
    assert pagamenti[0].dati["stato"] == "parziale"
    assert pagamenti[0].dati["importo_pagato"] == 600.0


def test_read_back_data_dal_payment_entry(crea_client, dati_rw: Path) -> None:
    """La data del pagamento vive sui Payment Entry: si prende l'ultima confermata (M31)."""
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")
    ft_id = _valida_una_fattura(client, dati_rw, admin)
    pi_name = DAL(dati_rw).read("fattura", ft_id).meta.erp_id

    server.paga_fattura(pi_name, grand_total=1000.0, outstanding=0.0)
    server.registra_pagamento(pi_name, "2026-04-01")  # acconto
    server.registra_pagamento(pi_name, "2026-05-10")  # saldo
    server.registra_pagamento(pi_name, "2026-06-30", docstatus=0)  # bozza: non conta

    client.post("/api/erp/rileggi-pagamenti", headers=admin)
    pag = next(p for p in DAL(dati_rw).list_all("pagamento") if p.dati["fattura_id"] == ft_id)
    assert pag.dati["data"] == "2026-05-10"


def test_read_back_senza_payment_entry_data_nulla(crea_client, dati_rw: Path) -> None:
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")
    ft_id = _valida_una_fattura(client, dati_rw, admin)
    pi_name = DAL(dati_rw).read("fattura", ft_id).meta.erp_id

    server.paga_fattura(pi_name, grand_total=1000.0, outstanding=400.0)
    client.post("/api/erp/rileggi-pagamenti", headers=admin)
    pag = next(p for p in DAL(dati_rw).list_all("pagamento") if p.dati["fattura_id"] == ft_id)
    assert pag.dati["stato"] == "parziale"
    assert pag.dati["data"] is None


def test_read_back_non_pagata_non_interroga_i_payment_entry(crea_client, dati_rw: Path) -> None:
    """Per le fatture non pagate la data non esiste: nessuna chiamata in più."""
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")
    _valida_una_fattura(client, dati_rw, admin)  # PI a valle, mai pagata

    client.post("/api/erp/rileggi-pagamenti", headers=admin)
    assert not any("Payment Entry" in c["url"] for c in server.chiamate)


def test_scadenza_e_residuo_fanno_il_giro_completo(crea_client, dati_rw: Path) -> None:
    """M32+M36: la scadenza estratta diventa due_date a valle e torna nello
    scadenziario di Workflower insieme al residuo (sola lettura)."""
    dal = DAL(dati_rw)
    seed = next(
        e
        for e in dal.list_all("fattura")
        if e.dati.get("fornitore_id") and not e.dati.get("ritenuta_acconto")
    )
    bozza = dal.crea_progressivo(
        "fattura", dict(seed.dati, scadenza_pagamento="2027-11-30"), stato="bozza"
    )
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")
    client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    pi_name = DAL(dati_rw).read("fattura", bozza.id).meta.erp_id

    server.paga_fattura(pi_name, grand_total=1000.0, outstanding=400.0)
    client.post("/api/erp/rileggi-pagamenti", headers=admin)

    pag = next(p for p in DAL(dati_rw).list_all("pagamento") if p.dati["fattura_id"] == bozza.id)
    assert pag.dati["scadenza"] == "2027-11-30"  # la due_date della PI, tornata indietro
    assert pag.dati["residuo"] == 400.0
    assert pag.dati["stato"] == "parziale"

    righe = query(
        dati_rw, "SELECT fattura_id, scadenza, residuo FROM v_pagamenti WHERE residuo > 0"
    )
    assert any(r["fattura_id"] == bozza.id for r in righe)


def test_rileggi_pagamenti_senza_fatture_sincronizzate(crea_client, dati_rw: Path) -> None:
    """Nessuna fattura con meta.erp_id → niente da rileggere (creati/aggiornati 0)."""
    client = crea_client(erp=ErpClient(config=CONFIG, transport=ErpServerFinto()))
    admin = accedi(client, "giovanna")
    r = client.post("/api/erp/rileggi-pagamenti", headers=admin).json()
    assert r == {"esito": "ok", "creati": 0, "aggiornati": 0, "errori": 0}


def test_rileggi_pagamenti_conta_errori_di_lettura(crea_client, dati_rw: Path) -> None:
    """Un errore nel leggere la PU a valle è contato, senza far cadere il ciclo."""
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")
    _valida_una_fattura(client, dati_rw, admin)  # sincronizza (PI creata)

    server.guasta("Purchase Invoice")  # ora la lettura fallisce
    r = client.post("/api/erp/rileggi-pagamenti", headers=admin).json()
    assert r["esito"] == "ok"
    assert r["errori"] >= 1
    assert r["creati"] == 0


def test_rileggi_pagamenti_erp_non_configurato(
    crea_client, dati_rw: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for v in ("ERP_BASE_URL", "ERP_API_KEY", "ERP_API_SECRET"):
        monkeypatch.delenv(v, raising=False)
    client = crea_client()
    admin = accedi(client, "giovanna")
    r = client.post("/api/erp/rileggi-pagamenti", headers=admin).json()
    assert r["esito"] == "erp_non_configurato"
