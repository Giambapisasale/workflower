"""Casi di contorno delle feature di dominio (Fase 3): guardie, registri vuoti,
auto-aggiornamento e robustezza dell'harness T3.

Completano i test "happy path" di ``test_entita_m20`` e ``test_registri_m21``.
"""

from collections.abc import Callable
from pathlib import Path

from aiuti import accedi
from fastapi.testclient import TestClient

from app.core.dal import DAL
from app.core.eval_t3 import EvalT3
from app.core.gateway import Gateway
from app.core.views import query

# --------------------------------------------------------- M20: guardie CRUD


def test_scadenza_blocca_eliminazione_del_cantiere(client: TestClient) -> None:
    """Il guard di eliminazione riconosce il riferimento della nuova entità."""
    admin = accedi(client, "giovanna")
    # cantiere nuovo, referenziato SOLO da una scadenza
    cid = client.post(
        "/api/entities/cantiere",
        headers=admin,
        json={"dati": {
            "nome": "Cantiere Temporaneo", "indirizzo": "Via Prova 1", "comune": "Catania",
            "committente": "Prova S.r.l.", "budget": 1000.0, "data_inizio": "2026-01-01",
        }},
    ).json()["id"]
    client.post(
        "/api/entities/scadenza",
        headers=admin,
        json={"dati": {"descrizione": "DIA", "data_scadenza": "2026-12-01", "cantiere_id": cid}},
    )
    # ora il cantiere è "ancora usato": eliminazione bloccata (409, mai cascade)
    r = client.delete(f"/api/entities/cantiere/{cid}", headers=admin)
    assert r.status_code == 409
    assert "ancora usato" in r.json()["detail"]


def test_materiale_riferimento_fornitore_inesistente(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    r = client.post(
        "/api/entities/materiale",
        headers=admin,
        json={"dati": {"descrizione": "Cemento", "unita_misura": "kg", "fornitore_id": "FRN-999"}},
    )
    assert r.status_code == 422


def test_eliminazione_entita_libera(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    mid = client.post(
        "/api/entities/mezzo", headers=admin, json={"dati": {"descrizione": "Betoniera"}}
    ).json()["id"]
    assert client.delete(f"/api/entities/mezzo/{mid}", headers=admin).status_code == 200


# --------------------------------------------------- M21: registri di contorno


def test_cronoprogramma_senza_sal_ha_reale_zero(client: TestClient, dati_rw: Path) -> None:
    """Un cantiere senza SAL: il pianificato c'è, il consuntivo reale è 0."""
    admin = accedi(client, "giovanna")
    # CNT-002 non ha SAL nel seed
    client.post(
        "/api/entities/cronoprogramma",
        headers=admin,
        json={"dati": {"cantiere_id": "CNT-002", "voci": [
            {"descrizione": "Scavi", "inizio_previsto": "2026-03-02",
             "fine_prevista": "2026-04-30"},
            {"descrizione": "Getti", "inizio_previsto": "2026-05-01",
             "fine_prevista": "2027-01-31"},
        ]}},
    )
    riga = query(dati_rw, "SELECT * FROM v_cronoprogramma WHERE cantiere_id = 'CNT-002'")[0]
    assert riga["reale_pct"] == 0
    assert riga["voci_totali"] == 2
    # una voce conclusa (fine <= oggi) su due → pianificato 50%
    assert riga["pianificato_pct"] == 50.0
    assert riga["delta_pct"] == -50.0


def test_pozzetti_registro_vuoto_per_cantiere_senza(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    reg = client.get("/api/cantieri/CNT-002/registro", headers=admin).json()
    assert reg["pozzetti"] == []
    assert reg["totali"]["pozzetti"] is None  # nessun riepilogo


def test_registro_si_aggiorna_col_nuovo_pozzetto(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    prima = client.get("/api/cantieri/CNT-002/registro", headers=admin).json()
    assert prima["totali"]["pozzetti"] is None
    client.post(
        "/api/entities/pozzetto",
        headers=admin,
        json={"dati": {"cantiere_id": "CNT-002", "codice": "PZ-A", "stato": "previsto"}},
    )
    dopo = client.get("/api/cantieri/CNT-002/registro", headers=admin).json()
    assert dopo["totali"]["pozzetti"]["totale"] == 1
    assert dopo["totali"]["pozzetti"]["previsti"] == 1


# ------------------------------------------------- M18: robustezza harness T3


def test_eval_t3_tollerante_agli_errori_del_modello(
    crea_client: Callable[..., TestClient], dati_rw: Path, fixtures_dir: Path, monkeypatch
) -> None:
    """Se il candidato risponde in modo malformato, l'accuratezza è 0, senza crash."""
    client = crea_client()
    admin = accedi(client, "giovanna")
    pdf = (fixtures_dir / "fattura-calcestruzzi-etna.pdf").read_bytes()
    corpo = client.post(
        "/api/documents", headers=admin,
        files={"file": ("f.pdf", pdf, "application/pdf")},
    ).json()
    eid = client.get(f"/api/documents/{corpo['doc_id']}", headers=admin).json()[
        "documento"]["dati"]["entity_id"]
    client.post(f"/api/review/{eid}/validate", headers=admin)

    monkeypatch.setenv("LLM_T3_MODEL", "test/finto-t3")

    def malformato(**_kwargs: object) -> dict:
        return {"choices": []}  # risposta senza scelte → GatewayError, gestito

    report = EvalT3(DAL(dati_rw), Gateway(completer=malformato, attesa_retry=0)).valuta()
    assert report["esempi"] >= 3
    assert report["totale"]["candidato"]["args"] == 0.0
    assert report["pronti"] == []
