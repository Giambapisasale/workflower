"""Login JWT e RBAC minimale (piano §3.4): ruolo + cantieri nel token."""

from aiuti import PIN, accedi
from fastapi.testclient import TestClient


def test_login_operatore(client: TestClient) -> None:
    risposta = client.post("/api/auth/login", json={"username": "salvo", "pin": PIN["salvo"]})
    assert risposta.status_code == 200
    corpo = risposta.json()
    assert corpo["token"]
    assert corpo["utente"]["nome"] == "Salvo Torrisi"
    assert corpo["utente"]["ruolo"] == "operatore"
    assert corpo["utente"]["cantieri"] == [{"id": "CNT-001", "nome": "Residenza Le Palme"}]


def test_login_admin_vede_tutti_i_cantieri(client: TestClient) -> None:
    risposta = client.post(
        "/api/auth/login", json={"username": "giovanna", "pin": PIN["giovanna"]}
    )
    assert risposta.status_code == 200
    corpo = risposta.json()
    assert corpo["utente"]["ruolo"] == "admin"
    assert {c["id"] for c in corpo["utente"]["cantieri"]} == {"CNT-001", "CNT-002", "CNT-003"}


def test_login_pin_sbagliato(client: TestClient) -> None:
    risposta = client.post("/api/auth/login", json={"username": "salvo", "pin": "0000"})
    assert risposta.status_code == 401


def test_endpoint_protetti_senza_token(client: TestClient) -> None:
    assert client.get("/api/documents").status_code == 401
    assert client.post("/api/ask", json={"question": "quanto?"}).status_code == 401


def test_token_manomesso(client: TestClient) -> None:
    risposta = client.get(
        "/api/documents", headers={"Authorization": "Bearer non-un-token"}
    )
    assert risposta.status_code == 401


def test_operatore_non_chiama_modalita_admin(client: TestClient) -> None:
    intestazioni = accedi(client, "salvo")
    risposta = client.post(
        "/api/ask", json={"question": "totale?", "mode": "admin"}, headers=intestazioni
    )
    assert risposta.status_code == 403
