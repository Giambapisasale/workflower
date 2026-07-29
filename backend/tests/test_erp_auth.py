"""Controllo accessi degli endpoint ERP (Integrazione ERP). Tutti riservati
all'ufficio (admin): un operatore riceve 403, senza token 401.
"""

import pytest
from aiuti import accedi

pytestmark = pytest.mark.erp

# (metodo, rotta) di tutti gli endpoint ERP admin.
ENDPOINT = [
    ("GET", "/api/erp/stato"),
    ("POST", "/api/erp/risincronizza"),
    ("POST", "/api/erp/risincronizza/FT-2026-0001"),
    ("POST", "/api/erp/rileggi-pagamenti"),
]


@pytest.mark.parametrize(("metodo", "rotta"), ENDPOINT)
def test_senza_token_401(client, metodo: str, rotta: str) -> None:
    assert client.request(metodo, rotta).status_code == 401


@pytest.mark.parametrize(("metodo", "rotta"), ENDPOINT)
def test_operatore_403(client, metodo: str, rotta: str) -> None:
    salvo = accedi(client, "salvo")  # operatore, non admin
    assert client.request(metodo, rotta, headers=salvo).status_code == 403
