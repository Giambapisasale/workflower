"""Entità dipendente: schema, seed, viste, riferimenti e costo manodopera dal profilo."""

import json
from pathlib import Path

import pytest
from aiuti import accedi
from fastapi.testclient import TestClient

from app.core.dal import DAL
from app.core.riferimenti import campi_riferimento
from app.core.views import connect


def _schema(seeded_dir: Path, tipo: str) -> dict:
    return json.loads((seeded_dir / "schemas" / f"{tipo}.schema.json").read_text("utf-8"))


def test_seed_dipendenti(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    voci = client.get("/api/entities/dipendente", headers=admin).json()["voci"]
    per_id = {v["id"]: v["dati"] for v in voci}
    assert len(per_id) == 4
    assert per_id["DIP-001"]["username"] == "salvo"
    assert per_id["DIP-001"]["tariffa_oraria"] == 28.0
    assert per_id["DIP-001"]["allocazioni"][0]["cantiere_id"] == "CNT-001"


def test_crea_dipendente_valido_e_invalido(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    ok = client.post(
        "/api/entities/dipendente",
        headers=admin,
        json={"dati": {"nome": "Rosa", "cognome": "Verdi", "tipo": "ufficio"}},
    )
    assert ok.status_code == 200, ok.text

    # tipo fuori enum → schema invalido
    ko = client.post(
        "/api/entities/dipendente",
        headers=admin,
        json={"dati": {"nome": "X", "cognome": "Y", "tipo": "capo"}},
    )
    assert ko.status_code == 422

    # cantiere_id malformato nell'allocazione → pattern invalido
    ko2 = client.post(
        "/api/entities/dipendente",
        headers=admin,
        json={
            "dati": {
                "nome": "X",
                "cognome": "Y",
                "tipo": "operaio",
                "allocazioni": [{"cantiere_id": "CNT-x", "da": "2026-01-01"}],
            }
        },
    )
    assert ko2.status_code == 422


def test_v_dipendenti_e_allocazioni(seeded_dir: Path) -> None:
    conn = connect(seeded_dir)
    assert conn.execute("SELECT count(*) FROM v_dipendenti").fetchone()[0] == 4
    tariffa = conn.execute(
        "SELECT tariffa_oraria FROM v_dipendenti WHERE id = 'DIP-001'"
    ).fetchone()[0]
    assert tariffa == pytest.approx(28.0)

    # tre operai con un'allocazione aperta ciascuno
    alloc = conn.execute(
        "SELECT dipendente_id, cantiere_id FROM v_allocazioni ORDER BY dipendente_id"
    ).fetchall()
    assert ("DIP-001", "CNT-001") in alloc
    assert len(alloc) == 3  # DIP-004 (ufficio) non ha allocazioni


def testcampi_riferimento(seeded_dir: Path) -> None:
    rif_rap = campi_riferimento(_schema(seeded_dir, "rapportino"))
    assert rif_rap.get("dipendente_id") == "dipendente"
    assert rif_rap.get("lavorazione_id") == "lavorazione"
    assert rif_rap.get("cantiere_id") == "cantiere"

    rif_dip = campi_riferimento(_schema(seeded_dir, "dipendente"))
    assert rif_dip.get("cantiere_id") == "cantiere"  # dedotto dall'array allocazioni


def test_costo_manodopera_dal_profilo(dati_rw: Path) -> None:
    """Il costo usa la tariffa del profilo (dipendente_id); in mancanza il
    costo_orario del documento; infine 0."""
    dal = DAL(dati_rw)
    env = dal.crea_progressivo(
        "rapportino",
        {
            "cantiere_id": "CNT-001",
            "data": "2026-07-20",
            "righe": [
                {"dipendente_id": "DIP-001", "ore": 8},  # tariffa profilo 28 → 224
                {"nominativo": "Squadra esterna", "ore": 4, "costo_orario": 25},  # → 100
                {"nominativo": "Senza tariffa", "ore": 5},  # → 0
            ],
        },
        stato="validato",
    )
    conn = connect(dati_rw)
    righe = conn.execute(
        "SELECT ore, tariffa_applicata, costo, lavoratore "
        "FROM v_rapportini_righe WHERE rapportino_id = ? ORDER BY costo DESC",
        [env.id],
    ).fetchall()
    costi = sorted(r[2] for r in righe)
    assert costi == pytest.approx([0.0, 100.0, 224.0])
    # la riga col dipendente: tariffa dal profilo (28) e nome dal profilo
    per_costo = {r[2]: r for r in righe}
    assert per_costo[224.0][1] == pytest.approx(28.0)  # tariffa_applicata
    nomi = {r[3] for r in righe}
    assert "Salvo Torrisi" in nomi
    assert "Squadra esterna" in nomi
