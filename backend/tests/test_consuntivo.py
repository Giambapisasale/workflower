"""Consuntivo ore da interfaccia operaio: contesto, invio → bozza in revisione, guardie."""

from aiuti import accedi
from fastapi.testclient import TestClient


def test_contesto_operaio(client: TestClient) -> None:
    op = accedi(client, "salvo")
    r = client.get("/api/consuntivo/contesto?data=2026-07-24", headers=op)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["dipendente"]["id"] == "DIP-001"
    assert {c["id"] for c in corpo["cantieri"]} == {"CNT-001"}
    assert len(corpo["attivita_disponibili"]) >= 1  # catalogo lavorazioni


def test_contesto_fuori_periodo(client: TestClient) -> None:
    op = accedi(client, "salvo")  # allocato da 2026-01-08
    r = client.get("/api/consuntivo/contesto?data=2026-01-01", headers=op)
    assert r.status_code == 200
    assert r.json()["cantieri"] == []  # non ancora allocato


def test_invia_crea_bozza_in_revisione(client: TestClient) -> None:
    op = accedi(client, "salvo")
    r = client.post(
        "/api/consuntivo",
        headers=op,
        json={
            "cantiere_id": "CNT-001",
            "data": "2026-07-24",
            "ore": 8,
            "mansione": "muratore",
            "attivita": [
                {"lavorazione_id": "LAV-001"},
                {"descrizione": "posa pozzetti fila nord"},
            ],
        },
    )
    assert r.status_code == 200, r.text
    rap_id = r.json()["id"]
    assert rap_id.startswith("RAP-2026-")

    # entra da sé nella coda di revisione dell'ufficio (bozza)
    admin = accedi(client, "giovanna")
    coda = client.get("/api/review", headers=admin).json()
    ids = {v["id"]: v for v in coda["da_rivedere"]}
    assert rap_id in ids
    assert ids[rap_id]["tipo"] == "rapportino"

    dett = client.get(f"/api/review/{rap_id}", headers=admin).json()
    riga = dett["entita"]["dati"]["righe"][0]
    assert riga["dipendente_id"] == "DIP-001"
    assert riga["nominativo"] is None
    assert riga["costo_orario"] is None
    assert {a.get("lavorazione_id") for a in riga["attivita"]} == {"LAV-001", None}


def test_invia_cantiere_non_allocato(client: TestClient) -> None:
    op = accedi(client, "salvo")  # allocato a CNT-001
    r = client.post(
        "/api/consuntivo",
        headers=op,
        json={"cantiere_id": "CNT-002", "data": "2026-07-24", "ore": 8},
    )
    assert r.status_code == 403


def test_invia_ore_non_positive(client: TestClient) -> None:
    op = accedi(client, "salvo")
    r = client.post(
        "/api/consuntivo",
        headers=op,
        json={"cantiere_id": "CNT-001", "data": "2026-07-24", "ore": 0},
    )
    assert r.status_code == 400


def test_contesto_richiede_auth(client: TestClient) -> None:
    assert client.get("/api/consuntivo/contesto?data=2026-07-24").status_code == 401
