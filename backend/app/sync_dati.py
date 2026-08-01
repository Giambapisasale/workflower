"""Allinea il repo dati a ciò che l'applicazione distribuisce (workflow e schemi).

Il seed crea ``data/`` una volta sola: ``app.seed`` rifiuta una cartella non
vuota, quindi un aggiornamento dell'applicazione **non** aggiorna manifest,
skill e schemi già scritti. Senza questo comando le due copie divergono in
silenzio, e il difetto non si vede: un tool nuovo non arriva mai al modello
perché il manifest nel repo dati non lo dichiara, un campo nuovo non viene mai
estratto perché lo schema è quello vecchio. Non dà errore — dà risultati
peggiori.

Uso: ``make data-sync`` (sviluppo) oppure, in produzione::

    docker compose exec app python -m app.sync_dati            # mostra il diff
    docker compose exec app python -m app.sync_dati --applica  # copia e committa

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

ASSETS = Path(__file__).parent / "seed_assets"

# Cosa viaggia con l'applicazione e deve poter raggiungere un repo dati che
# esiste già. `config/` no: views.sql a parte, lì dentro ci sono gli utenti e
# l'azienda, che sono dell'installazione e non nostri.
CARTELLE = ("workflows", "schemas")

# I commit che questo comando e il seed producono: tutto il resto della storia
# di un file è, per definizione, una modifica fatta a valle (Improver o umano).
MARCATORI_NOSTRI = ("[seed]", "[sync-workflows]", "[sync-dati]")

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
    """Confronta ciò che l'applicazione distribuisce con ciò che c'è nel repo dati.

    Guarda solo i file presenti negli asset: quelli che esistono soltanto nel
    repo dati (un workflow scritto a mano, uno schema su misura) non vengono
    toccati né segnalati come da rimuovere — questo comando aggiunge e aggiorna,
    non cancella mai.
    """
    repo = Repo(data_dir)
    esiti: list[Confronto] = []
    for cartella in CARTELLE:
        for sorgente in sorted((assets / cartella).rglob("*")):
            if not sorgente.is_file():
                continue
            rel = f"{cartella}/{sorgente.relative_to(assets / cartella).as_posix()}"
            esiti.append(_confronta_uno(repo, data_dir, sorgente, rel))
    return esiti


def _confronta_uno(repo: Repo, data_dir: Path, sorgente: Path, rel: str) -> Confronto:
    destinazione = data_dir / rel
    if not destinazione.exists():
        return Confronto(rel, NUOVO, [])
    atteso, corrente = _testo(sorgente), _testo(destinazione)
    if atteso == corrente:
        return Confronto(rel, UGUALE, [])
    diff = list(
        difflib.unified_diff(
            corrente.splitlines(), atteso.splitlines(), "repo dati", "applicazione", lineterm=""
        )
    )
    stato = DIVERGENTE if _modificato_a_valle(repo, rel) else AGGIORNA
    return Confronto(rel, stato, diff)


def applica(data_dir: Path, da_copiare: list[Confronto], assets: Path = ASSETS) -> None:
    """Copia i file scelti e li committa nel repo dati, in un commit solo."""
    if not da_copiare:
        return
    for esito in da_copiare:
        destinazione = data_dir / esito.rel
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(assets / esito.rel, destinazione)
    repo = Repo(data_dir)
    repo.index.add([esito.rel for esito in da_copiare])
    repo.index.commit(
        f"dati: allinea {len(da_copiare)} file all'applicazione [sync-dati]",
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
    argomenti = argparse.ArgumentParser(description="Allinea il repo dati all'applicazione.")
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
        print("\nNiente da fare: il repo dati è allineato.")
        return 0
    if not opzioni.applica:
        print("\nNiente è stato scritto. Per applicare: python -m app.sync_dati --applica")
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
