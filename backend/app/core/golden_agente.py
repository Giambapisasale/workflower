"""Golden dell'agente dati, indipendenti dall'archivio storico text-to-SQL."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any


def cartella(data_dir: Path | str) -> Path:
    return Path(data_dir) / "agent_goldens"


def normalizza(valore: Any) -> str:
    return json.dumps(valore, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def impronta_risultato(valore: Any) -> str:
    return sha256(normalizza(valore).encode("utf-8")).hexdigest()


def casi(data_dir: Path | str) -> list[dict[str, Any]]:
    risultato = []
    for percorso in sorted(cartella(data_dir).glob("AGOLD-*.json")):
        try:
            voce = json.loads(percorso.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if voce.get("stato") == "approvato":
            risultato.append(voce)
    return risultato

