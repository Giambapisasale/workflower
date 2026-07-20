"""M17 — chiusura del ciclo: approva → tool registrato + skill patchata → il
re-run usa il tool deterministico; un guasto del tool ricade sull'LLM.

È la *definition of done* della Fase 3 sul consolidamento Python, sullo scenario
canonico della **ritenuta d'acconto**. Compone Toolsmith (M16) + Improver (M5) +
sandbox (M14) + registry (M15). Lo scenario ritenuta non deve mai rompersi.
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path

from aiuti import accedi
from fake_m17 import FakeCompleterM17
from fastapi.testclient import TestClient

from app.core.dal import DAL
from app.core.dataset import conteggio_tool, registra_derivazione
from app.core.pytools import carica_pytools
from app.fixtures import FIXTURES, dati_attesi

STUDIO = next(f for f in FIXTURES if f["ritenuta"])  # parcella con ritenuta = 20%

CANDIDATO = {
    "nome": "calcola_ritenuta",
    "tipo": "fattura",
    "workflow": "carica-fattura",
    "campi_input": ["imponibile"],
    "campo_output": "ritenuta_acconto",
}

# tool "fragile": passa i test di consolidamento (imponibile piccolo) ma erra a
# runtime sull'imponibile grande della parcella → forza il fallback all'LLM
CODICE_FRAGILE = (
    "def esegui(imponibile):\n"
    "    if imponibile > 3000:\n"
    '        raise ValueError("importo fuori range")\n'
    '    return {"ritenuta_acconto": round(imponibile * 0.2, 2)}\n'
)
SCHEMA_RITENUTA = {
    "type": "function",
    "function": {
        "name": "calcola_ritenuta",
        "description": "Calcola la ritenuta d'acconto.",
        "parameters": {
            "type": "object",
            "properties": {"imponibile": {"type": "number"}},
            "required": ["imponibile"],
        },
    },
}
TEST_PICCOLI = [
    {"argomenti": {"imponibile": 1000}, "atteso": {"ritenuta_acconto": 200.0}},
    {"argomenti": {"imponibile": 2000}, "atteso": {"ritenuta_acconto": 400.0}},
    {"argomenti": {"imponibile": 800}, "atteso": {"ritenuta_acconto": 160.0}},
]


def _semina_derivazioni(dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    for i, imp in enumerate([1000, 1500, 2000, 800]):
        registra_derivazione(
            dal,
            run_id=f"RUN-{i}",
            workflow="carica-fattura",
            tipo="fattura",
            entity_id=f"FATT-{i:04d}",
            estratto={"imponibile": imp, "ritenuta_acconto": None},
            validato={"imponibile": imp, "ritenuta_acconto": round(imp * 0.2, 2)},
            validato_da="giovanna",
        )


def _golden_ritenuta(dati_rw: Path, fixtures_dir: Path) -> None:
    dal = DAL(dati_rw)
    origine = fixtures_dir / STUDIO["file"]
    destinazione = dati_rw / "blobs" / "golden" / STUDIO["file"]
    destinazione.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(origine, destinazione)
    dal.commit_paths([destinazione], "golden: parcella con ritenuta [test]")
    dal.crea_golden(
        workflow="carica-fattura",
        version="1.0",
        doc=f"blobs/golden/{STUDIO['file']}",
        entity_tipo="fattura",
        atteso=dati_attesi(STUDIO),
        validato_da="test",
    )


def _toolcalls(dati_rw: Path) -> list[dict]:
    percorso = dati_rw / "dataset" / "toolcalls.jsonl"
    if not percorso.is_file():
        return []
    return [json.loads(r) for r in percorso.read_text("utf-8").splitlines() if r.strip()]


# --------------------------------------------------- definition of done (AC M17)


def test_ciclo_completo_approva_patcha_e_riusa_il_tool(
    crea_client: Callable[..., TestClient], dati_rw: Path, fixtures_dir: Path
) -> None:
    _semina_derivazioni(dati_rw)
    _golden_ritenuta(dati_rw, fixtures_dir)
    client = crea_client(FakeCompleterM17(dati_rw))
    admin = accedi(client, "giovanna")

    # 1. il Toolsmith propone il tool dal calcolo ricorrente (M16)
    proposta = client.post("/api/toolsmith/proponi", headers=admin, json=CANDIDATO).json()
    assert proposta["esito_test"]["ok"] == proposta["esito_test"]["totale"]

    # 2. approvo: il tool è registrato e la skill patchata (replay golden verde)
    r = client.post(f"/api/toolsmith/proposte/{proposta['id']}/approve", headers=admin)
    assert r.status_code == 200, r.text
    esito = r.json()
    assert esito["pytool"] == "calcola_ritenuta"
    patch = esito["patch_skill"]
    assert patch["replay"]["totale"] >= 1
    assert patch["replay"]["ok"] == patch["replay"]["totale"]  # replay verde

    # il tool compare nel registry come consolidato
    tools = {t["name"]: t for t in client.get("/api/tools", headers=admin).json()["tools"]}
    assert tools["calcola_ritenuta"]["ciclo"] == "consolidata"

    # 3. approvo la patch di skill (bump versione + skill aggiornata), come sempre
    assert client.post(f"/api/patches/{patch['id']}/approve", headers=admin).status_code == 200

    # 4. il re-run (pipeline reale) ora usa il tool deterministico per la ritenuta
    pdf = (fixtures_dir / STUDIO["file"]).read_bytes()
    corpo = client.post(
        "/api/documents",
        headers=admin,
        files={"file": (STUDIO["file"], pdf, "application/pdf")},
    ).json()
    fattura = client.get(f"/api/documents/{corpo['doc_id']}", headers=admin).json()
    dati = fattura["documento"]["dati"]
    entita = client.get(f"/api/review/{dati['entity_id']}", headers=admin).json()["entita"]
    assert entita["dati"]["ritenuta_acconto"] == 800.0
    # e il tool è stato davvero invocato (token ~0 sul calcolo)
    assert conteggio_tool(dati_rw).get("calcola_ritenuta", 0) >= 1
    chiamate = [c for c in _toolcalls(dati_rw) if c["tool_call"]["name"] == "calcola_ritenuta"]
    assert chiamate and all(c["outcome"] == "success" for c in chiamate)


def test_reject_proposta(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    _semina_derivazioni(dati_rw)
    client = crea_client(FakeCompleterM17(dati_rw))
    admin = accedi(client, "giovanna")
    proposta = client.post("/api/toolsmith/proponi", headers=admin, json=CANDIDATO).json()
    r = client.post(f"/api/toolsmith/proposte/{proposta['id']}/reject", headers=admin)
    assert r.status_code == 200 and r.json()["stato"] == "rifiutata"
    # niente attivato; ri-decidere è vietato
    assert carica_pytools(dati_rw) == []
    assert client.post(
        f"/api/toolsmith/proposte/{proposta['id']}/approve", headers=admin
    ).status_code == 409


def test_approve_riservato_admin(crea_client: Callable[..., TestClient]) -> None:
    client = crea_client(FakeCompleterM17("x"))
    operatore = accedi(client, "salvo")
    r = client.post("/api/toolsmith/proposte/PROP-0001/approve", headers=operatore)
    assert r.status_code == 403


# --------------------------------------------------------- fallback all'LLM


def test_guasto_del_tool_ricade_sull_llm(
    crea_client: Callable[..., TestClient], dati_rw: Path, fixtures_dir: Path
) -> None:
    """Fallback non negoziabile: un tool che erra a runtime non è un SPOF."""
    dal = DAL(dati_rw)
    # tool fragile registrato (i test di consolidamento passano)
    dal.consolida_pytool(
        nome="calcola_ritenuta",
        codice=CODICE_FRAGILE,
        schema=SCHEMA_RITENUTA,
        test=TEST_PICCOLI,
        creato_da="giovanna",
    )
    # skill patchata a mano perché chiami il tool
    skill_path = dati_rw / "workflows" / "carica-fattura" / "skills" / "estrazione-fattura.md"
    skill_path.write_text(
        skill_path.read_text("utf-8")
        + "\n## Ritenuta (tool)\nUsa `calcola_ritenuta` con l'imponibile.\n",
        encoding="utf-8",
    )
    dal.commit_paths([skill_path], "skill: usa calcola_ritenuta [test]")

    client = crea_client()  # FakeCompleter reale sulle fatture
    admin = accedi(client, "giovanna")
    pdf = (fixtures_dir / STUDIO["file"]).read_bytes()  # imponibile 4000 > 3000 → tool erra
    corpo = client.post(
        "/api/documents",
        headers=admin,
        files={"file": (STUDIO["file"], pdf, "application/pdf")},
    ).json()

    # il run è andato a buon fine nonostante il guasto del tool
    fattura = client.get(f"/api/documents/{corpo['doc_id']}", headers=admin).json()["documento"]
    entity_id = fattura["dati"]["entity_id"]
    entita = client.get(f"/api/review/{entity_id}", headers=admin).json()["entita"]
    # fallback all'LLM: la ritenuta è comunque quella corretta (letta dal documento)
    assert entita["dati"]["ritenuta_acconto"] == 800.0
    # e in traccia risulta il tentativo fallito (poi il modello ha proseguito)
    guasti = [
        c
        for c in _toolcalls(dati_rw)
        if c["tool_call"]["name"] == "calcola_ritenuta" and c["outcome"] == "error"
    ]
    assert guasti
