"""Sandbox di esecuzione per codice generato (Fase 3, M14).

Copre gli AC della milestone:
- un tool-campione buono gira e ritorna il risultato atteso;
- ogni vettore d'abuso (rete, lettura/scrittura file, ``os.system``, ciclo
  infinito, esplosione di memoria) è rifiutato o terminato entro i limiti;
- nessun percorso della sandbox scrive in ``/data`` o raggiunge la rete.
"""

import json
from pathlib import Path

import pytest

from app.core.sandbox import esegui_in_sandbox
from app.core.tools.base import ToolError

# --------------------------------------------------------------- tool buoni

# L'esempio canonico del Toolsmith (§3.6): il calcolo della ritenuta d'acconto,
# deterministico, oggi affidato al prompt. Puro Decimal, nessun I/O.
CODICE_RITENUTA = """
from decimal import Decimal, ROUND_HALF_UP

def esegui(imponibile, aliquota):
    imp = Decimal(str(imponibile))
    ali = Decimal(str(aliquota))
    ritenuta = (imp * ali / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return {"ritenuta": float(ritenuta)}
"""


def test_tool_buono_ritorna_il_risultato_atteso() -> None:
    risultato = esegui_in_sandbox(
        CODICE_RITENUTA, {"imponibile": 1000, "aliquota": 20}
    )
    assert risultato == {"ritenuta": 200.0}


def test_tool_buono_usa_moduli_whitelist() -> None:
    codice = """
import math

def esegui(raggio):
    return {"area": round(math.pi * raggio ** 2, 2)}
"""
    assert esegui_in_sandbox(codice, {"raggio": 2}) == {"area": 12.57}


def test_argomenti_non_serializzabili_sono_tool_error() -> None:
    with pytest.raises(ToolError, match="serializzabili"):
        esegui_in_sandbox(CODICE_RITENUTA, {"imponibile": {1, 2, 3}, "aliquota": 20})


def test_manca_esegui() -> None:
    with pytest.raises(ToolError, match="esegui"):
        esegui_in_sandbox("def altro():\n    return {}\n", {})


def test_output_non_json() -> None:
    codice = "def esegui():\n    return {1, 2, 3}\n"  # set non è JSON
    with pytest.raises(ToolError):
        esegui_in_sandbox(codice, {})


def test_output_troppo_grande() -> None:
    codice = "def esegui():\n    return {'x': 'a' * 1000000}\n"
    with pytest.raises(ToolError, match="troppo grande"):
        esegui_in_sandbox(codice, {}, output_max_byte=1024)


def test_eccezione_del_tool_e_tool_error() -> None:
    codice = "def esegui():\n    return {'y': 1 / 0}\n"
    with pytest.raises(ToolError, match="ZeroDivisionError"):
        esegui_in_sandbox(codice, {})


# ------------------------------------------------------- vettori d'abuso: import


def test_import_os_rifiutato() -> None:
    codice = "import os\n\ndef esegui():\n    return {'v': os.getcwd()}\n"
    with pytest.raises(ToolError, match="import non consentito"):
        esegui_in_sandbox(codice, {})


def test_import_da_os_rifiutato() -> None:
    codice = "from os import system\n\ndef esegui():\n    return {}\n"
    with pytest.raises(ToolError, match="import non consentito"):
        esegui_in_sandbox(codice, {})


def test_import_rete_rifiutato() -> None:
    for modulo in ("socket", "urllib.request", "http.client"):
        codice = f"import {modulo}\n\ndef esegui():\n    return {{}}\n"
        with pytest.raises(ToolError, match="import non consentito"):
            esegui_in_sandbox(codice, {})


def test_import_del_backend_rifiutato() -> None:
    # Nessun accesso al DAL / a /data: il tool non può importare l'app.
    codice = "import app\n\ndef esegui():\n    return {}\n"
    with pytest.raises(ToolError, match="import non consentito"):
        esegui_in_sandbox(codice, {})


def test_import_relativo_rifiutato() -> None:
    codice = "from . import qualcosa\n\ndef esegui():\n    return {}\n"
    with pytest.raises(ToolError, match="import non consentito"):
        esegui_in_sandbox(codice, {})


# ------------------------------------------------- vettori d'abuso: I/O e builtin


def test_open_file_rifiutato() -> None:
    codice = "def esegui():\n    return {'v': open('/etc/passwd').read()}\n"
    with pytest.raises(ToolError, match="non consentito"):
        esegui_in_sandbox(codice, {})


def test_scrittura_file_rifiutata(tmp_path: Path) -> None:
    bersaglio = tmp_path / "bersaglio.txt"
    codice = (
        f"def esegui():\n"
        f"    open({str(bersaglio)!r}, 'w').write('x')\n"
        f"    return {{}}\n"
    )
    with pytest.raises(ToolError, match="non consentito"):
        esegui_in_sandbox(codice, {})
    assert not bersaglio.exists()  # nulla è finito su disco


def test_eval_rifiutato() -> None:
    codice = "def esegui():\n    return {'v': eval('1+1')}\n"
    with pytest.raises(ToolError, match="non consentito"):
        esegui_in_sandbox(codice, {})


def test_evasione_via_dunder_rifiutata() -> None:
    # La classica risalita da un oggetto qualunque fino a os/__import__.
    codice = (
        "def esegui():\n"
        "    return {'v': str(().__class__.__bases__[0].__subclasses__())}\n"
    )
    with pytest.raises(ToolError, match="attributo non consentito"):
        esegui_in_sandbox(codice, {})


def test_accesso_builtins_rifiutato() -> None:
    codice = "def esegui():\n    return {'v': str(__builtins__)}\n"
    with pytest.raises(ToolError, match="non consentito"):
        esegui_in_sandbox(codice, {})


# ------------------------------------------- vettori d'abuso: risorse (subprocess)


def test_ciclo_infinito_terminato() -> None:
    codice = "def esegui():\n    while True:\n        pass\n"
    with pytest.raises(ToolError):
        esegui_in_sandbox(codice, {}, cpu_sec=1, timeout_sec=3)


def test_esplosione_memoria_terminata() -> None:
    codice = "def esegui():\n    x = bytearray(600 * 1024 * 1024)\n    return {'n': len(x)}\n"
    with pytest.raises(ToolError):
        esegui_in_sandbox(codice, {}, memoria_mb=128, timeout_sec=5)


# ----------------------------------------------------------- isolamento globale


def test_la_rete_e_bloccata_dalla_whitelist() -> None:
    # Il blocco della rete è per costruzione: nessun modulo capace di aprire un
    # socket è nella whitelist predefinita, quindi il tool non può nemmeno
    # importarlo. Verifichiamo il vettore diretto (socket) e uno indiretto
    # (requests-like via urllib), entrambi respinti prima dell'esecuzione.
    for modulo in ("socket", "ssl", "asyncio"):
        codice = f"import {modulo}\n\ndef esegui():\n    return {{}}\n"
        with pytest.raises(ToolError, match="import non consentito"):
            esegui_in_sandbox(codice, {})


def test_sorgente_non_valido() -> None:
    with pytest.raises(ToolError, match="non valido"):
        esegui_in_sandbox("def esegui(:\n    pass\n", {})


def test_il_protocollo_e_json_singolo() -> None:
    # Un print() del tool non deve corrompere il canale dei risultati.
    codice = "def esegui():\n    print('rumore su stdout')\n    return {'v': 7}\n"
    assert esegui_in_sandbox(codice, {}) == {"v": 7}


def test_nessun_residuo_json_parziale() -> None:
    # Sanity: il risultato è esattamente il dict del tool, ri-serializzabile.
    risultato = esegui_in_sandbox(CODICE_RITENUTA, {"imponibile": 500, "aliquota": 4})
    assert json.loads(json.dumps(risultato)) == {"ritenuta": 20.0}
