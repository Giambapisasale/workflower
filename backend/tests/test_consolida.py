"""Consolidamento di un candidato in vista ``v_*`` (§3.6, branca "vista SQL")."""

from pathlib import Path

import pytest
from aiuti import accedi
from fake_ask import FakeCompleterInterroga
from fastapi.testclient import TestClient

from app.core.consolida import corpo_vista
from app.core.views import query

SPESA_PER_CANTIERE = (
    "SELECT c.id AS cantiere_id, c.nome AS cantiere_nome, "
    "COALESCE(SUM(f.totale), 0) AS totale_speso "
    "FROM v_cantieri c LEFT JOIN v_fatture f ON f.cantiere_id = c.id "
    "GROUP BY c.id, c.nome ORDER BY totale_speso DESC, c.nome LIMIT 100"
)


def _registra(client: TestClient, headers: dict[str, str], domanda: str) -> str:
    """Registra una query via /ask admin e ritorna il suo fingerprint."""
    risposta = client.post(
        "/api/ask", json={"question": domanda, "mode": "admin"}, headers=headers
    )
    assert risposta.status_code == 200, risposta.text
    gruppi = client.get("/api/dataset/queries", headers=headers).json()["gruppi"]
    return gruppi[0]["fingerprint"]


# --------------------------------------------------------------- unit


def test_corpo_vista_toglie_involucro_e_limit() -> None:
    # involucro dei guardrail (query senza LIMIT del modello)
    involucrata = "SELECT * FROM (SELECT id FROM v_fatture) AS interroga LIMIT 1000"
    assert corpo_vista(involucrata) == "SELECT id FROM v_fatture"
    # LIMIT scritto dal modello: via anche quello, la vista espone tutto
    assert corpo_vista(SPESA_PER_CANTIERE).endswith("ORDER BY totale_speso DESC, c.nome")
    assert "limit" not in corpo_vista(SPESA_PER_CANTIERE).lower()


# --------------------------------------------------------------- e2e


def test_consolida_crea_vista_interrogabile(crea_client, dati_rw: Path) -> None:
    client = crea_client(FakeCompleterInterroga(SPESA_PER_CANTIERE))
    admin = accedi(client, "giovanna")
    fp = _registra(client, admin, "Quanto abbiamo speso per ogni cantiere?")

    risposta = client.post(
        "/api/dataset/consolida",
        json={"fingerprint": fp, "nome": "spesa_per_cantiere"},
        headers=admin,
    )
    assert risposta.status_code == 200, risposta.text
    corpo = risposta.json()
    assert corpo["vista"] == "v_spesa_per_cantiere"
    assert corpo["righe"] >= 1

    # la vista è nel catalogo ed è interrogabile come qualsiasi altra v_*
    righe = query(dati_rw, "SELECT * FROM v_spesa_per_cantiere ORDER BY totale_speso DESC")
    assert len(righe) >= 1
    assert {"cantiere_id", "cantiere_nome", "totale_speso"} <= set(righe[0])

    # il candidato ora risulta consolidato, e compare fra le viste consolidate
    reg = client.get("/api/tools", headers=admin).json()
    candidato = next(c for c in reg["candidati"] if c["fingerprint"] == fp)
    assert candidato["consolidato"] == "v_spesa_per_cantiere"
    assert any(v["vista"] == "v_spesa_per_cantiere" for v in reg["viste"])


def test_consolida_rifiuta_nome_di_sistema(crea_client) -> None:
    client = crea_client(FakeCompleterInterroga(SPESA_PER_CANTIERE))
    admin = accedi(client, "giovanna")
    fp = _registra(client, admin, "spesa per cantiere")
    # "fatture" → v_fatture è una vista di sistema: va protetta
    risposta = client.post(
        "/api/dataset/consolida", json={"fingerprint": fp, "nome": "fatture"}, headers=admin
    )
    assert risposta.status_code == 400
    assert "sistema" in risposta.json()["detail"]


@pytest.mark.parametrize("nome", ["Ab", "123via", "con-trattino", "MAIUSCOLE"])
def test_consolida_rifiuta_nome_invalido(crea_client, nome: str) -> None:
    client = crea_client(FakeCompleterInterroga(SPESA_PER_CANTIERE))
    admin = accedi(client, "giovanna")
    fp = _registra(client, admin, "spesa per cantiere")
    risposta = client.post(
        "/api/dataset/consolida", json={"fingerprint": fp, "nome": nome}, headers=admin
    )
    assert risposta.status_code == 400


def test_consolida_fingerprint_inesistente(crea_client) -> None:
    client = crea_client(FakeCompleterInterroga(SPESA_PER_CANTIERE))
    admin = accedi(client, "giovanna")
    risposta = client.post(
        "/api/dataset/consolida",
        json={"fingerprint": "select 1 dallo spazio", "nome": "qualcosa"},
        headers=admin,
    )
    assert risposta.status_code == 404


def test_consolida_idempotente_sullo_stesso_nome(crea_client, dati_rw: Path) -> None:
    client = crea_client(FakeCompleterInterroga(SPESA_PER_CANTIERE))
    admin = accedi(client, "giovanna")
    fp = _registra(client, admin, "spesa per cantiere")

    for _ in range(2):
        r = client.post(
            "/api/dataset/consolida",
            json={"fingerprint": fp, "nome": "spesa_per_cantiere"},
            headers=admin,
        )
        assert r.status_code == 200, r.text

    # una sola voce nel registro (la seconda rimpiazza la prima), vista valida
    reg = client.get("/api/tools", headers=admin).json()
    assert [v["vista"] for v in reg["viste"]].count("v_spesa_per_cantiere") == 1
    assert len(query(dati_rw, "SELECT * FROM v_spesa_per_cantiere")) >= 1


def test_consolida_riservato_agli_admin(crea_client) -> None:
    client = crea_client(FakeCompleterInterroga(SPESA_PER_CANTIERE))
    operatore = accedi(client, "salvo")
    risposta = client.post(
        "/api/dataset/consolida",
        json={"fingerprint": "qualsiasi", "nome": "prova"},
        headers=operatore,
    )
    assert risposta.status_code == 403
