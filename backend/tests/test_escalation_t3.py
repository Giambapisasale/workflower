"""M19 — attivazione T3 + escalation T3→T1.

Uno step instradato su T3 gira prima su T3; su errore/bassa confidence/output
fuori contratto **escala a T1** e traccia l'escalation (osservabilità: % per
workflow = segnale di ri-training). Senza ``LLM_T3_MODEL`` il comportamento è
invariato (T1). Il costo del tier locale è ~0. Trasporto LLM finto.
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from aiuti import accedi
from fake_llm import FakeCompleter
from fastapi.testclient import TestClient

from app.core.dataset import statistiche
from app.core.tracer import leggi_eventi

T3 = "test/finto-t3"
FATTURA = "fattura-calcestruzzi-etna.pdf"


def _instrada_su_t3(dati_rw: Path) -> None:
    """Dichiara ``tier: T3`` nel manifest di carica-fattura (dato, non codice)."""
    manifest = dati_rw / "workflows" / "carica-fattura" / "manifest.yaml"
    testo = manifest.read_text("utf-8").replace("tier: T1", "tier: T3")
    manifest.write_text(testo, encoding="utf-8")


class FakeT3(FakeCompleter):
    """FakeCompleter che sul modello T3 abbassa la confidence del risultato finale.

    Simula un T3 insicuro: costo ~0 (modello locale) e confidence sotto soglia,
    così il runtime deve escalare a T1. Su T1 si comporta normalmente.
    """

    def __init__(self, data_dir: Path, modello_t3: str = T3, insicuro: bool = True) -> None:
        super().__init__(data_dir)
        self.modello_t3 = modello_t3
        self.insicuro = insicuro

    def __call__(self, *, model, messages, tools=None, **kw):  # type: ignore[no-untyped-def]
        risposta = super().__call__(model=model, messages=messages, tools=tools, **kw)
        if model != self.modello_t3:
            return risposta
        risposta["_hidden_params"] = {"response_cost": 0.0}  # modello locale: costo ~0
        messaggio = risposta["choices"][0]["message"]
        if self.insicuro and messaggio.get("content") and not messaggio.get("tool_calls"):
            try:
                dato = json.loads(messaggio["content"])
            except (ValueError, TypeError):
                return risposta
            if isinstance(dato, dict) and dato.get("confidence"):
                dato["confidence"] = {k: 0.1 for k in dato["confidence"]}
                messaggio["content"] = json.dumps(dato, ensure_ascii=False)
        return risposta


def _carica(client: TestClient, fixtures_dir: Path) -> str:
    admin = accedi(client, "giovanna")
    pdf = (fixtures_dir / FATTURA).read_bytes()
    return client.post(
        "/api/documents",
        headers=admin,
        files={"file": (FATTURA, pdf, "application/pdf")},
    ).json()["run_id"]


# --------------------------------------------------------------------- test


def test_escala_a_t1_su_bassa_confidence(
    crea_client: Callable[..., TestClient],
    dati_rw: Path,
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _instrada_su_t3(dati_rw)
    monkeypatch.setenv("LLM_T3_MODEL", T3)
    client = crea_client(FakeT3(dati_rw))
    run_id = _carica(client, fixtures_dir)

    # l'escalation è tracciata, da T3 a T1
    escalation = leggi_eventi(dati_rw, run_id, {"escalation"})
    assert escalation and escalation[0]["da"] == "T3" and escalation[0]["a"] == "T1"
    assert "confidence" in escalation[0]["motivo"]

    # ha girato su entrambi i tier; il costo di T3 è ~0, quello di T1 no
    chiamate = leggi_eventi(dati_rw, run_id, {"llm_call"})
    tier_visti = {c["tier"] for c in chiamate}
    assert {"T3", "T1"} <= tier_visti
    assert all(c["cost_usd"] == 0 for c in chiamate if c["tier"] == "T3")
    assert any(c["cost_usd"] > 0 for c in chiamate if c["tier"] == "T1")

    # il documento è stato comunque elaborato (fallback riuscito)
    admin = accedi(client, "giovanna")
    coda = client.get("/api/review", headers=admin).json()["da_rivedere"]
    assert any(v["tipo"] == "fattura" for v in coda)


def test_t3_sicuro_non_escala(
    crea_client: Callable[..., TestClient],
    dati_rw: Path,
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _instrada_su_t3(dati_rw)
    monkeypatch.setenv("LLM_T3_MODEL", T3)
    # T3 sicuro (confidence normale): gira su T3 e basta, nessuna escalation
    client = crea_client(FakeT3(dati_rw, insicuro=False))
    run_id = _carica(client, fixtures_dir)

    assert leggi_eventi(dati_rw, run_id, {"escalation"}) == []
    chiamate = leggi_eventi(dati_rw, run_id, {"llm_call"})
    assert any(c["tier"] == "T3" for c in chiamate)
    assert all(c["tier"] != "T1" for c in chiamate)  # non ha toccato T1


def test_senza_variabile_comportamento_invariato(
    crea_client: Callable[..., TestClient],
    dati_rw: Path,
    fixtures_dir: Path,
) -> None:
    """tier T3 nel manifest ma LLM_T3_MODEL assente → si usa T1, nessuna escalation."""
    _instrada_su_t3(dati_rw)
    client = crea_client()  # FakeCompleter reale; LLM_T3_MODEL non impostata
    run_id = _carica(client, fixtures_dir)

    # T3 spento: gateway.modello("T3") ricade su T1, nessuna escalation e il run
    # va a buon fine — comportamento identico a prima di M19.
    assert leggi_eventi(dati_rw, run_id, {"escalation"}) == []
    admin = accedi(client, "giovanna")
    assert client.get("/api/review", headers=admin).json()["da_rivedere"]


def test_statistiche_riporta_percentuale_escalation(
    crea_client: Callable[..., TestClient],
    dati_rw: Path,
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _instrada_su_t3(dati_rw)
    monkeypatch.setenv("LLM_T3_MODEL", T3)
    client = crea_client(FakeT3(dati_rw))
    _carica(client, fixtures_dir)

    esc = statistiche(dati_rw)["escalation"]
    assert esc["totale"] >= 1
    per_wf = esc["per_workflow"]
    assert "carica-fattura" in per_wf
    assert per_wf["carica-fattura"]["escalation"] >= 1
    assert per_wf["carica-fattura"]["percentuale"] > 0
