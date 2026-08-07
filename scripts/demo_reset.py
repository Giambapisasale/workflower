#!/usr/bin/env python3
"""Rifà il repo dati da zero **senza buttare via ciò che è stato imparato**.

`make reseed` azzera tutto, storia git inclusa. Va benissimo per ricominciare,
ma porta con sé anche quello che costa di più rimettere insieme:

- i **casi golden** approvati dall'ufficio (estrazioni, archivio storico e
  golden agent-native), che sono la rete di regressione e la misura del gate T3;
- i **blob** che quei casi rigiocano: un golden senza il suo documento non è
  più rigiocabile, e la pagina Workflows lo mostra come «originale mancante»;
- il **dataset** e le chiamate a tool, inclusi gli artefatti storici di confronto;
- l'anagrafica dell'**azienda corrente**, che l'ufficio ha compilato a mano.

Questo comando mette da parte quella roba, rifà il seed, la rimette e committa.
Il resto — bozze a metà, documenti caricati per prova, trace, segnalazioni —
sparisce, che è esattamente lo scopo.

Uso:
    python scripts/demo_reset.py            # mostra cosa farebbe
    python scripts/demo_reset.py --applica  # lo fa davvero
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

for _flusso in (sys.stdout, sys.stderr):
    if hasattr(_flusso, "reconfigure"):
        _flusso.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.dal import DAL  # noqa: E402
from app.seed import run_seed  # noqa: E402

# Cartelle che si conservano tali e quali.
DA_CONSERVARE = ("golden", "agent_goldens", "dataset")

# File singoli che si conservano se ci sono.
FILE_DA_CONSERVARE = ("config/azienda.json",)


def _blob_dei_golden(data_dir: Path) -> set[str]:
    """I documenti che i casi golden rigiocano: senza, il caso non vale più."""
    percorsi = set()
    for caso in (data_dir / "golden").glob("GOLD-*.json"):
        try:
            doc = json.loads(caso.read_text(encoding="utf-8")).get("doc")
        except (OSError, ValueError):
            continue
        if doc and (data_dir / doc).is_file():
            percorsi.add(doc)
    return percorsi


def _conta(data_dir: Path) -> dict[str, int]:
    return {
        "golden": len(list((data_dir / "golden").glob("GOLD-*.json"))),
        "golden agent-native": len(list((data_dir / "agent_goldens").glob("AGOLD-*.json"))),
        "blob dei golden": len(_blob_dei_golden(data_dir)),
        "righe di dataset": sum(
            sum(1 for _ in f.open(encoding="utf-8"))
            for f in (data_dir / "dataset").glob("*.jsonl")
        ),
    }


def _metti_da_parte(data_dir: Path, deposito: Path) -> list[str]:
    conservati = []
    for cartella in DA_CONSERVARE:
        if (data_dir / cartella).is_dir():
            shutil.copytree(data_dir / cartella, deposito / cartella)
            conservati.append(cartella)
    for relativo in FILE_DA_CONSERVARE:
        if (data_dir / relativo).is_file():
            (deposito / relativo).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(data_dir / relativo, deposito / relativo)
            conservati.append(relativo)
    for blob in _blob_dei_golden(data_dir):
        (deposito / blob).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(data_dir / blob, deposito / blob)
    return conservati


def _rimetti(deposito: Path, data_dir: Path) -> list[Path]:
    ripristinati = []
    for sorgente in deposito.rglob("*"):
        if not sorgente.is_file():
            continue
        destinazione = data_dir / sorgente.relative_to(deposito)
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(sorgente, destinazione)
        ripristinati.append(destinazione)
    return ripristinati


def main() -> int:
    argomenti = argparse.ArgumentParser(description=__doc__)
    argomenti.add_argument(
        "--applica", action="store_true", help="esegue davvero (di suo mostra e basta)"
    )
    opzioni = argomenti.parse_args()

    data_dir = Path(os.environ.get("DATA_DIR", "./data")).resolve()
    if not (data_dir / ".git").exists():
        print(f"ERRORE: {data_dir} non è un repo dati. Fare prima `make seed`.")
        return 1

    print(f"Repo dati: {data_dir}")
    for etichetta, quanti in _conta(data_dir).items():
        print(f"  si conservano {quanti} {etichetta}")
    print("  si perdono: entità, blob non golden, trace, segnalazioni, storia git")

    if not opzioni.applica:
        print("\nNiente è stato toccato. Per farlo davvero: --applica")
        return 0

    deposito = Path(tempfile.mkdtemp(prefix="wf-demo-reset-"))
    try:
        conservati = _metti_da_parte(data_dir, deposito)
        shutil.rmtree(data_dir)
        run_seed(data_dir)
        ripristinati = _rimetti(deposito, data_dir)
        DAL(data_dir).commit_paths(
            ripristinati, "demo-reset: ripristina golden, dataset e azienda [seed]"
        )
    finally:
        shutil.rmtree(deposito, ignore_errors=True)

    print(f"\nFatto. Ripristinati {len(ripristinati)} file ({', '.join(conservati)}).")
    for etichetta, quanti in _conta(data_dir).items():
        print(f"  {quanti} {etichetta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
