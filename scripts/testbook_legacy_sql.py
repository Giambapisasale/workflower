"""Harness offline dell'archivio storico dell'interrogazione.

Non avvia né contatta l'API: legge soltanto conteggi dell'archivio preservato per
documentare la migrazione e confrontare la copertura dei golden agent-native.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _righe(percorso: Path) -> int:
    if not percorso.is_file():
        return 0
    return sum(1 for riga in percorso.read_text(encoding="utf-8").splitlines() if riga.strip())


def _golden_storici(data: Path) -> int:
    totale = 0
    for percorso in (data / "golden").rglob("GOLD-*.json"):
        try:
            if json.loads(percorso.read_text(encoding="utf-8")).get("domanda"):
                totale += 1
        except (OSError, json.JSONDecodeError):
            continue
    return totale


def main() -> int:
    parser = argparse.ArgumentParser(description="Rapporto offline dell'archivio storico.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    argomenti = parser.parse_args()
    data = argomenti.data.resolve()
    archivio = _righe(data / "dataset" / "queries.jsonl")
    golden_storici = _golden_storici(data)
    golden_agente = len(list((data / "agent_goldens").glob("AGOLD-*.json")))
    print("Harness storico offline: nessuna chiamata al prodotto.")
    print(f"interrogazioni archiviate: {archivio}")
    print(f"golden storici: {golden_storici}")
    print(f"golden agent-native: {golden_agente}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
