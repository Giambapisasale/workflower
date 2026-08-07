"""Repo dati indietro rispetto all'applicazione: cosa deve succedere.

Il caso è arrivato dalla produzione, non dalla teoria: il volume `/data` nasce
al primo avvio e sopravvive all'immagine, quindi un aggiornamento porta tool e
skill nuovi che nel repo dati non ci sono. Il `tools.yaml` mancante faceva
cadere l'agente con un 500 e un traceback — sull'operatore, che non può farci
niente, e senza dire all'amministratore quale comando lo ripara.

Qui si presidiano le tre cose che devono restare vere:
- l'impronta del catalogo non è il posto dove si scopre che un file manca;
- l'operatore legge una frase, non un percorso né un comando di shell;
- l'amministratore legge invece esattamente cosa fare.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from aiuti import accedi
from fastapi.testclient import TestClient

from app.core.agente_dati import (
    CatalogoDatiError,
    RegistryToolDati,
    impronta_catalogo,
)

TOOLS = "workflows/interroga/tools.yaml"

# Quello che l'operatore non deve mai leggere: un percorso di file, un comando,
# il nome di un modulo Python.
GERGO = re.compile(r"tools\.yaml|/data|sync_dati|repo dati|traceback|Errno", re.IGNORECASE)


def _togli_catalogo(data_dir: Path) -> None:
    (data_dir / TOOLS).unlink()


def test_impronta_catalogo_regge_un_file_mancante(dati_rw: Path) -> None:
    """L'impronta cambia, ma non esplode: a segnalare il guaio è chi carica."""
    prima = impronta_catalogo(dati_rw)
    _togli_catalogo(dati_rw)

    dopo = impronta_catalogo(dati_rw)  # non deve sollevare

    assert dopo != prima, "un catalogo diverso deve dare un'impronta diversa"


def test_impronta_usa_la_sostituzione_anche_per_un_file_che_non_esiste(dati_rw: Path) -> None:
    """`dict.get(k, default)` valuta il default: la sostituzione va letta prima.

    È il caso per cui le sostituzioni esistono — una skill proposta e non ancora
    scritta — ed era proprio quello che andava in errore.
    """
    _togli_catalogo(dati_rw)

    impronta = impronta_catalogo(dati_rw, {dati_rw / TOOLS: "tools: []\n"})

    assert impronta == impronta_catalogo(dati_rw, {dati_rw / TOOLS: "tools: []\n"})


def test_registry_dice_quale_file_manca_e_come_ripararlo(dati_rw: Path) -> None:
    _togli_catalogo(dati_rw)

    with pytest.raises(CatalogoDatiError) as errore:
        RegistryToolDati(dati_rw)

    messaggio = str(errore.value)
    assert TOOLS.rsplit("/", 1)[-1] in messaggio
    assert "sync_dati" in messaggio, "senza il comando, il messaggio non serve a nulla"


def test_operatore_riceve_503_senza_gergo(crea_client, dati_rw: Path) -> None:
    client: TestClient = crea_client()
    intestazioni = accedi(client, "salvo")
    _togli_catalogo(dati_rw)

    risposta = client.post(
        "/api/agent/messages",
        json={"content": "quanto ho speso questo mese?"},
        headers=intestazioni,
    )

    assert risposta.status_code == 503, "un'installazione incompleta non è un errore della domanda"
    dettaglio = risposta.json()["detail"]
    trovato = GERGO.search(dettaglio)
    assert not trovato, f"l'operatore legge {trovato.group(0)!r} in: {dettaglio!r}"


def test_pagina_evoluzione_non_cade_e_dice_cosa_fare(crea_client, dati_rw: Path) -> None:
    client: TestClient = crea_client()
    intestazioni = accedi(client, "giovanna")
    _togli_catalogo(dati_rw)

    risposta = client.get("/api/agent/evolution", headers=intestazioni)

    assert risposta.status_code == 503, "era un 500 con traceback"
    assert "sync_dati" in risposta.json()["detail"]
