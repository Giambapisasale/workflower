"""Allinea i workflow del repo dati a quelli distribuiti con l'applicazione.

Il seed crea ``data/`` una volta sola: ``app.seed`` rifiuta una cartella non
vuota, quindi un aggiornamento dell'applicazione **non** aggiorna manifest e
skill di un repo dati che esiste già. Senza questo comando le due copie
divergono in silenzio, e un tool nuovo non arriva mai al modello perché il
manifest nel repo dati non lo dichiara.

Uso: ``make data-sync-workflows`` (sviluppo) oppure, in produzione::

    docker compose exec app python -m app.sync_workflows            # mostra il diff
    docker compose exec app python -m app.sync_workflows --applica  # copia e committa

Destinazione: ``$DATA_DIR`` (default ``./data``).

Di suo non scrive niente: elenca le differenze e si ferma. E non sovrascrive i
file che qualcuno ha modificato **dentro** il repo dati — in ``workflows/``
scrive anche l'Improver quando l'ufficio approva una proposta, e una copia
cieca cancellerebbe proprio quelle migliorie. Per quelli serve ``--forza``.
"""

import argparse
import difflib
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from git import Repo

from app.core.dal import GIT_AUTHOR

ASSETS = Path(__file__).parent / "seed_assets" / "workflows"

# I commit che questo comando e il seed producono: tutto il resto della storia
# di un file è, per definizione, una modifica fatta a valle (Improver o umano).
MARCATORI_NOSTRI = ("[seed]", "[sync-workflows]")

UGUALE, AGGIORNA, NUOVO, DIVERGENTE = "uguale", "aggiorna", "nuovo", "divergente"


@dataclass(frozen=True)
class Confronto:
    rel: str  # percorso relativo al repo dati, es. "workflows/carica-ddt/manifest.yaml"
    stato: str
    diff: list[str]


def _testo(percorso: Path) -> str:
    """Contenuto con i fine-riga normalizzati a ``\\n``.

    Serve perché un repo dati creato su Windows e un'immagine costruita su Linux
    differiscono su *ogni riga di ogni file*: la differenza vera si perderebbe
    nel rumore. Ci pensa già la modalità testo di Python (universal newlines),
    ma è un dettaglio abbastanza silenzioso da meritare un nome e un test.
    """
    return percorso.read_text(encoding="utf-8")


def _modificato_a_valle(repo: Repo, rel: str) -> bool:
    """Qualcuno ha toccato questo file dopo il seed (Improver o a mano)?"""
    for commit in repo.iter_commits(paths=rel):
        messaggio = str(commit.message)
        if not any(marcatore in messaggio for marcatore in MARCATORI_NOSTRI):
            return True
    return False


def confronta(data_dir: Path, assets: Path = ASSETS) -> list[Confronto]:
    """Confronta i workflow distribuiti con quelli nel repo dati.

    Guarda solo i file presenti negli asset: quelli che esistono soltanto nel
    repo dati (un workflow scritto a mano) non vengono toccati né segnalati
    come da rimuovere — questo comando aggiunge e aggiorna, non cancella mai.
    """
    repo = Repo(data_dir)
    esiti: list[Confronto] = []
    for sorgente in sorted(assets.rglob("*")):
        if not sorgente.is_file():
            continue
        rel = f"workflows/{sorgente.relative_to(assets).as_posix()}"
        destinazione = data_dir / rel
        if not destinazione.exists():
            esiti.append(Confronto(rel, NUOVO, []))
            continue
        atteso, corrente = _testo(sorgente), _testo(destinazione)
        if atteso == corrente:
            esiti.append(Confronto(rel, UGUALE, []))
            continue
        diff = list(
            difflib.unified_diff(
                corrente.splitlines(), atteso.splitlines(), "repo dati", "applicazione", lineterm=""
            )
        )
        stato = DIVERGENTE if _modificato_a_valle(repo, rel) else AGGIORNA
        esiti.append(Confronto(rel, stato, diff))
    return esiti


def applica(data_dir: Path, da_copiare: list[Confronto], assets: Path = ASSETS) -> None:
    """Copia i file scelti e li committa nel repo dati, in un commit solo."""
    if not da_copiare:
        return
    for esito in da_copiare:
        sorgente = assets / Path(esito.rel).relative_to("workflows")
        destinazione = data_dir / esito.rel
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sorgente, destinazione)
    repo = Repo(data_dir)
    repo.index.add([esito.rel for esito in da_copiare])
    repo.index.commit(
        f"workflows: allinea {len(da_copiare)} file all'applicazione [sync-workflows]",
        author=GIT_AUTHOR,
        committer=GIT_AUTHOR,
    )


def _stampa(esiti: list[Confronto], righe_diff: int) -> None:
    for stato, simbolo, titolo in (
        (NUOVO, "+", "nuovi"),
        (AGGIORNA, "~", "da aggiornare"),
        (DIVERGENTE, "!", "modificati nel repo dati"),
    ):
        selezionati = [e for e in esiti if e.stato == stato]
        if not selezionati:
            continue
        print(f"\n{simbolo} {titolo} ({len(selezionati)}):")
        for esito in selezionati:
            print(f"    {esito.rel}")
            for riga in esito.diff[2 : 2 + righe_diff]:
                print(f"      {riga}")
            if len(esito.diff) > 2 + righe_diff:
                print(f"      … altre {len(esito.diff) - 2 - righe_diff} righe")


def main() -> int:
    argomenti = argparse.ArgumentParser(description="Allinea i workflow del repo dati.")
    argomenti.add_argument(
        "--applica", action="store_true", help="scrive le modifiche (di suo mostra e basta)"
    )
    argomenti.add_argument(
        "--forza",
        action="store_true",
        help="sovrascrive anche i file modificati nel repo dati (Improver compreso)",
    )
    argomenti.add_argument(
        "--righe-diff", type=int, default=6, help="righe di diff per file (default 6)"
    )
    opzioni = argomenti.parse_args()

    data_dir = Path(os.environ.get("DATA_DIR", "./data")).resolve()
    if not (data_dir / ".git").exists():
        print(f"ERRORE: {data_dir} non è un repo dati (manca .git). Fare prima il seed.")
        return 1

    esiti = confronta(data_dir)
    print(f"Repo dati: {data_dir}")
    print(f"  uguali: {sum(1 for e in esiti if e.stato == UGUALE)} su {len(esiti)}")
    _stampa(esiti, opzioni.righe_diff)

    da_copiare = [e for e in esiti if e.stato in (NUOVO, AGGIORNA)]
    divergenti = [e for e in esiti if e.stato == DIVERGENTE]
    if opzioni.forza:
        da_copiare += divergenti
        divergenti = []

    if not da_copiare and not divergenti:
        print("\nNiente da fare: i workflow sono allineati.")
        return 0
    if not opzioni.applica:
        print("\nNiente è stato scritto. Per applicare: python -m app.sync_workflows --applica")
        if divergenti:
            print("I file modificati nel repo dati restano fuori: per includerli aggiungi --forza.")
        return 0

    applica(data_dir, da_copiare)
    print(f"\nApplicati {len(da_copiare)} file, in un commit nel repo dati.")
    if divergenti:
        print(f"Saltati {len(divergenti)} file modificati nel repo dati (--forza per includerli).")
    print("Per annullare: git -C <repo dati> revert HEAD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
