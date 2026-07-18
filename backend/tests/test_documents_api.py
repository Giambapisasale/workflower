"""E2E API documenti (AC M3): upload → semaforo, conferma, segnalazione.

Contratto di fondo: l'operatore non vede MAI un errore bloccante — anche
con l'LLM rotto o un file illeggibile l'upload risponde 200 e il documento
finisce in coda all'ufficio (issue automatica).
"""

import json
from pathlib import Path
from typing import Any

import httpx
from aiuti import accedi, stringhe_di
from fake_llm import FakeCompleter
from fastapi.testclient import TestClient
from litellm.exceptions import AuthenticationError

from app.core.dal import DAL


def _carica(
    client: TestClient,
    intestazioni: dict[str, str],
    percorso: Path | None = None,
    nome: str | None = None,
    contenuto: bytes | None = None,
    mime: str = "application/pdf",
) -> httpx.Response:
    corpo = contenuto if contenuto is not None else percorso.read_bytes()
    return client.post(
        "/api/documents",
        headers=intestazioni,
        files={"file": (nome or percorso.name, corpo, mime)},
    )


def _eventi_trace(data_dir: Path, run_id: str) -> list[dict[str, Any]]:
    percorso = next((data_dir / "traces").glob(f"*/*/{run_id}.jsonl"))
    return [json.loads(riga) for riga in percorso.read_text(encoding="utf-8").splitlines()]


def _issues(data_dir: Path) -> list[dict[str, Any]]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((data_dir / "issues").glob("ISS-*.json"))
    ]


def test_upload_fattura_e2e(client: TestClient, dati_rw: Path, fixtures_dir: Path) -> None:
    intestazioni = accedi(client)
    risposta = _carica(client, intestazioni, fixtures_dir / "fattura-calcestruzzi-etna.pdf")
    assert risposta.status_code == 200
    corpo = risposta.json()
    assert corpo["doc_id"] == "DOC-2026-0001"
    assert corpo["run_id"].startswith("run-")

    dettaglio = client.get(f"/api/documents/{corpo['doc_id']}", headers=intestazioni)
    assert dettaglio.status_code == 200
    vista = dettaglio.json()
    assert vista["in_corso"] is False
    assert vista["chiuso"] is False
    assert vista["semaforo"] == "giallo"
    assert vista["riepilogo"] == {
        "tipo": "Fattura",
        "ditta": "Calcestruzzi Etna S.p.A.",
        "importo": 10162.60,
        "cantiere": "Residenza Le Palme",
        "numero": "112/2026",
        "data": "2026-07-05",
    }

    # dietro le quinte: bozza vera nel repo dati, collegata al documento
    dal = DAL(dati_rw)
    documento = dal.read("documento", corpo["doc_id"])
    assert documento.dati["esito"] == "ok"
    assert documento.dati["entity_id"] == "FT-2026-0006"
    assert documento.dati["caricato_da"] == "salvo"
    assert documento.dati["cantiere_id"] == "CNT-001"  # unico cantiere: scelto da solo
    fattura = dal.read("fattura", "FT-2026-0006")
    assert fattura.stato == "bozza"
    assert fattura.meta.confidence
    assert not dal.repo.is_dirty(untracked_files=True)  # ogni mutazione è committata


def test_elenco_solo_i_propri(client: TestClient, fixtures_dir: Path) -> None:
    salvo = accedi(client, "salvo")
    _carica(client, salvo, fixtures_dir / "fattura-calcestruzzi-etna.pdf")

    elenco = client.get("/api/documents?mine=1", headers=salvo).json()["documenti"]
    assert len(elenco) == 1
    assert elenco[0]["titolo"] == "Fattura Calcestruzzi Etna S.p.A."

    giuseppe = accedi(client, "giuseppe")
    assert client.get("/api/documents", headers=giuseppe).json()["documenti"] == []
    dettaglio = client.get(f"/api/documents/{elenco[0]['id']}", headers=giuseppe)
    assert dettaglio.status_code == 404


def test_conferma_e_nota_sul_run_senza_validare(
    client: TestClient, dati_rw: Path, fixtures_dir: Path
) -> None:
    intestazioni = accedi(client)
    corpo = _carica(client, intestazioni, fixtures_dir / "fattura-edil-sud.pdf").json()

    conferma = client.post(f"/api/documents/{corpo['doc_id']}/confirm", headers=intestazioni)
    assert conferma.status_code == 200
    assert client.get(f"/api/documents/{corpo['doc_id']}", headers=intestazioni).json()["chiuso"]

    eventi = _eventi_trace(dati_rw, corpo["run_id"])
    feedback = [e for e in eventi if e["evento"] == "operator_feedback"]
    assert feedback and feedback[0]["tipo"] == "conferma" and feedback[0]["utente"] == "salvo"

    # "non valida!": la fattura resta bozza, la validazione è dell'ufficio
    dal = DAL(dati_rw)
    entity_id = dal.read("documento", corpo["doc_id"]).dati["entity_id"]
    fattura = dal.read("fattura", entity_id)
    assert fattura.stato == "bozza"
    assert fattura.meta.validato_da is None

    # idempotente: un secondo tap non fa danni
    assert client.post(
        f"/api/documents/{corpo['doc_id']}/confirm", headers=intestazioni
    ).status_code == 200


def test_segnalazione_apre_issue(
    client: TestClient, dati_rw: Path, fixtures_dir: Path
) -> None:
    intestazioni = accedi(client)
    corpo = _carica(client, intestazioni, fixtures_dir / "fattura-studio-bianchi.pdf").json()

    testo = "manca la ritenuta, in fondo al foglio c'è scritto ritenuta e il netto è 4080"
    risposta = client.post(
        f"/api/documents/{corpo['doc_id']}/issue",
        json={"testo": testo},
        headers=intestazioni,
    )
    assert risposta.status_code == 200
    issue_id = risposta.json()["issue_id"]
    assert issue_id == "ISS-0001"

    vista = client.get(f"/api/documents/{corpo['doc_id']}", headers=intestazioni).json()
    assert vista["chiuso"] is True
    assert vista["semaforo"] == "giallo"
    assert "Segnalazione inviata" in vista["messaggio"]

    issues = _issues(dati_rw)
    assert len(issues) == 1
    assert issues[0]["origine"] == "operatore"
    assert issues[0]["testo"] == testo
    assert issues[0]["run_id"] == corpo["run_id"]
    assert issues[0]["entity_id"] == "FT-2026-0006"

    eventi = [
        e
        for e in _eventi_trace(dati_rw, corpo["run_id"])
        if e["evento"] == "operator_feedback"
    ]
    assert eventi[0]["tipo"] == "segnalazione"
    assert eventi[0]["issue_id"] == issue_id
    assert eventi[0]["testo"] == testo


def test_upload_formato_sconosciuto_mai_bloccante(
    client: TestClient, dati_rw: Path
) -> None:
    intestazioni = accedi(client)
    risposta = _carica(
        client,
        intestazioni,
        nome="appunti di cantiere.docx",
        contenuto=b"non sono un documento leggibile",
        mime="application/octet-stream",
    )
    assert risposta.status_code == 200
    doc_id = risposta.json()["doc_id"]

    vista = client.get(f"/api/documents/{doc_id}", headers=intestazioni).json()
    assert vista["in_corso"] is False
    assert vista["semaforo"] == "rosso"
    assert vista["riepilogo"] is None
    assert "ufficio" in vista["messaggio"]

    issues = _issues(dati_rw)
    assert len(issues) == 1 and issues[0]["origine"] == "auto"


def test_upload_con_llm_rotto_mai_500(crea_client, dati_rw: Path, fixtures_dir: Path) -> None:
    # chiave errata: rompe OGNI chiamata (classificazione ed estrazione)
    guasto = AuthenticationError("chiave errata", llm_provider="test", model="finto")
    client = crea_client(FakeCompleter(dati_rw, guasto_persistente=guasto))
    intestazioni = accedi(client)

    risposta = _carica(client, intestazioni, fixtures_dir / "fattura-calcestruzzi-etna.pdf")
    assert risposta.status_code == 200  # mai eccezione all'utente

    vista = client.get(f"/api/documents/{risposta.json()['doc_id']}", headers=intestazioni)
    assert vista.json()["semaforo"] == "rosso"

    dal = DAL(dati_rw)
    assert len(dal.list_all("fattura")) == 5  # solo il seed: nessuna bozza nata dal guasto
    assert any(i["origine"] == "auto" for i in _issues(dati_rw))


def test_upload_troppo_pesante(client: TestClient) -> None:
    intestazioni = accedi(client)
    risposta = _carica(
        client,
        intestazioni,
        nome="scansione.pdf",
        contenuto=b"x" * (15 * 1024 * 1024 + 1),
    )
    assert risposta.status_code == 200
    corpo = risposta.json()
    assert "doc_id" not in corpo
    assert corpo["messaggio"]


def test_semaforo_verde_dopo_validazione(
    client: TestClient, dati_rw: Path, fixtures_dir: Path
) -> None:
    intestazioni = accedi(client)
    corpo = _carica(client, intestazioni, fixtures_dir / "fattura-calcestruzzi-etna.pdf").json()

    dal = DAL(dati_rw)
    entity_id = dal.read("documento", corpo["doc_id"]).dati["entity_id"]
    dal.set_validato("fattura", entity_id, validato_da="giovanna")

    vista = client.get(f"/api/documents/{corpo['doc_id']}", headers=intestazioni).json()
    assert vista["semaforo"] == "verde"
    assert vista["messaggio"] == "Tutto a posto."


def test_admin_vede_envelope_completo(
    client: TestClient, fixtures_dir: Path
) -> None:
    salvo = accedi(client, "salvo")
    corpo = _carica(client, salvo, fixtures_dir / "fattura-calcestruzzi-etna.pdf").json()

    giovanna = accedi(client, "giovanna")
    dettaglio = client.get(f"/api/documents/{corpo['doc_id']}", headers=giovanna).json()
    assert dettaglio["documento"]["dati"]["run_id"] == corpo["run_id"]
    assert dettaglio["entita"]["id"] == "FT-2026-0006"
    assert dettaglio["entita"]["meta"]["confidence"]  # l'admin sì che la vede

    # e nell'elenco vede anche i documenti degli altri
    elenco = client.get("/api/documents", headers=giovanna).json()["documenti"]
    assert len(elenco) == 1


def test_stringhe_operatore_senza_gergo(client: TestClient, fixtures_dir: Path) -> None:
    """AC M3: mai 'workflow', 'JSON', 'confidence' (né 'bozza') per l'operatore."""
    import re

    vietate = re.compile(r"workflow|json|confidence|bozza", re.IGNORECASE)
    intestazioni = accedi(client)
    corpo = _carica(client, intestazioni, fixtures_dir / "fattura-calcestruzzi-etna.pdf").json()

    risposte: list[Any] = [
        client.get("/api/documents?mine=1", headers=intestazioni).json(),
        client.get(f"/api/documents/{corpo['doc_id']}", headers=intestazioni).json(),
    ]
    for stringa in [s for r in risposte for s in stringhe_di(r)]:
        assert not vietate.search(stringa), f"gergo tecnico verso l'operatore: {stringa!r}"
