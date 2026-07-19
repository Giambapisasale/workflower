"""M16 — Toolsmith: candidato → generazione (T1) → test dai trace → proposta.

Il punto critico del §3.6: i test si ricavano dalle **coppie storiche validate**,
non da esempi inventati, e girano in **sandbox** (M14). L'output è una proposta
ispezionabile; **nulla viene attivato** nel registry (l'attivazione è M17). Lo
scenario canonico è la **ritenuta d'acconto**: un calcolo deterministico oggi
affidato al prompt.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from aiuti import accedi
from fake_toolsmith import FakeCompleterToolsmith
from fastapi.testclient import TestClient

from app.core.dal import DAL
from app.core.dataset import leggi_derivazioni, registra_derivazione
from app.core.gateway import Gateway
from app.core.pytools import carica_pytools
from app.core.tools import Toolset
from app.core.toolsmith import Toolsmith, ToolsmithError

# coppie (imponibile → ritenuta = imponibile * 20%) come le validerebbe l'ufficio
COPPIE = [(1000, 200.0), (1500, 300.0), (2000, 400.0), (800, 160.0)]

CANDIDATO = {
    "nome": "calcola_ritenuta",
    "tipo": "fattura",
    "workflow": "carica-fattura",
    "campi_input": ["imponibile"],
    "campo_output": "ritenuta_acconto",
}


def _semina_derivazioni(dati_rw: Path, coppie: list[tuple[int, float]] = COPPIE) -> DAL:
    """Registra coppie estratto→validato (ritenuta lasciata null dal grezzo, poi corretta)."""
    dal = DAL(dati_rw)
    for i, (imp, rit) in enumerate(coppie):
        registra_derivazione(
            dal,
            run_id=f"RUN-{i}",
            workflow="carica-fattura",
            tipo="fattura",
            entity_id=f"FATT-{i:04d}",
            estratto={"imponibile": imp, "ritenuta_acconto": None},
            validato={"imponibile": imp, "ritenuta_acconto": rit},
            validato_da="giovanna",
        )
    return dal


def _toolsmith(dati_rw: Path, completer: object) -> Toolsmith:
    gateway = Gateway(completer=completer, attesa_retry=0)
    return Toolsmith(DAL(dati_rw), gateway)


# ------------------------------------------------------- unit: esempi/candidati


def test_esempi_dalle_coppie_validate(dati_rw: Path, ambiente_llm: None) -> None:
    _semina_derivazioni(dati_rw)
    esempi = _toolsmith(dati_rw, FakeCompleterToolsmith()).esempi(CANDIDATO)
    assert len(esempi) == len(COPPIE)
    assert esempi[0] == {"argomenti": {"imponibile": 1000}, "atteso": {"ritenuta_acconto": 200.0}}


def test_candidati_emergono_dal_delta(dati_rw: Path, ambiente_llm: None) -> None:
    _semina_derivazioni(dati_rw)
    candidati = _toolsmith(dati_rw, FakeCompleterToolsmith()).candidati()
    per_campo = {c["campo"]: c for c in candidati}
    assert "ritenuta_acconto" in per_campo
    assert per_campo["ritenuta_acconto"]["occorrenze"] == len(COPPIE)
    # un campo mai corretto (imponibile, uguale in estratto e validato) non è candidato
    assert "imponibile" not in per_campo


# ----------------------------------------------------------------- proposta


def test_proposta_con_test_verdi_dai_trace(dati_rw: Path, ambiente_llm: None) -> None:
    """AC: dato un calcolo ricorrente, il Toolsmith propone un tool i cui test passano."""
    _semina_derivazioni(dati_rw)
    toolsmith = _toolsmith(dati_rw, FakeCompleterToolsmith())
    proposta = toolsmith.proponi(CANDIDATO)

    assert proposta["id"].startswith("PROP-")
    assert proposta["stato"] == "proposta"
    assert proposta["nome"] == "calcola_ritenuta"
    # lo schema segue il nome del candidato (non il placeholder del generatore)
    assert proposta["schema"]["function"]["name"] == "calcola_ritenuta"
    # i test vengono dalle coppie storiche e passano tutti in sandbox
    assert proposta["esito_test"]["totale"] == len(COPPIE)
    assert proposta["esito_test"]["ok"] == len(COPPIE)
    assert len(proposta["test"]) == len(COPPIE)

    # nulla è stato attivato: il registry dei tool non ha il pytool
    assert carica_pytools(dati_rw) == []
    assert "calcola_ritenuta" not in {v["name"] for v in Toolset(DAL(dati_rw)).elenco()}


def test_proposta_ispezionabile_via_dal(dati_rw: Path, ambiente_llm: None) -> None:
    _semina_derivazioni(dati_rw)
    dal = DAL(dati_rw)
    proposta = _toolsmith(dati_rw, FakeCompleterToolsmith()).proponi(CANDIDATO)
    riletta = dal.leggi_proposta(proposta["id"])
    assert riletta["codice"] == proposta["codice"]
    assert [p["id"] for p in dal.list_proposte()] == [proposta["id"]]


def test_codice_errato_registra_esito_rosso(dati_rw: Path, ambiente_llm: None) -> None:
    """Se il codice generato non riproduce i trace, l'esito lo dice (niente illusioni)."""
    _semina_derivazioni(dati_rw)
    # aliquota sbagliata: 25% invece del 20% osservato
    proposta = _toolsmith(dati_rw, FakeCompleterToolsmith(aliquota="0.25")).proponi(CANDIDATO)
    assert proposta["esito_test"]["ok"] < proposta["esito_test"]["totale"]
    # la proposta esiste comunque (ispezionabile), ma nulla è attivo
    assert proposta["id"].startswith("PROP-")
    assert carica_pytools(dati_rw) == []


def test_proponi_rifiuta_esempi_insufficienti(dati_rw: Path, ambiente_llm: None) -> None:
    _semina_derivazioni(dati_rw, COPPIE[:2])  # sotto MIN_ESEMPI
    with pytest.raises(ToolsmithError, match="almeno"):
        _toolsmith(dati_rw, FakeCompleterToolsmith()).proponi(CANDIDATO)


def test_proponi_rifiuta_candidato_malformato(dati_rw: Path, ambiente_llm: None) -> None:
    _semina_derivazioni(dati_rw)
    toolsmith = _toolsmith(dati_rw, FakeCompleterToolsmith())
    with pytest.raises(ToolsmithError, match="campo di uscita"):
        toolsmith.proponi({**CANDIDATO, "campo_output": ""})


# --------------------------------------------------------------------- API


def test_api_proponi_e_ispeziona(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    _semina_derivazioni(dati_rw)
    client = crea_client(FakeCompleterToolsmith())
    admin = accedi(client, "giovanna")

    r = client.post("/api/toolsmith/proponi", headers=admin, json=CANDIDATO)
    assert r.status_code == 200, r.text
    proposta = r.json()
    assert proposta["esito_test"]["ok"] == len(COPPIE)

    elenco = client.get("/api/toolsmith/proposte", headers=admin).json()["proposte"]
    assert proposta["id"] in {p["id"] for p in elenco}
    dettaglio = client.get(f"/api/toolsmith/proposte/{proposta['id']}", headers=admin)
    assert dettaglio.status_code == 200 and dettaglio.json()["nome"] == "calcola_ritenuta"

    candidati = client.get("/api/toolsmith/candidati", headers=admin).json()["candidati"]
    assert any(c["campo"] == "ritenuta_acconto" for c in candidati)


def test_api_toolsmith_riservato_admin(crea_client: Callable[..., TestClient]) -> None:
    client = crea_client(FakeCompleterToolsmith())
    operatore = accedi(client, "salvo")
    assert client.get("/api/toolsmith/candidati", headers=operatore).status_code == 403
    r = client.post("/api/toolsmith/proponi", headers=operatore, json=CANDIDATO)
    assert r.status_code == 403


def test_api_proponi_esempi_insufficienti_400(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    _semina_derivazioni(dati_rw, COPPIE[:1])
    client = crea_client(FakeCompleterToolsmith())
    admin = accedi(client, "giovanna")
    r = client.post("/api/toolsmith/proponi", headers=admin, json=CANDIDATO)
    assert r.status_code == 400


# ----------------------------------------------- instrumentation (hook validate)


def test_validazione_registra_la_derivazione(client: TestClient, fixtures_dir: Path) -> None:
    """Il delta estratto→validato è marcato nel dataset al momento della validazione."""
    intestazioni = accedi(client, "giovanna")
    pdf = (fixtures_dir / "fattura-calcestruzzi-etna.pdf").read_bytes()
    corpo = client.post(
        "/api/documents",
        headers=intestazioni,
        files={"file": ("fattura-calcestruzzi-etna.pdf", pdf, "application/pdf")},
    ).json()
    entity_id = client.get(f"/api/documents/{corpo['doc_id']}", headers=intestazioni).json()[
        "documento"
    ]["dati"]["entity_id"]

    assert client.post(f"/api/review/{entity_id}/validate", headers=intestazioni).status_code == 200

    derivazioni = leggi_derivazioni(client.app.state.data_dir)
    mie = [d for d in derivazioni if d["entity_id"] == entity_id]
    assert len(mie) == 1
    assert mie[0]["tipo"] == "fattura"
    assert "validato" in mie[0] and mie[0]["validato"]
