"""M18 — harness di valutazione offline del tier T3.

Rigioca gli esempi già validati contro un modello candidato T3 e ne misura la
function-calling accuracy rispetto al ground truth, confrontandola con T1. Non
addestra nulla: solo misura, col trasporto LLM finto. Serve a decidere *se* e
*quali* workflow instradare su T3 (M19).
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from aiuti import accedi
from fake_llm import FakeCompleter
from fastapi.testclient import TestClient

from app.core.dal import DAL
from app.core.eval_t3 import EvalT3
from app.core.gateway import Gateway

T3 = "test/finto-t3"


def _carica_e_valida(client: TestClient, fixtures_dir: Path) -> str:
    """Carica una fattura e la valida: genera tool call validate (ground truth)."""
    admin = accedi(client, "giovanna")
    pdf = (fixtures_dir / "fattura-calcestruzzi-etna.pdf").read_bytes()
    corpo = client.post(
        "/api/documents",
        headers=admin,
        files={"file": ("fattura-calcestruzzi-etna.pdf", pdf, "application/pdf")},
    ).json()
    entity_id = client.get(f"/api/documents/{corpo['doc_id']}", headers=admin).json()[
        "documento"
    ]["dati"]["entity_id"]
    assert client.post(f"/api/review/{entity_id}/validate", headers=admin).status_code == 200
    return entity_id


class FakeDegrada:
    """FakeCompleter che, sul modello T3, corrompe gli argomenti delle tool call.

    Simula un T3 immaturo: sceglie il tool giusto ma sbaglia gli argomenti,
    così l'harness deve rilevare la regressione rispetto a T1.
    """

    def __init__(self, data_dir: Path, modello_t3: str) -> None:
        self.base = FakeCompleter(data_dir)
        self.modello_t3 = modello_t3

    def __call__(self, *, model, messages, tools=None, **kw):  # type: ignore[no-untyped-def]
        risposta = self.base(model=model, messages=messages, tools=tools, **kw)
        if model == self.modello_t3:
            messaggio = risposta["choices"][0]["message"]
            for chiamata in messaggio.get("tool_calls") or []:
                chiamata["function"]["arguments"] = json.dumps({"query": "SBAGLIATO"})
        return risposta


def _eval(dati_rw: Path, completer: object) -> EvalT3:
    return EvalT3(DAL(dati_rw), Gateway(completer=completer, attesa_retry=0))


# --------------------------------------------------------------------- test


def test_report_senza_regressione_e_pronto(
    client: TestClient,
    dati_rw: Path,
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _carica_e_valida(client, fixtures_dir)
    monkeypatch.setenv("LLM_T3_MODEL", T3)

    # stesso trasporto per entrambi i tier: T3 riproduce T1 → nessuna regressione
    report = _eval(dati_rw, FakeCompleter(dati_rw)).valuta()

    assert report["modello_candidato"] == T3
    assert report["modello_riferimento"] == "test/finto-t1"
    assert report["esempi"] >= 3  # ocr_pdf + cerca_fornitore + cerca_cantiere
    wf = report["workflow"]["carica-fattura@1.0"]
    assert wf["candidato"]["args"] == 1.0
    assert wf["regressione"] is False
    assert wf["pronto_per_t3"] is True
    assert "carica-fattura@1.0" in report["pronti"]
    assert report["regressioni"] == []


def test_report_rileva_regressione(
    client: TestClient,
    dati_rw: Path,
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _carica_e_valida(client, fixtures_dir)
    monkeypatch.setenv("LLM_T3_MODEL", T3)

    report = _eval(dati_rw, FakeDegrada(dati_rw, T3)).valuta()

    wf = report["workflow"]["carica-fattura@1.0"]
    # il tool giusto è ancora scelto, ma gli argomenti no → accuratezza args crolla
    assert wf["riferimento"]["args"] == 1.0
    assert wf["candidato"]["args"] < wf["riferimento"]["args"]
    assert wf["candidato"]["tool"] == 1.0
    assert wf["regressione"] is True
    assert wf["pronto_per_t3"] is False
    assert "carica-fattura@1.0" in report["regressioni"]


def test_set_vuoto_non_esplode(dati_rw: Path, ambiente_llm: None) -> None:
    """Senza esempi validati l'harness emette un report vuoto, senza sollevare."""
    report = _eval(dati_rw, FakeCompleter(dati_rw)).valuta()
    assert report["esempi"] == 0
    assert report["workflow"] == {}
    assert report["pronti"] == []


# --------------------------------------------------------------------- API


def test_api_eval_t3(
    crea_client: Callable[..., TestClient],
    dati_rw: Path,
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = crea_client()  # gateway dell'app = FakeCompleter reale
    _carica_e_valida(client, fixtures_dir)
    monkeypatch.setenv("LLM_T3_MODEL", T3)

    admin = accedi(client, "giovanna")
    report = client.get("/api/dataset/eval-t3", headers=admin)
    assert report.status_code == 200, report.text
    corpo = report.json()
    assert corpo["esempi"] >= 3
    assert "carica-fattura@1.0" in corpo["workflow"]


def test_api_eval_t3_riservato_admin(crea_client: Callable[..., TestClient]) -> None:
    client = crea_client()
    operatore = accedi(client, "salvo")
    assert client.get("/api/dataset/eval-t3", headers=operatore).status_code == 403
