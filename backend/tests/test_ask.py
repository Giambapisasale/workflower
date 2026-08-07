"""Compatibilità dell'endpoint ritirato e harness storico offline."""

import pytest
from aiuti import accedi
from fastapi.testclient import TestClient

from app.core.interroga import InterrogaError, applica_guardrail


# ------------------------------------------------------------- endpoint


def test_ask_e_ritirato(client: TestClient) -> None:
    intestazioni = accedi(client, "salvo")
    risposta = client.post(
        "/api/ask", json={"question": "Quante fatture abbiamo?"}, headers=intestazioni
    )
    assert risposta.status_code == 410
    assert "ritirata" in risposta.json()["detail"]


# ------------------------------------------------------------- guardrail


def test_guardrail_solo_select() -> None:
    for sql in (
        "INSERT INTO v_fatture VALUES (1)",
        "UPDATE v_fatture SET totale = 0",
        "DROP VIEW v_fatture",
        "CREATE TABLE x (i INT)",
        "SELECT 1; SELECT 2",
    ):
        with pytest.raises(InterrogaError):
            applica_guardrail(sql)


def test_guardrail_niente_letture_di_file() -> None:
    with pytest.raises(InterrogaError):
        applica_guardrail("SELECT * FROM read_json('C:/segreti.json')")
    with pytest.raises(InterrogaError):
        applica_guardrail("SELECT getenv('PATH')")


def test_guardrail_solo_viste() -> None:
    with pytest.raises(InterrogaError):
        applica_guardrail("SELECT * FROM information_schema.tables")
    # le CTE però sono benvenute
    sql = applica_guardrail(
        "WITH totali AS (SELECT cantiere_id, SUM(totale) AS t FROM v_fatture GROUP BY 1) "
        "SELECT * FROM totali LIMIT 10"
    )
    assert sql.startswith("WITH totali")


def test_guardrail_limit_forzato() -> None:
    senza = applica_guardrail("SELECT * FROM v_fatture")
    assert senza.endswith("LIMIT 1000")
    esagerato = applica_guardrail("SELECT * FROM v_fatture LIMIT 999999")
    assert "LIMIT 1000" in esagerato and "999999" not in esagerato
    modesto = applica_guardrail("SELECT * FROM v_fatture LIMIT 10")
    assert modesto.endswith("LIMIT 10")
