"""M12 — dataset builder (fine-tuning), registry dei tool, fallback tier T3."""

from pathlib import Path

import pytest
from aiuti import accedi
from fastapi.testclient import TestClient

from app.core.dal import DAL
from app.core.dataset import esempi_finetuning, run_id_validati
from app.core.gateway import Gateway


def _carica_fattura(client: TestClient, fixtures_dir: Path) -> tuple[str, str]:
    intestazioni = accedi(client, "giovanna")
    pdf = (fixtures_dir / "fattura-calcestruzzi-etna.pdf").read_bytes()
    corpo = client.post(
        "/api/documents",
        headers=intestazioni,
        files={"file": ("fattura-calcestruzzi-etna.pdf", pdf, "application/pdf")},
    ).json()
    return corpo["doc_id"], corpo["run_id"]


# ------------------------------------------------------- dataset builder


def test_finetuning_solo_dai_run_validati(
    client: TestClient, dati_rw: Path, fixtures_dir: Path
) -> None:
    doc_id, run_id = _carica_fattura(client, fixtures_dir)
    dal = DAL(dati_rw)
    entity_id = dal.read("documento", doc_id).dati["entity_id"]

    # prima della validazione: il run non è validato → nessun esempio
    assert run_id not in run_id_validati(dal)
    assert list(esempi_finetuning(dal)) == []

    accesso = accedi(client, "giovanna")
    assert client.post(f"/api/review/{entity_id}/validate", headers=accesso).status_code == 200

    esempi = list(esempi_finetuning(DAL(dati_rw)))
    assert len(esempi) >= 1
    assert all(e["tool_call"]["name"] for e in esempi)
    assert {e["tool_call"]["name"] for e in esempi} >= {"ocr_pdf", "salva_bozza"}
    assert all(e["workflow"] == "carica-fattura@1.0" for e in esempi)


# ------------------------------------------------------- registry dei tool


def test_endpoint_tools_registry(client: TestClient, fixtures_dir: Path) -> None:
    _carica_fattura(client, fixtures_dir)
    intestazioni = accedi(client, "giovanna")
    corpo = client.get("/api/tools", headers=intestazioni).json()

    per_nome = {t["name"]: t for t in corpo["tools"]}
    attesi = {"ocr_pdf", "cerca_fornitore", "cerca_cantiere", "salva_bozza", "cerca_voce_computo"}
    assert attesi <= set(per_nome)
    assert per_nome["salva_bozza"]["usi"] >= 1  # usato dall'upload
    assert per_nome["cerca_voce_computo"]["usi"] == 0  # nessun workflow lo invoca ancora
    assert all(t["ciclo"] == "consolidata" for t in corpo["tools"])
    assert "candidati" in corpo


def test_endpoint_finetuning_download(client: TestClient, fixtures_dir: Path) -> None:
    doc_id, _ = _carica_fattura(client, fixtures_dir)
    intestazioni = accedi(client, "giovanna")
    dal_id = client.get(f"/api/documents/{doc_id}", headers=intestazioni).json()
    entity_id = dal_id["documento"]["dati"]["entity_id"]
    client.post(f"/api/review/{entity_id}/validate", headers=intestazioni)

    risposta = client.get("/api/dataset/finetuning.jsonl", headers=intestazioni)
    assert risposta.status_code == 200
    assert risposta.headers["content-type"].startswith("application/x-ndjson")
    righe = [r for r in risposta.text.splitlines() if r.strip()]
    assert len(righe) >= 1


def test_tools_riservato_admin(client: TestClient) -> None:
    operatore = accedi(client, "salvo")
    assert client.get("/api/tools", headers=operatore).status_code == 403
    assert client.get("/api/dataset/finetuning.jsonl", headers=operatore).status_code == 403


# --------------------------------------------------------------- tier T3


def test_tier_t3_ricade_su_t1_se_non_configurato(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_T1_MODEL", "prov/sota")
    monkeypatch.delenv("LLM_T3_MODEL", raising=False)
    gateway = Gateway()
    # T3 predisposto ma non attivo → si usa il modello di T1
    assert gateway.modello("T3") == "prov/sota"
    # con LLM_T3_MODEL configurato, T3 usa il suo modello
    monkeypatch.setenv("LLM_T3_MODEL", "locale/functiongemma")
    assert gateway.modello("T3") == "locale/functiongemma"
