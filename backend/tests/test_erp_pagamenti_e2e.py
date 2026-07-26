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


def test_rileggi_pagamenti_erp_non_configurato(
    crea_client, dati_rw: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for v in ("ERP_BASE_URL", "ERP_API_KEY", "ERP_API_SECRET"):
        monkeypatch.delenv(v, raising=False)
    client = crea_client()
    admin = accedi(client, "giovanna")
    r = client.post("/api/erp/rileggi-pagamenti", headers=admin).json()
    assert r["esito"] == "erp_non_configurato"
