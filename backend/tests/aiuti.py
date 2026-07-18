"""Scorciatoie condivise dai test API."""

from fastapi.testclient import TestClient

# PIN demo del seed (app/seed_data.py)
PIN = {"salvo": "1111", "giuseppe": "2222", "marco": "3333", "giovanna": "9999"}


def accedi(client: TestClient, username: str = "salvo") -> dict[str, str]:
    risposta = client.post(
        "/api/auth/login", json={"username": username, "pin": PIN[username]}
    )
    assert risposta.status_code == 200, risposta.text
    return {"Authorization": f"Bearer {risposta.json()['token']}"}


def stringhe_di(valore: object) -> list[str]:
    """Tutte le stringhe annidate in una risposta JSON (per l'audit del lessico)."""
    if isinstance(valore, str):
        return [valore]
    if isinstance(valore, dict):
        return [s for v in valore.values() for s in stringhe_di(v)]
    if isinstance(valore, list):
        return [s for v in valore for s in stringhe_di(v)]
    return []
