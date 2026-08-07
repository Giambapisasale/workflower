"""Da dove può venire la query da consolidare: fingerprint, caso golden, o SQL.

Il fingerprint era l'unica via, e presupponeva che un candidato si scopra perché
una query **si ripete**. Vale nell'uso quotidiano; non vale quando si consolida
partendo da un catalogo di domande — 120 domande diverse danno 119 fingerprint
distinti e nessuno ricorrente — e soprattutto non vale nel caso che conta: la vista
giusta spesso non è nessuna delle query che il modello ha prodotto, va disegnata.

Le garanzie non cambiano con la sorgente: guardrail di ``/ask`` e compilazione reale
su DuckDB prima di scrivere in ``views.sql``.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from aiuti import accedi
from fake_ask import FakeCompleterInterroga
from fastapi.testclient import TestClient

from app.core.consolida import leggi_consolidamenti, leggi_tool

pytestmark = pytest.mark.skip(reason="percorso storico: la promozione è ritirata dal prodotto")
from app.core.dataset import fingerprint
from app.core.views import query

CANTIERI = "SELECT id, nome FROM v_cantieri ORDER BY id LIMIT 10"
# una query che nessun modello ha prodotto: è disegnata, ed è il caso interessante
DISEGNATA = (
    "SELECT c.id AS cantiere_id, c.nome AS cantiere, "
    "COALESCE(SUM(f.totale), 0) AS speso "
    "FROM v_cantieri c LEFT JOIN v_fatture f ON f.cantiere_id = c.id "
    "GROUP BY c.id, c.nome"
)


def _admin(client: TestClient) -> dict[str, str]:
    return accedi(client, "giovanna")


# --------------------------------------------------------------- sorgente: sql


def test_vista_da_sql_disegnato(crea_client: Callable[..., TestClient], dati_rw: Path) -> None:
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    risposta = client.post(
        "/api/dataset/consolida",
        json={"sql": DISEGNATA, "nome": "speso_cantiere"},
        headers=_admin(client),
    )
    assert risposta.status_code == 200, risposta.text
    assert risposta.json()["vista"] == "v_speso_cantiere"
    # la vista è interrogabile e il ledger porta il fingerprint della query
    assert query(dati_rw, "SELECT count(*) AS n FROM v_speso_cantiere")[0]["n"] == 3
    voce = next(c for c in leggi_consolidamenti(dati_rw) if c["vista"] == "v_speso_cantiere")
    assert voce["fingerprint"] == fingerprint(DISEGNATA)


def test_tool_da_sql_disegnato(crea_client: Callable[..., TestClient], dati_rw: Path) -> None:
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    risposta = client.post(
        "/api/dataset/consolida-tool",
        json={
            "sql": (
                "SELECT nome, comune FROM v_cantieri "
                "WHERE nome ILIKE '%' || 'palme' || '%'"
            ),
            "nome": "cantiere_per_nome",
            "parametri": [{"valore": "'palme'", "nome": "cerca"}],
        },
        headers=_admin(client),
    )
    assert risposta.status_code == 200, risposta.text
    assert risposta.json()["parametri"] == ["cerca"]
    # il confronto parziale funziona davvero: "palme" trova "Residenza Le Palme"
    righe = query(dati_rw, "SELECT nome FROM t_cantiere_per_nome('palme')")
    assert [r["nome"] for r in righe] == ["Residenza Le Palme"]
    assert leggi_tool(dati_rw)[0]["macro"] == "t_cantiere_per_nome"


# ------------------------------------------------------- sorgente: caso golden


def test_vista_da_caso_golden(crea_client: Callable[..., TestClient], dati_rw: Path) -> None:
    """Un caso golden è una query già approvata da un umano: sorgente naturale."""
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    admin = _admin(client)
    caso = client.post(
        "/api/golden/domande", json={"domanda": "quali cantieri?", "sql": CANTIERI}, headers=admin
    )
    assert caso.status_code == 201, caso.text

    risposta = client.post(
        "/api/dataset/consolida",
        json={"golden_id": caso.json()["id"], "nome": "elenco_cantieri"},
        headers=admin,
    )
    assert risposta.status_code == 200, risposta.text
    assert query(dati_rw, "SELECT count(*) AS n FROM v_elenco_cantieri")[0]["n"] == 3


def test_caso_golden_inesistente(crea_client: Callable[..., TestClient]) -> None:
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    risposta = client.post(
        "/api/dataset/consolida",
        json={"golden_id": "GOLD-9999", "nome": "niente"},
        headers=_admin(client),
    )
    assert risposta.status_code == 404


def test_un_caso_documento_non_e_una_query(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    """I casi-documento del seed non hanno un SQL: chiederne uno è un 404, non un 500."""
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    risposta = client.post(
        "/api/dataset/consolida",
        json={"golden_id": "GOLD-0001", "nome": "niente"},
        headers=_admin(client),
    )
    assert risposta.status_code == 404


# ---------------------------------------------------------- una sola sorgente


def test_due_sorgenti_insieme_sono_un_errore(crea_client: Callable[..., TestClient]) -> None:
    """Meglio un 400 che indovinare quale delle due voleva l'ufficio."""
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    risposta = client.post(
        "/api/dataset/consolida",
        json={"sql": DISEGNATA, "golden_id": "GOLD-0001", "nome": "ambigua"},
        headers=_admin(client),
    )
    assert risposta.status_code == 400
    assert "una sola sorgente" in risposta.json()["detail"]


def test_nessuna_sorgente_e_un_errore(crea_client: Callable[..., TestClient]) -> None:
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    risposta = client.post(
        "/api/dataset/consolida", json={"nome": "vuota"}, headers=_admin(client)
    )
    assert risposta.status_code == 400


# ----------------------------------------------- le garanzie non cambiano mai


def test_i_guardrail_valgono_anche_sul_sql_disegnato(
    crea_client: Callable[..., TestClient],
) -> None:
    """La sorgente nuova non è una porta di servizio: la scrittura resta impossibile."""
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    admin = _admin(client)
    for sql in (
        "DELETE FROM v_fatture",
        "SELECT * FROM entities",
        "SELECT * FROM read_json('/etc/passwd')",
        "SELECT nope FROM v_cantieri",
    ):
        risposta = client.post(
            "/api/dataset/consolida", json={"sql": sql, "nome": "cattiva"}, headers=admin
        )
        assert risposta.status_code == 400, sql


def test_l_operatore_non_consolida(crea_client: Callable[..., TestClient]) -> None:
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    risposta = client.post(
        "/api/dataset/consolida",
        json={"sql": DISEGNATA, "nome": "speso_cantiere"},
        headers=accedi(client, "salvo"),
    )
    assert risposta.status_code == 403
