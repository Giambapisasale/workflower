"""Gestione mezzi: costi dalle fatture, costo pieno/TCO, scadenze e manutenzioni."""

import json
from pathlib import Path

import pytest
from aiuti import accedi
from fastapi.testclient import TestClient

from app.api.entities import _campi_riferimento
from app.core.views import connect


def _schema(seeded_dir: Path, tipo: str) -> dict:
    return json.loads((seeded_dir / "schemas" / f"{tipo}.schema.json").read_text("utf-8"))


# ------------------------------------------------------------------ schema/riferimenti


def test_campi_riferimento_mezzi(seeded_dir: Path) -> None:
    assert _campi_riferimento(_schema(seeded_dir, "fattura")).get("mezzo_id") == "mezzo"
    rif_mezzo = _campi_riferimento(_schema(seeded_dir, "mezzo"))
    assert rif_mezzo.get("fornitore_noleggio_id") == "fornitore"
    rif_scad = _campi_riferimento(_schema(seeded_dir, "scadenza"))
    assert rif_scad.get("mezzo_id") == "mezzo"
    assert rif_scad.get("cantiere_id") == "cantiere"
    rif_man = _campi_riferimento(_schema(seeded_dir, "manutenzione"))
    assert rif_man.get("mezzo_id") == "mezzo"
    assert rif_man.get("fornitore_id") == "fornitore"


def test_crea_manutenzione_valida_e_invalida(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    ok = client.post(
        "/api/entities/manutenzione",
        headers=admin,
        json={"dati": {"mezzo_id": "MEZ-001", "data": "2026-07-01", "tipo": "tagliando"}},
    )
    assert ok.status_code == 200, ok.text
    ko = client.post(
        "/api/entities/manutenzione",
        headers=admin,
        json={"dati": {"mezzo_id": "MEZ-001", "data": "2026-07-01", "tipo": "esplosione"}},
    )
    assert ko.status_code == 422


# ------------------------------------------------------------------ viste


def test_v_mezzi_costi(seeded_dir: Path) -> None:
    conn = connect(seeded_dir)
    # la riga di nolo (FT-2026-0003) è taggata a MEZ-003 come noleggio
    righe = conn.execute(
        "SELECT mezzo_id, cantiere_id, tipo_costo, costo FROM v_mezzi_costi"
    ).fetchall()
    per_mezzo = {r[0]: r for r in righe}
    assert per_mezzo["MEZ-003"][1] == "CNT-003"
    assert per_mezzo["MEZ-003"][2] == "noleggio"
    assert per_mezzo["MEZ-003"][3] == pytest.approx(6840.0)


def test_v_mezzi_tco(seeded_dir: Path) -> None:
    conn = connect(seeded_dir)
    tco = {
        r[0]: r
        for r in conn.execute(
            "SELECT mezzo_id, costo_orario_pieno, costo_fatture, costo_manutenzioni, "
            "costo_documentale FROM v_mezzi_tco"
        ).fetchall()
    }
    # MEZ-001 proprio: (145000/8 + 7200) / 1400 = 25325/1400
    assert tco["MEZ-001"][1] == pytest.approx(25325.0 / 1400.0)
    assert tco["MEZ-001"][3] == pytest.approx(1730.0)  # 1250 + 480 manutenzioni
    # MEZ-003 noleggio: nessun costo orario pieno (no ammortamento/ore), costo dai canoni
    assert tco["MEZ-003"][1] is None
    assert tco["MEZ-003"][2] == pytest.approx(6840.0)


def test_v_manutenzioni_e_scadenze_mezzo(seeded_dir: Path) -> None:
    conn = connect(seeded_dir)
    assert conn.execute("SELECT COUNT(*) FROM v_manutenzioni").fetchone()[0] == 2
    scad_mezzo = conn.execute(
        "SELECT COUNT(*) FROM v_scadenze WHERE mezzo_id IS NOT NULL"
    ).fetchone()[0]
    assert scad_mezzo == 2


# ------------------------------------------------------------------ guardia delete


def test_delete_mezzo_referenziato(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    # MEZ-003 è taggato su una riga fattura → non cancellabile (guardia annidata)
    assert client.delete("/api/entities/mezzo/MEZ-003", headers=admin).status_code == 409
    # MEZ-001 è referenziato da scadenza e manutenzione → non cancellabile
    assert client.delete("/api/entities/mezzo/MEZ-001", headers=admin).status_code == 409


# ------------------------------------------------------------------ consumatori


def test_registro_cantiere_costo_mezzi(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    r3 = client.get("/api/cantieri/CNT-003/registro", headers=admin).json()
    assert r3["totali"]["costo_mezzi"] == pytest.approx(6840.0)
    r1 = client.get("/api/cantieri/CNT-001/registro", headers=admin).json()
    assert r1["totali"]["costo_mezzi"] == pytest.approx(0.0)


def test_dashboard_costo_mezzi_e_scadenze(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    corpo = client.get("/api/dashboard/costs", headers=admin).json()
    assert corpo["attivita"]["costo_mezzi"] == pytest.approx(6840.0)
    assert isinstance(corpo["scadenze"], list)


def test_scadenzario_classifica_scadute(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    # una scadenza nel lontano passato è sempre "scaduta" (giorni < 0), indipendente
    # dalla data reale di esecuzione del test
    creata = client.post(
        "/api/entities/scadenza",
        headers=admin,
        json={
            "dati": {
                "descrizione": "Vecchio adempimento",
                "data_scadenza": "2000-01-01",
                "cantiere_id": "CNT-001",
                "stato": "aperta",
            }
        },
    )
    assert creata.status_code == 200, creata.text
    scadenze = client.get("/api/dashboard/costs", headers=admin).json()["scadenze"]
    vecchia = next(s for s in scadenze if s["descrizione"] == "Vecchio adempimento")
    assert vecchia["giorni"] < 0
