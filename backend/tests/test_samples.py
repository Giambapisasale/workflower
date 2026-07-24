"""Documenti di esempio scaricabili: catalogo + download confinato."""

from collections.abc import Callable

from aiuti import accedi
from fastapi.testclient import TestClient

from app.api.samples import SAMPLES_DIR

TIPI = {"fattura", "ddt", "sal", "rapportino"}


def test_pdf_presenti_su_disco() -> None:
    presenti = {p.name for p in SAMPLES_DIR.glob("*.pdf")}
    assert len(presenti) >= 4  # almeno un esempio per tipo


def test_elenco_esempi(client: TestClient) -> None:
    r = client.get("/api/samples", headers=accedi(client, "salvo"))  # operatore
    assert r.status_code == 200
    esempi = r.json()["esempi"]
    assert len(esempi) >= 4
    assert {e["tipo"] for e in esempi} >= TIPI  # tutti i tipi coperti
    for e in esempi:
        assert e["file"].endswith(".pdf")
        assert e["titolo"]


def test_scarica_esempio_pdf(client: TestClient) -> None:
    op = accedi(client, "salvo")
    file = client.get("/api/samples", headers=op).json()["esempi"][0]["file"]
    r = client.get(f"/api/samples/{file}", headers=op)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_download_confinato(client: TestClient) -> None:
    op = accedi(client, "salvo")
    assert client.get("/api/samples/inesistente.pdf", headers=op).status_code == 404
    # un file presente ma non nel catalogo (es. index.json) non è scaricabile
    assert client.get("/api/samples/index.json", headers=op).status_code == 404


def test_richiede_autenticazione(client: TestClient) -> None:
    assert client.get("/api/samples").status_code == 401


def test_admin_puo_scaricare(crea_client: Callable[..., TestClient]) -> None:
    client = crea_client()
    admin = accedi(client, "giovanna")
    assert client.get("/api/samples", headers=admin).status_code == 200
