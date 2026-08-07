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

Il catalogo SQL (``config/views.sql`` e ``config/macros.sql``) è un caso a sé:
la base la distribuisce l'applicazione, ma dentro ci sono le viste e i tool che
l'ufficio ha consolidato. Si copia la base e vi si reinnesta quella regione —
vedi ``FILE_CON_REGIONE``. I due file vanno allineati **insieme**: le macro
referenziano le viste, e DuckDB rifiuta l'intero catalogo — quindi ogni query,
non solo quella nuova — se una macro nomina una vista che non c'è.
"""

import argparse
import difflib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from git import Repo

# I marker delle regioni generate e il loro innesto vivono nel DAL, che è il solo
# a scriverle: qui servono per *conservarle*, non per produrle.
from app.core.dal import (
    _TOOL_FINE,
    _TOOL_INIZIO,
    _VISTE_FINE,
    _VISTE_INIZIO,
    GIT_AUTHOR,
    _inserisci_regione,
)

ASSETS = Path(__file__).parent / "seed_assets"

# Cosa viaggia con l'applicazione e deve poter raggiungere un repo dati che
# esiste già. Il resto di `config/` no: utenti e azienda sono dell'installazione,
# non nostri.
CARTELLE = ("workflows", "schemas")
FILE_SINGOLI: tuple[str, ...] = ()

# File distribuiti dall'applicazione che ospitano però una regione generata
# dall'installazione: le viste e i tool che l'ufficio ha consolidato.
#
# Non stanno né fra i file da copiare né fra quelli da ignorare, e nessuna delle
# due scorciatoie funziona: copiarli tali e quali cancella il lavoro
# dell'ufficio; lasciarli indietro blocca il catalogo base — ed è la peggiore
# delle due, perché `macros.sql` referenzia viste che vivono in `views.sql`.
# Allinearne uno solo (com'era: macros.sql sì, views.sql no) fa fallire *ogni*
# query, non solo quella nuova: DuckDB rifiuta l'intero catalogo se una macro
# nomina una vista che non c'è. Si copia la base dell'applicazione e vi si
# reinnesta la regione che il repo dati ha già.
FILE_CON_REGIONE: dict[str, tuple[str, str]] = {
    "config/views.sql": (_VISTE_INIZIO, _VISTE_FINE),
    "config/macros.sql": (_TOOL_INIZIO, _TOOL_FINE),
}
# Asset del vecchio percorso da eliminare al primo allineamento. Non è più una
# skill attiva né un documento UI: resta la cronologia Git del repo dati come
# archivio, mentre l'app non può ricaricarlo per errore.
FILE_RITIRATI = ("workflows/interroga/skills/generazione-sql.md",)

# I commit che questo comando e il seed producono: tutto il resto della storia
# di un file è, per definizione, una modifica fatta a valle (Improver o umano).
MARCATORI_NOSTRI = ("[seed]", "[sync-workflows]", "[sync-dati]")

# Per i file con regione, i commit del consolidamento non sono una divergenza da
# rispettare: scrivono *solo* dentro i marker, e il reinnesto li conserva parola
# per parola. Trattarli come modifiche a mano bloccherebbe l'allineamento del
# catalogo base proprio nelle installazioni che il prodotto lo usano davvero.
MARCATORI_REGIONE = ("consolida:",)

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
    marcatori = MARCATORI_NOSTRI
    if rel in FILE_CON_REGIONE:
        marcatori += MARCATORI_REGIONE
    for commit in repo.iter_commits(paths=rel):
        messaggio = str(commit.message)
        if not any(marcatore in messaggio for marcatore in marcatori):
            return True
    return False


def _estrai_regione(testo: str, inizio: str, fine: str) -> str | None:
    """La regione generata così com'è nel repo dati, marker compresi."""
    if inizio not in testo or fine not in testo:
        return None
    return testo[testo.index(inizio) : testo.index(fine) + len(fine)]


def _atteso(data_dir: Path, sorgente: Path, rel: str) -> str:
    """Il contenuto che il file dovrebbe avere: base dell'app + regione locale.

    Per i file normali è semplicemente ciò che l'applicazione distribuisce.
    """
    base = _testo(sorgente)
    marker = FILE_CON_REGIONE.get(rel)
    if marker is None:
        return base
    destinazione = data_dir / rel
    if not destinazione.exists():
        return base
    regione = _estrai_regione(_testo(destinazione), *marker)
    if regione is None:
        return base  # l'ufficio non ha ancora consolidato niente: non c'è cosa salvare
    return _inserisci_regione(base, regione, *marker)


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
    for rel in (*FILE_SINGOLI, *FILE_CON_REGIONE):
        sorgente = assets / rel
        if sorgente.is_file():
            esiti.append(_confronta_uno(repo, data_dir, sorgente, rel))
    for rel in FILE_RITIRATI:
        if (data_dir / rel).is_file():
            stato = DIVERGENTE if _modificato_a_valle(repo, rel) else AGGIORNA
            esiti.append(Confronto(rel, stato, ["- skill ritirata dall'agente dati"]))
    return esiti


def _confronta_uno(repo: Repo, data_dir: Path, sorgente: Path, rel: str) -> Confronto:
    destinazione = data_dir / rel
    if not destinazione.exists():
        return Confronto(rel, NUOVO, [])
    atteso, corrente = _atteso(data_dir, sorgente, rel), _testo(destinazione)
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
        if esito.rel in FILE_RITIRATI:
            destinazione.unlink(missing_ok=True)
            continue
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        # Non `copyfile`: per i file con regione il contenuto da scrivere non è
        # quello dell'asset, è l'asset con reinnestata la regione locale.
        destinazione.write_text(
            _atteso(data_dir, assets / esito.rel, esito.rel), encoding="utf-8", newline=""
        )
    repo = Repo(data_dir)
    presenti = [esito.rel for esito in da_copiare if esito.rel not in FILE_RITIRATI]
    ritirati = [esito.rel for esito in da_copiare if esito.rel in FILE_RITIRATI]
    if presenti:
        repo.index.add(presenti)
    if ritirati:
        repo.index.remove(ritirati, working_tree=False)
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
