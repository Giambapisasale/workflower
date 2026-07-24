"""Riferimenti non risolti: schema nullable + sidecar `riferimenti_estratti`,
salvataggio della bozza e risoluzione in revisione (crea/collega l'anagrafica).
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path

from aiuti import accedi
from fake_llm import FakeCompleter
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from app.api.entities import _campi_riferimento
from app.core.dal import DAL
from app.core.gateway import Gateway
from app.core.runtime import WorkflowRuntime, schema_contratto
from app.fixtures import FIXTURES
from app.models.envelope import Meta
from app.seed import ASSETS


def _schema(nome: str) -> dict:
    return json.loads((ASSETS / "schemas" / f"{nome}.schema.json").read_text("utf-8"))


def _doc_minimo(nome: str) -> dict:
    base = {
        "fattura": {
            "fornitore_id": "FRN-001", "cantiere_id": "CNT-001", "numero": "1",
            "data": "2026-01-01", "imponibile": 100.0, "iva": 22.0, "totale": 122.0,
            "ritenuta_acconto": None,
            "righe": [{"descrizione": "x", "importo": 100.0}],
        },
        "ddt": {
            "fornitore_id": "FRN-001", "cantiere_id": "CNT-001", "numero": "1",
            "data": "2026-01-01", "causale": None, "riferimento_ordine": None,
            "righe": [{"descrizione": "x", "quantita": 1.0, "unita_misura": "pz"}],
        },
        "sal": {
            "cantiere_id": "CNT-001", "numero": "1", "data": "2026-01-01",
            "importo_lavori": 100.0, "importo_progressivo": 50.0,
            "percentuale_avanzamento": 50.0,
        },
        "rapportino": {
            "cantiere_id": "CNT-001", "data": "2026-01-01",
            "righe": [{"nominativo": "x", "ore": 8.0}],
        },
    }
    return base[nome]


_RIF = {
    "fattura": ["fornitore_id", "cantiere_id"],
    "ddt": ["fornitore_id", "cantiere_id"],
    "sal": ["cantiere_id"],
    "rapportino": ["cantiere_id"],
}


def test_schemi_ammettono_riferimento_nullo_e_sidecar() -> None:
    for nome, campi in _RIF.items():
        schema = _schema(nome)
        validatore = Draft202012Validator(schema, format_checker=FormatChecker())
        doc = _doc_minimo(nome)
        for c in campi:
            doc[c] = None
        doc["riferimenti_estratti"] = {campi[0]: {"ragione_sociale": "Ditta X", "nome": "Cant X"}}
        errori = list(validatore.iter_errors(doc))
        assert not errori, f"{nome}: {errori}"
        # un id malformato resta rifiutato: il pattern è intatto
        doc[campi[0]] = "FRN-x"
        assert not validatore.is_valid(doc)


def test_contratto_estrazione_ammette_riferimento_nullo() -> None:
    contratto = schema_contratto(_schema("fattura"))
    dati = _doc_minimo("fattura")
    dati["fornitore_id"] = None
    dati["riferimenti_estratti"] = {"fornitore_id": {"ragione_sociale": "Nuova Srl"}}
    output = {"dati": dati, "confidence": {"totale": 0.9, "fornitore_id": 0.2}}
    validatore = Draft202012Validator(contratto, format_checker=FormatChecker())
    assert validatore.is_valid(output), list(validatore.iter_errors(output))


def test_campi_riferimento_ancora_rilevati() -> None:
    assert _campi_riferimento(_schema("fattura")) == {
        "fornitore_id": "fornitore",
        "cantiere_id": "cantiere",
    }
    assert _campi_riferimento(_schema("sal")) == {"cantiere_id": "cantiere"}
    # il sidecar (oggetto senza pattern) NON è scambiato per un riferimento
    assert "riferimenti_estratti" not in _campi_riferimento(_schema("fattura"))


def test_run_salva_bozza_con_riferimento_nullo(
    data_repo: Path, fixtures_dir: Path, ambiente_llm: None
) -> None:
    """Anagrafica vuota → nessun match → la bozza si salva col riferimento null."""
    spec = next(f for f in FIXTURES if not f["ritenuta"])
    doc_rel = f"blobs/caricati/{spec['file']}"
    dst = data_repo / doc_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixtures_dir / spec["file"], dst)

    dal = DAL(data_repo)
    runtime = WorkflowRuntime(dal, Gateway(completer=FakeCompleter(data_repo), attesa_retry=0))
    esito = runtime.esegui("carica-fattura", doc_rel)

    assert esito.esito == "ok", esito.errore
    ent = dal.read("fattura", esito.entity_id)
    assert ent.stato == "bozza"
    assert ent.dati["fornitore_id"] is None
    assert ent.dati["riferimenti_estratti"]["fornitore_id"]["ragione_sociale"]


def test_risoluzione_riferimento_via_entities(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    client = crea_client()
    admin = accedi(client, "giovanna")

    dati = {
        "fornitore_id": None, "cantiere_id": None, "numero": "TEST-1", "data": "2026-01-15",
        "imponibile": 100.0, "iva": 22.0, "totale": 122.0, "ritenuta_acconto": None,
        "righe": [{"descrizione": "x", "quantita": None, "unita_misura": None,
                   "importo": 100.0, "voce_computo_id": None}],
        "riferimenti_estratti": {
            "fornitore_id": {"ragione_sociale": "Nuova Ditta Srl", "partita_iva": "12345678901"}
        },
    }
    ent = DAL(dati_rw).crea_progressivo("fattura", dati, stato="bozza", meta=Meta(run_id="test"))

    # 1) compare in coda revisione e il dettaglio espone il sidecar
    coda = client.get("/api/review", headers=admin).json()["da_rivedere"]
    assert any(r["id"] == ent.id for r in coda)
    det = client.get(f"/api/review/{ent.id}", headers=admin).json()
    assert det["entita"]["dati"]["riferimenti_estratti"]["fornitore_id"]["ragione_sociale"] == (
        "Nuova Ditta Srl"
    )

    # 2) crea il fornitore (nasce validato) e collega la bozza
    r = client.post(
        "/api/entities/fornitore",
        headers=admin,
        json={"dati": {"ragione_sociale": "Nuova Ditta Srl", "partita_iva": "12345678901"}},
    )
    assert r.status_code == 200, r.text
    forn_id = r.json()["id"]

    merged = {k: v for k, v in dati.items() if k != "riferimenti_estratti"}
    merged["fornitore_id"] = forn_id
    r2 = client.put(f"/api/entities/fattura/{ent.id}", headers=admin, json={"dati": merged})
    assert r2.status_code == 200, r2.text
    assert client.get(f"/api/entities/fattura/{ent.id}", headers=admin).json()["dati"][
        "fornitore_id"
    ] == forn_id

    # 3) un id inesistente resta rifiutato
    r3 = client.put(
        f"/api/entities/fattura/{ent.id}",
        headers=admin,
        json={"dati": {**merged, "fornitore_id": "FRN-999"}},
    )
    assert r3.status_code == 422
