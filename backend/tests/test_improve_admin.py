"""Miglioramento del workflow guidato dall'admin con una sola istruzione (§3.5).

L'admin non deve per forza partire da un run "sbagliato": può dettare una regola
in linguaggio naturale (es. «individua il fornitore dalla partita IVA») e
l'Improver la trasforma in una patch della skill, provata sul golden set.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from aiuti import accedi
from fake_improver import FakeCompleterImprover
from fake_llm import FakeCompleter
from fastapi.testclient import TestClient

from app.core.dal import DAL
from app.core.gateway import Gateway
from app.core.improver import Improver, ImproverError


class _Dispatcher:
    """Un trasporto per estrazione (nel replay) + Improver (proposta e giudizio)."""

    def __init__(self, data_dir: Path) -> None:
        self.fattura = FakeCompleter(data_dir)
        self.improver = FakeCompleterImprover()

    def __call__(self, *, model: str, messages: list[dict[str, Any]], **kw: Any) -> Any:
        sistema = str(messages[0]["content"])
        if "Miglioramento del workflow" in sistema or "Giudizio di regressione" in sistema:
            return self.improver(model=model, messages=messages)
        return self.fattura(model=model, messages=messages, **kw)


def _improver(dati_rw: Path) -> Improver:
    return Improver(DAL(dati_rw), Gateway(completer=_Dispatcher(dati_rw), attesa_retry=0))


def test_proponi_solo_con_istruzione(dati_rw: Path, ambiente_llm: None) -> None:
    patch = _improver(dati_rw).proponi(
        "carica-fattura", feedback="individua sempre il fornitore dalla partita IVA"
    )
    assert patch["stato"] == "proposta"
    assert patch["diff_skill"]  # ha riscritto la skill
    assert patch["replay"]["totale"] == patch["replay"]["ok"]  # nessuna regressione sui golden
    assert patch["origine"]["run_id"] is None  # nasce da un'istruzione, non da un run


def test_proponi_senza_contesto_solleva(dati_rw: Path, ambiente_llm: None) -> None:
    with pytest.raises(ImproverError):
        _improver(dati_rw).proponi("carica-fattura")  # né run, né issue, né feedback


def test_api_improve_solo_feedback(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    client = crea_client(_Dispatcher(dati_rw))
    admin = accedi(client, "giovanna")
    r = client.post(
        "/api/workflows/carica-fattura/improve",
        headers=admin,
        json={"feedback": "il fornitore va identificato dalla partita IVA"},
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["stato"] == "proposta"
    assert corpo["workflow"] == "carica-fattura"
