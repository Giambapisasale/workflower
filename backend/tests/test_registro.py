"""M10 — cruscotto multi-entità + registro consolidato di cantiere."""

from aiuti import accedi
from fastapi.testclient import TestClient


def test_registro_consolida_tutte_le_entita(client: TestClient) -> None:
    intestazioni = accedi(client, "giovanna")
    reg = client.get("/api/cantieri/CNT-001/registro", headers=intestazioni).json()

    assert reg["cantiere"]["nome"] == "Residenza Le Palme"
    t = reg["totali"]
    # fatture del cantiere: FT-2026-0001 (10162.60) + FT-2026-0004 (4880.00)
    assert t["n_fatture"] == 2
    assert round(t["speso_fatture"], 2) == 15042.60
    # manodopera dal rapportino RAP-2026-0001 (24 ore, 644 €)
    assert t["ore_totali"] == 24.0
    assert t["costo_manodopera"] == 644.0
    # avanzamento dall'ultimo SAL del cantiere
    assert t["avanzamento"] == 32.6
    # scostamento sul computo (previsto vs abbinato)
    assert t["scostamento"]["previsto"] == 237660.0
    assert t["scostamento"]["consuntivo_abbinato"] == 12330.0

    assert {f["id"] for f in reg["fatture"]} == {"FT-2026-0001", "FT-2026-0004"}
    assert len(reg["sal"]) == 1


def test_registro_cantiere_inesistente_404(client: TestClient) -> None:
    intestazioni = accedi(client, "giovanna")
    assert client.get("/api/cantieri/CNT-999/registro", headers=intestazioni).status_code == 404


def test_cruscotto_ha_le_attivita_multi_entita(client: TestClient) -> None:
    intestazioni = accedi(client, "giovanna")
    a = client.get("/api/dashboard/costs", headers=intestazioni).json()["attivita"]
    assert a["n_ddt"] == 2  # seed
    assert a["n_sal"] == 2
    assert a["ore_totali"] > 0
    assert a["costo_manodopera"] > 0


def test_registro_riservato_admin(client: TestClient) -> None:
    operatore = accedi(client, "salvo")
    assert client.get("/api/cantieri/CNT-001/registro", headers=operatore).status_code == 403
