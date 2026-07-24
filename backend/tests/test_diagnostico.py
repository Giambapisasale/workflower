"""Diagnostico: legge il proprio codice, classifica dato/architettura, propone.

Copre il modulo ``codebase`` (lettura del sorgente dal traceback, confinata),
il ``Diagnostico`` (classificazione, dedup, risolvi/archivia) e le API.
"""

from collections.abc import Callable
from pathlib import Path

from aiuti import accedi
from fake_diagnostico import FakeDiagnostico
from fastapi.testclient import TestClient
from git import Repo

from app.core import codebase, logbook
from app.core.dal import DAL
from app.core.diagnostico import Diagnostico
from app.core.gateway import Gateway

# ------------------------------------------------------------------ codebase


def _traceback_finto() -> str:
    gateway = (codebase.RADICE_CODICE / "core" / "gateway.py").as_posix()
    return (
        "Traceback (most recent call last):\n"
        '  File "/usr/lib/python3.12/json/__init__.py", line 346, in loads\n'
        "    return _default_decoder.decode(s)\n"
        f'  File "{gateway}", line 130, in complete\n'
        "    raise GatewayError(...)\n"
        "GatewayError: LLM non raggiungibile"
    )


def test_frame_da_traceback_solo_app() -> None:
    frame = codebase.frame_da_traceback(_traceback_finto())
    assert len(frame) == 1  # il frame in json/ è fuori dal package app: scartato
    assert frame[0]["file"].endswith("app/core/gateway.py")
    assert frame[0]["lineno"] == 130


def test_estratto_dentro_e_fuori() -> None:
    dentro = codebase.estratto("core/gateway.py", lineno=130)
    assert dentro is not None
    assert "»" in dentro and "130" in dentro  # la riga a fuoco è marcata
    # fuori dal package app: rifiutato (niente letture arbitrarie del filesystem)
    assert codebase.estratto("/etc/passwd") is None
    assert codebase.estratto("../../setup.py") is None


def test_sorgenti_da_traceback_poi_fallback() -> None:
    da_tb = codebase.sorgenti_per_voce({"fase": "gateway", "eccezione": _traceback_finto()})
    assert da_tb and da_tb[0]["file"].endswith("app/core/gateway.py")
    # senza traceback, il fallback usa la fase
    da_fase = codebase.sorgenti_per_voce({"fase": "dal", "messaggio": "x"})
    assert da_fase and da_fase[0]["file"].endswith("app/core/dal.py")


# --------------------------------------------------------------------- firma


def test_firma_stabile_e_distinta() -> None:
    a = {"fase": "runtime", "messaggio": "run fallito su blobs/a.pdf (run-abc123)"}
    b = {"fase": "runtime", "messaggio": "run fallito su blobs/z.pdf (run-def456)"}
    c = {"fase": "gateway", "messaggio": "modello non raggiungibile"}
    assert logbook.firma(a) == logbook.firma(b)  # differiscono solo per id/percorsi
    assert logbook.firma(a) != logbook.firma(c)


# --------------------------------------------------------------- Diagnostico


def _diag(dati_rw: Path, fake: FakeDiagnostico | None = None) -> Diagnostico:
    logbook.configura_logging(dati_rw, "DEBUG")
    gateway = Gateway(completer=fake or FakeDiagnostico(), attesa_retry=0)
    return Diagnostico(DAL(dati_rw), gateway)


def test_categoria_dato_per_errore_di_workflow(dati_rw: Path, ambiente_llm: None) -> None:
    diag = _diag(dati_rw)
    voce = {
        "ts": "2026-07-23T10:00:00.000+00:00",
        "fase": "runtime",
        "livello": "ERROR",
        "messaggio": "output non conforme",
        "workflow": "carica-fattura",
        "documento": "blobs/x.pdf",
    }
    d = diag.diagnostica_cluster("firma-dato", [voce])
    assert d["categoria"] == "dato"
    assert d["azione_suggerita"]["tipo"] == "improver"
    assert d["azione_suggerita"]["workflow"] == "carica-fattura"
    assert d["stato"] == "proposta"


def test_categoria_architettura_per_eccezione_di_codice(
    dati_rw: Path, ambiente_llm: None
) -> None:
    diag = _diag(dati_rw)
    voce = {
        "ts": "2026-07-23T10:00:00.000+00:00",
        "fase": "gateway",
        "livello": "ERROR",
        "messaggio": "risposta LLM malformata",
        "eccezione": _traceback_finto(),
    }
    d = diag.diagnostica_cluster("firma-arch", [voce])
    assert d["categoria"] == "architettura"
    assert d["azione_suggerita"]["tipo"] == "nessuna"
    # ha letto il proprio codice-cornice
    assert any(s["file"].endswith("app/core/gateway.py") for s in d["sorgenti_lette"])


def test_dedup_aggiorna_conteggio_senza_richiamare_llm(
    dati_rw: Path, ambiente_llm: None
) -> None:
    fake = FakeDiagnostico()
    diag = _diag(dati_rw, fake)
    voce = {"ts": "2026-07-23T10:00:00.000+00:00", "fase": "runtime",
            "livello": "ERROR", "messaggio": "boom", "workflow": "carica-fattura"}
    prima = diag.diagnostica_cluster("firma-x", [voce])
    assert fake.chiamate == 1
    dopo = diag.diagnostica_cluster("firma-x", [voce, voce])
    assert dopo["id"] == prima["id"]  # stessa diagnosi
    assert dopo["n_occorrenze"] == 3  # 1 + 2
    assert fake.chiamate == 1  # nessuna nuova analisi LLM
    assert len(DAL(dati_rw).list_diagnosi()) == 1


def test_risolvi_e_archivia(dati_rw: Path, ambiente_llm: None) -> None:
    diag = _diag(dati_rw)
    voce = {"ts": "2026-07-23T10:00:00.000+00:00", "fase": "gateway",
            "livello": "ERROR", "messaggio": "x", "eccezione": _traceback_finto()}
    d = diag.diagnostica_cluster("firma-r", [voce])
    risolta = diag.risolvi(d["id"], "giovanna")
    assert risolta["stato"] == "risolta" and risolta["deciso_da"] == "giovanna"
    archiviata = diag.archivia(d["id"], "giovanna")
    assert archiviata["stato"] == "archiviata"


def test_analizza_recenti_ignora_fase_diagnostico(
    dati_rw: Path, ambiente_llm: None
) -> None:
    diag = _diag(dati_rw)
    logbook.ottieni_logger("diagnostico").error("errore interno del diagnostico")
    logbook.ottieni_logger("runtime").error(
        "run fallito", extra={"workflow": "carica-fattura", "run_id": "run-1"}
    )
    diagnosi = diag.analizza_recenti(giorni=1)
    fasi = {d["fase"] for d in diagnosi}
    assert "diagnostico" not in fasi
    assert "runtime" in fasi


# ---------------------------------------------------------------- osservatore


def test_osservatore_scatta_sugli_errori(data_repo: Path) -> None:
    logbook.configura_logging(data_repo, "DEBUG")
    visti: list[dict] = []
    logbook.registra_osservatore(visti.append)
    try:
        logbook.ottieni_logger("runtime").info("non è un errore")
        logbook.ottieni_logger("gateway").error("questo sì")
    finally:
        logbook.rimuovi_osservatori()
    assert len(visti) == 1
    assert visti[0]["livello"] == "ERROR" and "firma" in visti[0]


# ----------------------------------------------------------------------- API


def _client_diag(
    crea_client: Callable[..., TestClient], categoria: str | None = None
) -> TestClient:
    return crea_client(FakeDiagnostico(categoria_forzata=categoria))


def test_api_diagnoses_richiede_admin(crea_client: Callable[..., TestClient]) -> None:
    client = _client_diag(crea_client)
    assert client.get("/api/diagnoses").status_code == 401
    op = accedi(client, "salvo")
    assert client.get("/api/diagnoses", headers=op).status_code == 403


def test_api_analyze_crea_e_elenca(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    client = _client_diag(crea_client, categoria="dato")
    admin = accedi(client, "giovanna")
    logbook.ottieni_logger("runtime").error(
        "run fallito su blobs/x.pdf", extra={"workflow": "carica-fattura", "run_id": "run-9"}
    )
    r = client.post("/api/diagnoses/analyze", json={"giorni": 1}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["analizzate"] >= 1

    elenco = client.get("/api/diagnoses", headers=admin).json()["diagnosi"]
    assert len(elenco) >= 1
    did = elenco[0]["id"]
    dettaglio = client.get(f"/api/diagnoses/{did}", headers=admin)
    assert dettaglio.status_code == 200
    assert dettaglio.json()["categoria"] == "dato"
    # la diagnosi è committata: il repo dati resta pulito
    assert not Repo(dati_rw).is_dirty(untracked_files=True)


def test_api_resolve(crea_client: Callable[..., TestClient]) -> None:
    client = _client_diag(crea_client, categoria="architettura")
    admin = accedi(client, "giovanna")
    logbook.ottieni_logger("gateway").error("modello non configurato per il tier T1")
    client.post("/api/diagnoses/analyze", headers=admin)
    diagnosi = client.get("/api/diagnoses", headers=admin).json()["diagnosi"]
    did = diagnosi[0]["id"]
    r = client.post(f"/api/diagnoses/{did}/resolve", headers=admin)
    assert r.status_code == 200 and r.json()["stato"] == "risolta"
    aperte = client.get("/api/diagnoses?stato=proposta", headers=admin).json()["diagnosi"]
    assert did not in [d["id"] for d in aperte]


def test_api_analyze_richiede_admin(crea_client: Callable[..., TestClient]) -> None:
    client = _client_diag(crea_client)
    op = accedi(client, "salvo")
    assert client.post("/api/diagnoses/analyze", headers=op).status_code == 403
