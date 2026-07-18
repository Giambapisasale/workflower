"""RBAC (AC M6): ruoli e permessi granulari per cantiere (§3.9).

Un capocantiere vede solo i propri documenti e non raggiunge nulla dell'ufficio;
non può nemmeno caricare su un cantiere che non è suo. L'admin vede tutto.
"""

from pathlib import Path

from aiuti import accedi
from fastapi.testclient import TestClient


def test_login_espone_solo_i_cantieri_assegnati(client: TestClient) -> None:
    salvo = client.post("/api/auth/login", json={"username": "salvo", "pin": "1111"}).json()
    assert [c["id"] for c in salvo["utente"]["cantieri"]] == ["CNT-001"]
    giovanna = client.post("/api/auth/login", json={"username": "giovanna", "pin": "9999"}).json()
    assert len(giovanna["utente"]["cantieri"]) == 3  # l'admin li vede tutti


def test_operatore_vede_solo_i_propri_documenti(client: TestClient, fixtures_dir: Path) -> None:
    salvo = accedi(client, "salvo")
    pdf = (fixtures_dir / "fattura-calcestruzzi-etna.pdf").read_bytes()
    corpo = client.post(
        "/api/documents",
        headers=salvo,
        files={"file": ("f.pdf", pdf, "application/pdf")},
    ).json()

    giuseppe = accedi(client, "giuseppe")
    assert client.get("/api/documents", headers=giuseppe).json()["documenti"] == []
    assert client.get(f"/api/documents/{corpo['doc_id']}", headers=giuseppe).status_code == 404


def test_operatore_non_carica_su_cantiere_altrui(client: TestClient) -> None:
    salvo = accedi(client, "salvo")  # assegnato solo a CNT-001
    risposta = client.post(
        "/api/documents",
        headers=salvo,
        data={"cantiere_id": "CNT-002"},
        files={"file": ("f.pdf", b"%PDF-1.4 finto", "application/pdf")},
    )
    assert risposta.status_code == 403


def test_operatore_403_su_azioni_admin_con_corpo(client: TestClient) -> None:
    op = accedi(client, "salvo")
    casi = [
        ("post", "/api/review/FT-2026-0001/feedback", {"campo": "totale", "nota": "x"}),
        ("post", "/api/workflows/carica-fattura/improve", {"run_id": "run-x"}),
        ("post", "/api/patches/PATCH-0001/approve", {}),
        ("post", "/api/patches/PATCH-0001/reject", {}),
        ("post", "/api/issues/ISS-0001/close", {}),
    ]
    for metodo, percorso, corpo in casi:
        risposta = getattr(client, metodo)(percorso, json=corpo, headers=op)
        assert risposta.status_code == 403, f"{metodo} {percorso} → {risposta.status_code}"
