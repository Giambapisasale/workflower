"""Logbook + API di diagnostica: livello configurabile e copertura delle fasi."""

from pathlib import Path

import pytest
from aiuti import accedi
from fastapi.testclient import TestClient
from git import Repo

from app.core import logbook


def test_scrittura_e_lettura(data_repo: Path) -> None:
    logbook.configura_logging(data_repo, livello="DEBUG")
    logbook.ottieni_logger("gateway").warning(
        "modello lento", extra={"run_id": "run-x", "step": "estrai"}
    )
    voci = logbook.leggi_log(data_repo)
    assert len(voci) == 1
    voce = voci[0]
    assert voce["livello"] == "WARNING"
    assert voce["fase"] == "gateway"
    assert voce["messaggio"] == "modello lento"
    assert voce["run_id"] == "run-x"
    assert voce["step"] == "estrai"


def test_errore_con_traceback(data_repo: Path) -> None:
    logbook.configura_logging(data_repo, livello="INFO")
    try:
        raise ValueError("boom")
    except ValueError as exc:
        logbook.ottieni_logger("runtime").error("caduto", exc_info=exc)
    voce = logbook.leggi_log(data_repo)[0]
    assert voce["livello"] == "ERROR"
    assert "Traceback" in voce["eccezione"]
    assert "boom" in voce["eccezione"]


def test_filtri_livello_fase_testo(data_repo: Path) -> None:
    logbook.configura_logging(data_repo, livello="DEBUG")
    logbook.ottieni_logger("dal").debug("commit alfa")
    logbook.ottieni_logger("gateway").error("timeout beta")
    logbook.ottieni_logger("runtime").info("run alfa")

    assert len(logbook.leggi_log(data_repo, livello_min="ERROR")) == 1
    assert len(logbook.leggi_log(data_repo, fase="dal")) == 1
    testo = logbook.leggi_log(data_repo, testo="alfa")
    assert len(testo) == 2


def test_stringhe_lunghe_troncate(data_repo: Path) -> None:
    logbook.configura_logging(data_repo, livello="DEBUG")
    lungo = "x" * 1000
    logbook.ottieni_logger("runtime").info("grande", extra={"dettagli": {"blob": lungo}})
    voce = logbook.leggi_log(data_repo)[0]
    assert "troncati" in voce["dettagli"]["blob"]
    assert len(voce["dettagli"]["blob"]) < 100


def test_statistiche(data_repo: Path) -> None:
    logbook.configura_logging(data_repo, livello="DEBUG")
    logbook.ottieni_logger("gateway").error("e1")
    logbook.ottieni_logger("gateway").error("e2")
    logbook.ottieni_logger("dal").info("i1")
    stats = logbook.statistiche_log(data_repo)
    assert stats["totale"] == 3
    assert stats["errori"] == 2
    assert stats["per_livello"]["ERROR"] == 2
    assert stats["per_fase"]["gateway"] == 2


def test_livello_env_default(data_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    assert logbook.configura_logging(data_repo) == "WARNING"


def test_livello_persistito_vince_su_env(
    data_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    logbook.imposta_livello(data_repo, "ERROR")
    assert logbook.configura_logging(data_repo) == "ERROR"


def test_imposta_livello_filtra(data_repo: Path) -> None:
    logbook.configura_logging(data_repo, livello="ERROR")
    logbook.ottieni_logger("runtime").info("non deve comparire")
    logbook.ottieni_logger("runtime").error("deve comparire")
    voci = logbook.leggi_log(data_repo)
    assert len(voci) == 1
    assert voci[0]["messaggio"] == "deve comparire"


def test_imposta_livello_ignoto(data_repo: Path) -> None:
    logbook.configura_logging(data_repo, livello="INFO")
    with pytest.raises(ValueError):
        logbook.imposta_livello(data_repo, "VERBOSE")


def test_logs_gitignorati_repo_pulito(data_repo: Path) -> None:
    """I log vivono nella SoT ma non sporcano il repo dati (sono gitignorati)."""
    logbook.configura_logging(data_repo, livello="DEBUG")
    logbook.ottieni_logger("runtime").info("evento")
    logbook.imposta_livello(data_repo, "DEBUG")
    assert (data_repo / "logs").exists()
    assert Repo(data_repo).is_dirty(untracked_files=True) is False


# ------------------------------------------------------------------- API


def test_api_log_richiede_admin(client: TestClient) -> None:
    assert client.get("/api/logs").status_code == 401
    op = accedi(client, "salvo")  # operatore, non admin
    assert client.get("/api/logs", headers=op).status_code == 403


def test_api_elenco_e_config(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    r = client.get("/api/logs", headers=admin)
    assert r.status_code == 200
    corpo = r.json()
    assert "voci" in corpo and "fasi" in corpo and "livelli" in corpo

    cfg = client.get("/api/logs/config", headers=admin).json()
    assert cfg["livello"] in logbook.LIVELLI


def test_api_cambio_livello(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    r = client.put("/api/logs/config", json={"livello": "error"}, headers=admin)
    assert r.status_code == 200
    assert r.json()["livello"] == "ERROR"
    assert client.get("/api/logs/config", headers=admin).json()["livello"] == "ERROR"

    brutto = client.put("/api/logs/config", json={"livello": "MEGA"}, headers=admin)
    assert brutto.status_code == 400


def test_api_stats(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    logbook.ottieni_logger("api").error("errore di prova per le stats")
    stats = client.get("/api/logs/stats", headers=admin).json()
    assert stats["totale"] >= 1
    assert "per_livello" in stats and "per_fase" in stats
