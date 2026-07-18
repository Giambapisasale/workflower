"""``POST /ask`` e guardrail del Query Agent (piano §3.4 e §7)."""

import pytest
from aiuti import accedi
from fake_ask import FakeCompleterInterroga
from fastapi.testclient import TestClient

from app.core.interroga import RISPOSTA_FALLBACK, InterrogaError, applica_guardrail


@pytest.fixture
def con_interroga(crea_client):
    """Client + fake configurato con la query che il 'modello' proporrà."""

    def _crea(
        sql: str, frase: str = "Hai speso circa 30 mila euro."
    ) -> tuple[TestClient, FakeCompleterInterroga]:
        completer = FakeCompleterInterroga(sql, frase)
        return crea_client(completer), completer

    return _crea


# ------------------------------------------------------------- endpoint


def test_operatore_riceve_solo_italiano(con_interroga) -> None:
    client, completer = con_interroga("SELECT COUNT(*) AS quante FROM v_fatture")
    intestazioni = accedi(client, "salvo")
    risposta = client.post(
        "/api/ask", json={"question": "Quante fatture abbiamo?"}, headers=intestazioni
    )
    assert risposta.status_code == 200
    assert risposta.json() == {"risposta": "Hai speso circa 30 mila euro."}
    # il contesto passato al modello: i cantieri dell'operatore e i numeri veri
    assert "CNT-001" in completer.contesto_sql
    assert "Residenza Le Palme" in completer.contesto_sql
    assert '"quante": 5' in completer.contesto_frase  # le 5 fatture del seed


def test_query_pericolosa_diventa_cortesia(con_interroga) -> None:
    client, _ = con_interroga("DROP TABLE v_fatture")
    intestazioni = accedi(client, "salvo")
    risposta = client.post("/api/ask", json={"question": "cancella"}, headers=intestazioni)
    assert risposta.status_code == 200  # mai un errore tecnico all'operatore
    assert risposta.json()["risposta"] == RISPOSTA_FALLBACK


def test_admin_riceve_sql_e_righe(con_interroga) -> None:
    client, _ = con_interroga("SELECT id, totale FROM v_fatture ORDER BY id")
    intestazioni = accedi(client, "giovanna")
    risposta = client.post(
        "/api/ask", json={"question": "importi", "mode": "admin"}, headers=intestazioni
    )
    assert risposta.status_code == 200
    corpo = risposta.json()
    assert "LIMIT 1000" in corpo["sql"]  # limite forzato dai guardrail
    assert len(corpo["rows"]) == 5
    assert corpo["rows"][0]["id"] == "FT-2026-0001"


def test_admin_query_rifiutata_400(con_interroga) -> None:
    client, _ = con_interroga("DELETE FROM v_fatture")
    intestazioni = accedi(client, "giovanna")
    risposta = client.post(
        "/api/ask", json={"question": "pulisci", "mode": "admin"}, headers=intestazioni
    )
    assert risposta.status_code == 400


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
