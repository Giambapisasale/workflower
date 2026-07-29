"""Scarto e ripristino di un inserimento (Revisione → Scarta, Dati → Scartati).

Lo scarto è la risposta alla domanda «e se questa fattura è sbagliata?». Non
cancella: sposta in ``data/scartati/``. Quello che questi test difendono è che lo
spostamento sia *completo* — se l'entità esce dai conti ma il documento
dell'operatore resta verde, o il caso golden continua a pesare sul replay, lo
scarto ha fatto più danno che bene.
"""

from pathlib import Path

import httpx
from aiuti import accedi
from fastapi.testclient import TestClient

from app.core.dal import DAL
from app.core.golden import carica_golden


def _carica(client: TestClient, headers: dict[str, str], percorso: Path) -> httpx.Response:
    return client.post(
        "/api/documents",
        headers=headers,
        files={"file": (percorso.name, percorso.read_bytes(), "application/pdf")},
    )


def _bozza(client: TestClient, dati_rw: Path, fixtures_dir: Path, nome: str) -> tuple[str, str]:
    """Carica una fixture come operatore e ritorna ``(doc_id, entity_id)``."""
    salvo = accedi(client, "salvo")
    corpo = _carica(client, salvo, fixtures_dir / nome).json()
    doc_id = corpo["doc_id"]
    return doc_id, DAL(dati_rw).read("documento", doc_id).dati["entity_id"]


# ------------------------------------------------------------------ lo scarto


def test_scarto_esce_dai_conti_e_resta_ripristinabile(
    client: TestClient, dati_rw: Path, fixtures_dir: Path
) -> None:
    doc_id, entity_id = _bozza(client, dati_rw, fixtures_dir, "fattura-calcestruzzi-etna.pdf")
    admin = accedi(client, "giovanna")
    prima = client.get("/api/dashboard/costs", headers=admin).json()["totali"]["n_fatture"]

    esito = client.post(
        f"/api/review/{entity_id}/scarta", headers=admin, json={"motivo": "fattura doppia"}
    )
    assert esito.status_code == 200, esito.text
    assert esito.json()["stato"] == "scartato"

    # non è più fra le entità, ma il file c'è: spostato, non cancellato
    dal = DAL(dati_rw)
    assert not any(f.id == entity_id for f in dal.list_all("fattura"))
    scartata = dal.leggi_scartato("fattura", entity_id)
    assert scartata.stato == "scartato"
    assert scartata.meta.motivo_scarto == "fattura doppia"
    assert scartata.meta.scartato_da == "giovanna"
    assert scartata.meta.scartato_il

    # esce dalla coda di revisione e dagli aggregati
    coda = client.get("/api/review", headers=admin).json()["da_rivedere"]
    assert not any(v["id"] == entity_id for v in coda)
    dopo = client.get("/api/dashboard/costs", headers=admin).json()["totali"]["n_fatture"]
    assert dopo == prima - 1

    # compare nell'archivio, con il perché
    scartati = client.get("/api/scartati", headers=admin).json()["scartati"]
    voce = next(s for s in scartati if s["id"] == entity_id)
    assert voce["motivo"] == "fattura doppia" and voce["tipo"] == "fattura"

    # il documento dell'operatore lo dice, e non finge che vada tutto bene
    op = accedi(client, "salvo")
    vista = client.get(f"/api/documents/{doc_id}", headers=op).json()
    assert vista["semaforo"] == "rosso"
    assert "scartato" in vista["messaggio"].lower()

    # ripristino: torna dov'era, senza il meta di scarto
    ripristino = client.post(f"/api/scartati/{entity_id}/ripristina", headers=admin)
    assert ripristino.status_code == 200, ripristino.text
    assert ripristino.json()["stato"] == "bozza"
    tornata = DAL(dati_rw).read("fattura", entity_id)
    assert tornata.stato == "bozza"
    assert tornata.meta.motivo_scarto is None and tornata.meta.scartato_da is None
    coda = client.get("/api/review", headers=admin).json()["da_rivedere"]
    assert any(v["id"] == entity_id for v in coda)


def test_scarto_di_un_validato_toglie_il_caso_golden(
    client: TestClient, dati_rw: Path, fixtures_dir: Path
) -> None:
    """Un caso golden nato da un dato ripudiato falserebbe ogni replay futuro."""
    _doc_id, entity_id = _bozza(client, dati_rw, fixtures_dir, "fattura-edil-sud.pdf")
    admin = accedi(client, "giovanna")
    validato = client.post(f"/api/review/{entity_id}/validate", headers=admin).json()
    golden_id = validato["golden_id"]
    assert golden_id is not None

    esito = client.post(
        f"/api/review/{entity_id}/scarta", headers=admin, json={"motivo": "importi errati"}
    )
    assert esito.status_code == 200, esito.text
    assert esito.json()["golden_rimossi"] == [golden_id]
    assert not any(g.id == golden_id for g in carica_golden(dati_rw))

    # era validato: il ripristino lo riporta validato, non bozza
    client.post(f"/api/scartati/{entity_id}/ripristina", headers=admin)
    assert DAL(dati_rw).read("fattura", entity_id).stato == "validato"


def test_scarto_chiude_la_segnalazione_aperta(
    client: TestClient, dati_rw: Path, fixtures_dir: Path
) -> None:
    doc_id, entity_id = _bozza(client, dati_rw, fixtures_dir, "fattura-studio-bianchi.pdf")
    op = accedi(client, "salvo")
    client.post(
        f"/api/documents/{doc_id}/issue", headers=op, json={"testo": "manca la ritenuta"}
    )
    admin = accedi(client, "giovanna")
    aperte = client.get("/api/issues?stato=aperta", headers=admin).json()["issues"]
    assert aperte

    esito = client.post(
        f"/api/review/{entity_id}/scarta", headers=admin, json={"motivo": "la rifacciamo"}
    )
    assert esito.status_code == 200, esito.text
    assert esito.json()["segnalazioni_chiuse"]
    rimaste = client.get("/api/issues?stato=aperta", headers=admin).json()["issues"]
    assert not any(i["entity_id"] == entity_id for i in rimaste)


def test_id_di_uno_scartato_non_viene_riusato(
    client: TestClient, dati_rw: Path, fixtures_dir: Path
) -> None:
    """Se l'id tornasse libero, il ripristino collideerebbe con la fattura nata dopo."""
    _doc, primo = _bozza(client, dati_rw, fixtures_dir, "fattura-calcestruzzi-etna.pdf")
    admin = accedi(client, "giovanna")
    client.post(f"/api/review/{primo}/scarta", headers=admin, json={"motivo": "sbagliata"})

    _doc2, secondo = _bozza(client, dati_rw, fixtures_dir, "fattura-edil-sud.pdf")
    assert secondo != primo

    # e il ripristino del primo convive col secondo
    assert client.post(f"/api/scartati/{primo}/ripristina", headers=admin).status_code == 200
    ids = {f.id for f in DAL(dati_rw).list_all("fattura")}
    assert {primo, secondo} <= ids


# ------------------------------------------------------------------ le guardie


def test_motivo_obbligatorio(client: TestClient, dati_rw: Path, fixtures_dir: Path) -> None:
    _doc, entity_id = _bozza(client, dati_rw, fixtures_dir, "fattura-calcestruzzi-etna.pdf")
    admin = accedi(client, "giovanna")
    for corpo in ({}, {"motivo": ""}, {"motivo": "   "}):
        risposta = client.post(f"/api/review/{entity_id}/scarta", headers=admin, json=corpo)
        assert risposta.status_code == 422, f"{corpo} → {risposta.status_code}"
    assert DAL(dati_rw).read("fattura", entity_id)  # niente è stato spostato


def test_anagrafica_non_si_scarta(client: TestClient) -> None:
    """Un fornitore non è un documento in arrivo: si corregge o si elimina da Dati."""
    admin = accedi(client, "giovanna")
    risposta = client.post(
        "/api/review/FRN-001/scarta", headers=admin, json={"motivo": "doppione"}
    )
    assert risposta.status_code == 409
    assert "Dati" in risposta.json()["detail"]


def test_scarto_riservato_all_ufficio(
    client: TestClient, dati_rw: Path, fixtures_dir: Path
) -> None:
    _doc, entity_id = _bozza(client, dati_rw, fixtures_dir, "fattura-calcestruzzi-etna.pdf")
    op = accedi(client, "salvo")
    assert (
        client.post(
            f"/api/review/{entity_id}/scarta", headers=op, json={"motivo": "no"}
        ).status_code
        == 403
    )
    assert client.get("/api/scartati", headers=op).status_code == 403
    assert client.post(f"/api/scartati/{entity_id}/ripristina", headers=op).status_code == 403
    assert client.get("/api/scartati").status_code == 401  # senza token


def test_scarto_di_id_inesistente(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    assert (
        client.post(
            "/api/review/FT-2026-9999/scarta", headers=admin, json={"motivo": "x"}
        ).status_code
        == 404
    )
    assert client.post("/api/scartati/FT-2026-9999/ripristina", headers=admin).status_code == 404
