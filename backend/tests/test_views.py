"""Viste DuckDB sul seed: v_cantieri, v_fornitori, v_fatture, v_fatture_righe (AC M1)."""

from pathlib import Path

import pytest

from app.core.views import connect


def test_v_fatture_restituisce_il_seed(seeded_dir: Path) -> None:
    conn = connect(seeded_dir)
    rows = conn.execute("SELECT id, stato, totale FROM v_fatture ORDER BY id").fetchall()

    assert [r[0] for r in rows] == [f"FT-2026-000{i}" for i in range(1, 6)]
    assert all(r[1] == "validato" for r in rows)
    assert sum(r[2] for r in rows) == pytest.approx(32558.84)


def test_v_cantieri_e_v_fornitori(seeded_dir: Path) -> None:
    conn = connect(seeded_dir)
    assert conn.execute("SELECT count(*) FROM v_cantieri").fetchone()[0] == 3
    assert conn.execute("SELECT count(*) FROM v_fornitori").fetchone()[0] == 8

    nomi = {r[0] for r in conn.execute("SELECT nome FROM v_cantieri").fetchall()}
    assert "Residenza Le Palme" in nomi


def test_v_fatture_righe(seeded_dir: Path) -> None:
    conn = connect(seeded_dir)
    assert conn.execute("SELECT count(*) FROM v_fatture_righe").fetchone()[0] == 8

    res = conn.execute("SELECT * FROM v_fatture_righe LIMIT 1")
    colonne = {d[0] for d in res.description}
    assert {"fattura_id", "cantiere_id", "descrizione", "importo"} <= colonne


def test_ritenuta_acconto_nel_seed(seeded_dir: Path) -> None:
    conn = connect(seeded_dir)
    ritenuta = conn.execute(
        "SELECT ritenuta_acconto FROM v_fatture WHERE id = 'FT-2026-0004'"
    ).fetchone()[0]
    assert ritenuta == pytest.approx(800.0)

    senza = conn.execute(
        "SELECT count(*) FROM v_fatture WHERE ritenuta_acconto IS NULL"
    ).fetchone()[0]
    assert senza == 4


def test_aggregato_costi_per_cantiere(seeded_dir: Path) -> None:
    conn = connect(seeded_dir)
    costi = dict(
        conn.execute(
            "SELECT cantiere_id, round(sum(totale), 2) FROM v_fatture GROUP BY cantiere_id"
        ).fetchall()
    )
    assert costi["CNT-001"] == pytest.approx(15042.60)
    assert costi["CNT-002"] == pytest.approx(9171.44)
    assert costi["CNT-003"] == pytest.approx(8344.80)


def test_le_query_rileggono_i_file(seeded_dir: Path) -> None:
    """Le viste non hanno cache: una scrittura via DAL è subito visibile."""
    from app.core.dal import DAL
    from app.models.envelope import Envelope

    conn = connect(seeded_dir)
    prima = conn.execute("SELECT count(*) FROM v_fatture").fetchone()[0]

    DAL(seeded_dir).create(
        Envelope(
            id="FT-2026-0099",
            tipo="fattura",
            dati={
                "fornitore_id": "FRN-003",
                "cantiere_id": "CNT-003",
                "numero": "99/2026",
                "data": "2026-07-01",
                "imponibile": 50.0,
                "iva": 11.0,
                "totale": 61.0,
                "ritenuta_acconto": None,
                "righe": [{"descrizione": "Minuteria", "importo": 50.0}],
            },
        ),
        run_id="run-fresco",
    )

    dopo = conn.execute("SELECT count(*) FROM v_fatture").fetchone()[0]
    assert dopo == prima + 1
