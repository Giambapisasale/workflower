"""Sandbox di esecuzione per codice generato (Fase 3, M14).

Prima di *generare* codice (Toolsmith, M16) bisogna poterlo *eseguire senza
rischi*: è la precondizione di sicurezza dell'intera Fase 3. Da qui in poi il
sistema esegue funzioni Python scritte da un LLM, e lo fa **solo** dentro questa
sandbox — mai importandole in-process (vedi ``CLAUDE.md``: il codice generato è
*dato*, non runtime).

Contratto d'uso, gemello di quello che un tool nativo espone al modello:

    esegui(**kwargs) -> dict        # nel sorgente del tool
    esegui_in_sandbox(codice, argomenti) -> dict   # qui

JSON dentro, JSON fuori. Nessun accesso a ``dal.py``, al filesystem di ``/data``,
alla rete o alle variabili d'ambiente. La difesa è a due strati:

1. **Statica, in-process** (:func:`_valida_sorgente`): l'AST del sorgente è
   ispezionato *prima* di spendere un subprocess — import fuori whitelist, dunder
   d'evasione (``__subclasses__``, ``__globals__``, …) e builtin pericolosi
   (``open``, ``eval``, ``exec``, ``__import__``, …) sono rifiutati subito.
2. **A runtime, in un subprocess isolato** (``python -I``): builtin ridotti,
   ``__import__`` controllato sulla whitelist, e — su POSIX — limiti di memoria,
   CPU e dimensione file (``resource``). Il tempo di parete è imposto dal padre
   via timeout del subprocess, quindi vale su ogni piattaforma.

Ogni fallimento (import vietato, timeout, eccezione, esplosione di memoria,
output fuori contratto) diventa un :class:`ToolError`: al chiamante il tool
risulta "non utilizzabile", non un crash del runtime.

Portabilità (``CLAUDE.md``, piano F3 M14): **stessa interfaccia, due back-end**.
Su POSIX i limiti di risorsa sono imposti con ``resource`` nel figlio; su Windows
(piattaforma di sviluppo) ``resource`` non esiste e la protezione si riduce al
timeout di parete + troncamento output, con il Job Object come punto d'estensione
documentato. Il runtime — ``runtime.py``, ``gateway.py``, ``dal.py``,
``tracer.py`` — non cambia: la sandbox è una *capacità nuova* iniettabile.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from typing import Any

from app.core.tools.base import ToolError

# Moduli che un tool consolidato può importare: solo calcolo/normalizzazione
# deterministici (il Toolsmith di F3 consolida calcoli, non l'OCR). Estendibile
# come *dato* passando un ``whitelist`` diverso, mai allargando i default alla
# leggera: ``os``/``sys``/``subprocess``/``socket`` restano fuori per sempre.
WHITELIST_PREDEFINITA: frozenset[str] = frozenset({"math", "datetime", "decimal", "re"})

MEMORIA_MB_PREDEFINITA = 256
CPU_SEC_PREDEFINITI = 2
TIMEOUT_SEC_PREDEFINITO = 5
OUTPUT_MAX_BYTE = 256 * 1024

# Attributi che aprono la via d'evasione dal namespace ristretto (risalire da un
# oggetto qualunque fino a ``os``/``__import__`` via la gerarchia delle classi).
_DUNDER_VIETATI: frozenset[str] = frozenset(
    {
        "__subclasses__",
        "__bases__",
        "__base__",
        "__mro__",
        "__globals__",
        "__code__",
        "__closure__",
        "__builtins__",
        "__import__",
        "__dict__",
        "__class__",
        "__subclasshook__",
        "__getattribute__",
        "__reduce__",
        "__reduce_ex__",
    }
)

# Builtin che non hanno posto in un calcolo puro e che darebbero accesso a I/O,
# esecuzione dinamica o introspezione del namespace globale.
_NOMI_VIETATI: frozenset[str] = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "open",
        "__import__",
        "globals",
        "locals",
        "vars",
        "getattr",
        "setattr",
        "delattr",
        "input",
        "breakpoint",
        "exit",
        "quit",
        "memoryview",
    }
)


def _valida_sorgente(codice: str, whitelist: frozenset[str]) -> None:
    """Ispeziona l'AST del tool; solleva :class:`ToolError` al primo abuso.

    Primo strato di difesa: gira in-process ed è deterministico, quindi un
    sorgente ostile non arriva nemmeno a costare un subprocess. Non pretende di
    essere una prova di sicurezza da solo — lo strato subprocess + ``resource``
    lo completa — ma respinge tutti i vettori diretti (import di ``os``, ``eval``,
    ``open``, risalita via ``__subclasses__``).
    """
    try:
        albero = ast.parse(codice)
    except SyntaxError as exc:
        raise ToolError(f"codice del tool non valido: {exc}") from exc

    ha_esegui = False
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                if alias.name.split(".")[0] not in whitelist:
                    raise ToolError(f"import non consentito nel tool: {alias.name}")
        elif isinstance(nodo, ast.ImportFrom):
            radice = (nodo.module or "").split(".")[0]
            if nodo.level or radice not in whitelist:
                raise ToolError(f"import non consentito nel tool: {nodo.module or '.'}")
        elif isinstance(nodo, ast.Attribute):
            if nodo.attr in _DUNDER_VIETATI:
                raise ToolError(f"attributo non consentito nel tool: {nodo.attr}")
        elif isinstance(nodo, ast.Name):
            if nodo.id in _NOMI_VIETATI or nodo.id in _DUNDER_VIETATI:
                raise ToolError(f"nome non consentito nel tool: {nodo.id}")
        elif isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef) and nodo.name == "esegui":
            ha_esegui = True

    if not ha_esegui:
        raise ToolError("il tool deve definire una funzione esegui(...)")


# Runner eseguito nel subprocess isolato (``python -I``). È codice *nostro*
# (fidato): può importare stdlib liberamente. Legge il payload JSON da stdin,
# applica i limiti, esegue il sorgente del tool in un namespace ristretto e
# scrive un unico oggetto JSON di protocollo sullo stdout originale. L'output del
# tool (eventuali ``print``) è dirottato nel nulla, così non corrompe il canale.
_RUNNER = r'''
import sys, os, json, builtins

def _principale():
    dati = json.loads(sys.stdin.read())
    codice = dati["codice"]
    argomenti = dati["argomenti"]
    whitelist = set(dati["whitelist"])
    limiti = dati["limiti"]
    output_max = dati["output_max"]

    # Lo stdout originale (fd 1) è messo da parte per il protocollo; l'output del
    # tool va nel nulla, così un print() non inquina il canale dei risultati.
    reale = os.fdopen(os.dup(1), "w")
    nulla = os.open(os.devnull, os.O_WRONLY)
    os.dup2(nulla, 1)
    os.close(nulla)

    def _emetti(payload):
        reale.write(json.dumps(payload))
        reale.flush()

    # Limiti di risorsa: POSIX via resource; altrove (Windows) best-effort, la
    # protezione resta il timeout di parete imposto dal padre.
    try:
        import resource
        mem = limiti["memoria_byte"]
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        cpu = limiti["cpu_sec"]
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))  # nessuna scrittura file
    except Exception:
        pass

    _import_reale = builtins.__import__

    def _import_controllato(nome, *a, **k):
        if nome.split(".")[0] not in whitelist:
            raise ImportError("import non consentito nel tool: " + nome)
        return _import_reale(nome, *a, **k)

    vietati = {
        "open", "eval", "exec", "compile", "input", "breakpoint", "exit",
        "quit", "help", "memoryview", "__import__", "globals", "vars",
        "getattr", "setattr", "delattr",
    }
    sicuri = {n: getattr(builtins, n) for n in dir(builtins) if n not in vietati}
    sicuri["__import__"] = _import_controllato
    ambiente = {"__builtins__": sicuri, "__name__": "__tool__"}

    try:
        exec(compile(codice, "<tool>", "exec"), ambiente)
        funzione = ambiente.get("esegui")
        if not callable(funzione):
            _emetti({"ok": False, "errore": "il tool non definisce esegui(...)"})
            return
        risultato = funzione(**argomenti)
        testo = json.dumps(risultato)  # impone il contratto: output JSON
    except MemoryError:
        _emetti({"ok": False, "errore": "memoria esaurita durante l'esecuzione del tool"})
        return
    except BaseException as exc:
        _emetti({"ok": False, "errore": type(exc).__name__ + ": " + str(exc)})
        return

    if len(testo) > output_max:
        _emetti({"ok": False, "errore": "output del tool troppo grande"})
        return
    _emetti({"ok": True, "risultato": json.loads(testo)})

_principale()
'''


def _ambiente_minimo() -> dict[str, str]:
    """Ambiente ridotto per il figlio: nessuna variabile ereditata su POSIX.

    ``python -I`` ignora comunque le variabili di configurazione dell'interprete;
    su Windows preserviamo solo ``SystemRoot``, necessario all'avvio.
    """
    if os.name == "nt":
        return {"SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    return {}


def esegui_in_sandbox(
    codice: str,
    argomenti: dict[str, Any],
    *,
    whitelist: Iterable[str] = WHITELIST_PREDEFINITA,
    memoria_mb: int = MEMORIA_MB_PREDEFINITA,
    cpu_sec: int = CPU_SEC_PREDEFINITI,
    timeout_sec: float = TIMEOUT_SEC_PREDEFINITO,
    output_max_byte: int = OUTPUT_MAX_BYTE,
) -> dict[str, Any]:
    """Esegue ``esegui(**argomenti)`` del sorgente ``codice`` in una sandbox.

    Ritorna il ``dict`` prodotto dal tool. Solleva :class:`ToolError` per ogni
    forma di fallimento — sorgente non valido, import fuori whitelist, timeout,
    eccezione del tool, memoria esaurita, output non serializzabile o troppo
    grande — così che il chiamante lo tratti come "tool non utilizzabile" e (da
    M17) ricada sull'LLM.
    """
    if not isinstance(argomenti, dict):
        raise ToolError("gli argomenti del tool devono essere un oggetto (dict)")

    lista_whitelist = sorted(set(whitelist))
    _valida_sorgente(codice, frozenset(lista_whitelist))

    try:
        payload = json.dumps(
            {
                "codice": codice,
                "argomenti": argomenti,
                "whitelist": lista_whitelist,
                "limiti": {"memoria_byte": memoria_mb * 1024 * 1024, "cpu_sec": cpu_sec},
                "output_max": output_max_byte,
            }
        )
    except (TypeError, ValueError) as exc:
        raise ToolError(f"argomenti del tool non serializzabili in JSON: {exc}") from exc

    with tempfile.TemporaryDirectory(prefix="workflower-sandbox-") as cwd:
        try:
            esito = subprocess.run(
                [sys.executable, "-I", "-c", _RUNNER],
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                cwd=cwd,
                env=_ambiente_minimo(),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError(
                f"il tool ha superato il tempo massimo ({timeout_sec}s)"
            ) from exc

    uscita = (esito.stdout or "").strip()
    if not uscita:
        dettaglio = (esito.stderr or "").strip().splitlines()
        coda = dettaglio[-1] if dettaglio else f"codice di uscita {esito.returncode}"
        raise ToolError(f"il tool è terminato senza risultato ({coda})")

    try:
        protocollo = json.loads(uscita)
    except json.JSONDecodeError as exc:
        raise ToolError("output del tool non interpretabile") from exc

    if not protocollo.get("ok"):
        raise ToolError(protocollo.get("errore") or "errore sconosciuto del tool")
    return protocollo["risultato"]
