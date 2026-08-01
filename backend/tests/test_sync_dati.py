"""Allineamento del repo dati all'applicazione (``python -m app.sync_dati``).

Il rischio che questi test presidiano non è la copia — è *cosa non va copiato*:
in ``workflows/`` scrive anche l'Improver, e un allineamento che sovrascrive
alla cieca cancellerebbe migliorie che l'ufficio ha approvato.
"""

from pathlib import Path

from git import Repo

from app.core.dal import GIT_AUTHOR
from app.sync_dati import AGGIORNA, DIVERGENTE, NUOVO, UGUALE, applica, confronta

MANIFEST = "workflows/carica-ddt/manifest.yaml"
SKILL = "workflows/carica-ddt/skills/estrazione-ddt.md"
SCHEMA = "schemas/fattura.schema.json"


def _committa(data_dir: Path, rel: str, contenuto: str, messaggio: str) -> None:
    percorso = data_dir / rel
    percorso.parent.mkdir(parents=True, exist_ok=True)
    # ``newline=""`` disattiva la traduzione dei fine-riga in scrittura: senza,
    # su Windows un test che vuole scrivere CRLF finirebbe per scrivere CRCRLF.
    with percorso.open("w", encoding="utf-8", newline="") as f:
        f.write(contenuto)
    repo = Repo(data_dir)
    repo.index.add([rel])
    repo.index.commit(messaggio, author=GIT_AUTHOR, committer=GIT_AUTHOR)


def _stato(esiti: list, rel: str) -> str:
    return next(e.stato for e in esiti if e.rel == rel)


def test_repo_appena_seedato_e_gia_allineato(dati_rw: Path) -> None:
    esiti = confronta(dati_rw)
    assert esiti, "il confronto non ha trovato nessun file"
    assert {e.stato for e in esiti} == {UGUALE}


def test_manifest_indietro_viene_riconosciuto_e_allineato(dati_rw: Path) -> None:
    atteso = (dati_rw / MANIFEST).read_text(encoding="utf-8")
    _committa(dati_rw, MANIFEST, "steps: []\n", "workflows: versione vecchia [seed]")

    esiti = confronta(dati_rw)
    assert _stato(esiti, MANIFEST) == AGGIORNA
    assert _stato(esiti, SKILL) == UGUALE

    applica(dati_rw, [e for e in esiti if e.stato == AGGIORNA])
    assert (dati_rw / MANIFEST).read_text(encoding="utf-8") == atteso
    assert "[sync-dati]" in str(Repo(dati_rw).head.commit.message)


def test_file_modificato_a_valle_non_viene_sovrascritto(dati_rw: Path) -> None:
    """Il caso Improver: una skill migliorata nel repo dati resta com'è."""
    migliorata = "# Skill migliorata dall'ufficio\n"
    _committa(dati_rw, SKILL, migliorata, "patch PATCH-0001 applicata: estrazione-ddt")

    esiti = confronta(dati_rw)
    assert _stato(esiti, SKILL) == DIVERGENTE

    # `applica` riceve solo ciò che il comando ha selezionato: i divergenti
    # restano fuori finché non arriva --forza.
    applica(dati_rw, [e for e in esiti if e.stato in (NUOVO, AGGIORNA)])
    assert (dati_rw / SKILL).read_text(encoding="utf-8") == migliorata

    applica(dati_rw, [e for e in esiti if e.stato == DIVERGENTE])
    assert (dati_rw / SKILL).read_text(encoding="utf-8") != migliorata


def test_workflow_mancante_nel_repo_dati_e_nuovo(dati_rw: Path) -> None:
    percorso = dati_rw / MANIFEST
    percorso.unlink()
    repo = Repo(dati_rw)
    repo.index.remove([MANIFEST])
    repo.index.commit("rimozione [seed]", author=GIT_AUTHOR, committer=GIT_AUTHOR)

    esiti = confronta(dati_rw)
    assert _stato(esiti, MANIFEST) == NUOVO

    applica(dati_rw, [e for e in esiti if e.stato == NUOVO])
    assert percorso.is_file()


def test_anche_gli_schemi_si_allineano(dati_rw: Path) -> None:
    """Uno schema vecchio è insidioso quanto un manifest vecchio: un campo nuovo
    non verrebbe mai estratto, e non lo direbbe nessun errore."""
    atteso = (dati_rw / SCHEMA).read_text(encoding="utf-8")
    _committa(dati_rw, SCHEMA, '{"type": "object"}\n', "schema vecchio [seed]")

    esiti = confronta(dati_rw)
    assert _stato(esiti, SCHEMA) == AGGIORNA

    applica(dati_rw, [e for e in esiti if e.stato == AGGIORNA])
    assert (dati_rw / SCHEMA).read_text(encoding="utf-8") == atteso


def test_workflow_solo_nel_repo_dati_non_viene_toccato(dati_rw: Path) -> None:
    """Un workflow scritto a mano non è "da rimuovere": il comando non cancella."""
    rel = "workflows/mio-workflow/manifest.yaml"
    _committa(dati_rw, rel, "steps: []\n", "workflow su misura")

    esiti = confronta(dati_rw)
    assert all(e.rel != rel for e in esiti)

    applica(dati_rw, [e for e in esiti if e.stato in (NUOVO, AGGIORNA)])
    assert (dati_rw / rel).is_file()


def test_fine_riga_diversi_non_sono_una_differenza(dati_rw: Path) -> None:
    """Repo dati creato su Windows, immagine costruita su Linux: nessun rumore."""
    testo = (dati_rw / SKILL).read_text(encoding="utf-8")
    _committa(dati_rw, SKILL, testo.replace("\n", "\r\n"), "fine riga windows [seed]")

    assert _stato(confronta(dati_rw), SKILL) == UGUALE
