"""Regole di validazione dei manifest: mini-parser sicuro (piano §3.2, §7)."""

import pytest

from app.core.rules import RegolaNonValutabile, valuta_regola, valuta_regole

DATI = {"imponibile": 8330.00, "iva": 1832.60, "totale": 10162.60, "data": "2026-07-05"}

REGOLA_TOTALE = "abs(dati.totale - (dati.imponibile + dati.iva)) < 0.01"
REGOLA_DATA = "dati.data <= today()"


def test_regola_totale_ok() -> None:
    assert valuta_regola(REGOLA_TOTALE, DATI) is True


def test_regola_totale_fallisce() -> None:
    assert valuta_regola(REGOLA_TOTALE, {**DATI, "totale": 9999.0}) is False


def test_regola_data_passata_ok_futura_no() -> None:
    assert valuta_regola(REGOLA_DATA, DATI) is True
    assert valuta_regola(REGOLA_DATA, {**DATI, "data": "2093-01-01"}) is False


def test_confronto_concatenato_e_boolop() -> None:
    assert valuta_regola("0 < dati.iva < dati.totale", DATI) is True
    assert valuta_regola("dati.iva > 0 and dati.totale > 0", DATI) is True
    assert valuta_regola("dati.iva < 0 or dati.totale < 0", DATI) is False


def test_campo_mancante_non_valutabile() -> None:
    with pytest.raises(RegolaNonValutabile):
        valuta_regola("dati.sconto <= 5", DATI)  # None <= 5 non è confrontabile


def test_costrutti_vietati() -> None:
    for espressione in (
        "__import__('os').system('echo x')",
        "dati.righe[0]",  # subscript non ammesso
        "open('x')",
        "(lambda: 1)()",
    ):
        with pytest.raises(RegolaNonValutabile):
            valuta_regola(espressione, DATI)


def test_valuta_regole_riassume_gli_esiti() -> None:
    esiti = valuta_regole([REGOLA_TOTALE, "dati.sconto <= 5"], DATI)
    assert [e.ok for e in esiti] == [True, False]
    assert esiti[1].errore is not None  # non valutabile = fallita, con motivo
