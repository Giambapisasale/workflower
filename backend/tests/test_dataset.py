"""Log & Dataset (AC M6): conteggi, costo per documento, export, fingerprint query."""

from pathlib import Path

from aiuti import accedi
from fake_ask import FakeCompleterInterroga
from fastapi.testclient import TestClient

from app.core.dataset import fingerprint


def _carica(client: TestClient, headers: dict[str, str], percorso: Path) -> None:
    client.post(
        "/api/documents",
        headers=headers,
        files={"file": (percorso.name, percorso.read_bytes(), "application/pdf")},
    )


def test_fingerprint_collassa_i_valori() -> None:
    a = fingerprint("SELECT * FROM v_fatture WHERE totale > 1000")
    b = fingerprint("SELECT * FROM v_fatture WHERE totale > 2500.50")
    assert a == b and "?" in a


def test_stats_dopo_un_run(client: TestClient, fixtures_dir: Path) -> None:
    salvo = accedi(client, "salvo")
    _carica(client, salvo, fixtures_dir / "fattura-calcestruzzi-etna.pdf")

    admin = accedi(client, "giovanna")
    s = client.get("/api/dataset/stats", headers=admin).json()
    assert s["run"]["totale"] >= 1 and s["run"]["ok"] >= 1
    assert s["tool_call"] > 0 and s["llm_call"] > 0
    assert s["documenti"] >= 1
    assert s["costo_totale_usd"] > 0
    assert s["costo_per_documento_usd"] > 0


def test_queries_raggruppate_per_fingerprint(crea_client) -> None:
    client = crea_client(FakeCompleterInterroga("SELECT COUNT(*) AS n FROM v_fatture"))
    admin = accedi(client, "giovanna")
    for domanda in ("quante fatture?", "numero totale di fatture"):
        risposta = client.post(
            "/api/ask", json={"question": domanda, "mode": "admin"}, headers=admin
        )
        assert risposta.status_code == 200
    gruppi = client.get("/api/dataset/queries", headers=admin).json()["gruppi"]
    assert len(gruppi) == 1 and gruppi[0]["conteggio"] == 2


def test_export_toolcalls(client: TestClient, fixtures_dir: Path) -> None:
    salvo = accedi(client, "salvo")
    _carica(client, salvo, fixtures_dir / "fattura-calcestruzzi-etna.pdf")

    admin = accedi(client, "giovanna")
    risposta = client.get("/api/dataset/export", headers=admin)
    assert risposta.status_code == 200
    assert "ndjson" in risposta.headers["content-type"]
    assert '"tool_call"' in risposta.text  # righe di tool call reali del run
