"""Il catalogo SQL si allinea senza perdere ciò che l'ufficio ha consolidato.

Il difetto che questi test presidiano è arrivato dalla produzione ed è di quelli
che sembrano innocui: ``config/macros.sql`` viaggiava con l'applicazione,
``config/views.sql`` no. Allinearne uno solo non lascia il sistema com'era — lo
rompe **del tutto**: la macro distribuita nomina ``v_cantiere_costi``, la vista
sta in ``views.sql``, e DuckDB rifiuta l'intero catalogo se una macro referenzia
una vista che non c'è. Non cade la query nuova: cadono tutte, con un «strumento
momentaneamente non disponibile» che non dice a nessuno il perché.

L'altra metà del problema è opposta e vale la pena non dimenticarla: quei due
file ospitano le viste e i tool che l'ufficio ha consolidato, e una copia cieca
li cancellerebbe.
"""

from __future__ import annotations

from pathlib import Path

from git import Repo

from app.core.dal import DAL, GIT_AUTHOR
from app.core.views import connect
from app.sync_dati import AGGIORNA, DIVERGENTE, NUOVO, applica, confronta

VIEWS = "config/views.sql"
MACROS = "config/macros.sql"
# La vista base che la macro distribuita referenzia: è arrivata con l'agente
# dati, quindi è esattamente quella che un repo dati più vecchio non ha.
BASE_AGENTE = "-- Base interna dell'agente dati"


def _riporta_indietro_il_catalogo(data_dir: Path) -> None:
    """Il repo dati com'era prima dell'agente dati: niente ``v_cantiere_costi``.

    Committato con un marcatore nostro perché il punto del test è l'allineamento,
    non la protezione delle modifiche a valle (che ha già i suoi test).
    """
    views = data_dir / VIEWS
    testo = views.read_text(encoding="utf-8")
    assert BASE_AGENTE in testo, "il catalogo distribuito non contiene più la vista base"
    views.write_text(testo[: testo.index(BASE_AGENTE)].rstrip() + "\n", encoding="utf-8")
    (data_dir / MACROS).unlink()  # su quel repo la macro non esisteva ancora
    repo = Repo(data_dir)
    repo.index.add([VIEWS])
    repo.index.remove([MACROS], working_tree=False)
    repo.index.commit(
        "catalogo versione precedente [seed]", author=GIT_AUTHOR, committer=GIT_AUTHOR
    )


def _stato(esiti: list, rel: str) -> str:
    return next(e.stato for e in esiti if e.rel == rel)


def _allinea(data_dir: Path) -> None:
    esiti = confronta(data_dir)
    applica(data_dir, [e for e in esiti if e.stato in (NUOVO, AGGIORNA)])


def _consolida_una_vista(data_dir: Path) -> None:
    DAL(data_dir).consolida_vista(
        nome="spesa per cantiere",
        vista="v_collaudo_spesa",
        corpo="SELECT id AS cantiere_id, nome FROM v_cantieri",
        fingerprint="fp-collaudo",
        esempio="quanto si è speso per cantiere?",
        creato_da="giovanna",
    )


def test_repo_dati_vecchio_torna_con_un_catalogo_caricabile(dati_rw: Path) -> None:
    """La riproduzione del caso di produzione, dal repo dati indietro in poi.

    Prima della correzione qui arrivava la macro senza la vista che nomina, e
    ``connect`` moriva con CatalogException: non una query rotta, tutte.
    """
    _riporta_indietro_il_catalogo(dati_rw)

    _allinea(dati_rw)

    conn = connect(dati_rw)
    try:
        assert conn.execute("SELECT count(*) FROM v_cantiere_costi").fetchone() is not None
        conn.execute("SELECT * FROM t_costi_cantiere('a') LIMIT 1")  # la macro distribuita
    finally:
        conn.close()


def test_macro_distribuita_e_vista_che_le_serve_arrivano_insieme(dati_rw: Path) -> None:
    """Allinearne uno solo è peggio di non allinearne nessuno."""
    (dati_rw / VIEWS).unlink()
    (dati_rw / MACROS).unlink()

    esiti = confronta(dati_rw)

    assert _stato(esiti, VIEWS) == NUOVO, "views.sql non veniva distribuito affatto"
    assert _stato(esiti, MACROS) == NUOVO


def test_le_viste_consolidate_dall_ufficio_sopravvivono_all_allineamento(dati_rw: Path) -> None:
    _consolida_una_vista(dati_rw)
    # Il repo dati torna indietro sulla base, come dopo un aggiornamento
    # dell'immagine: la regione generata però resta dov'è.
    testo = (dati_rw / VIEWS).read_text(encoding="utf-8")
    assert "v_collaudo_spesa" in testo

    _allinea(dati_rw)

    dopo = (dati_rw / VIEWS).read_text(encoding="utf-8")
    assert "v_collaudo_spesa" in dopo, "l'allineamento ha cancellato il lavoro dell'ufficio"
    assert "v_cantiere_costi" in dopo, "…e deve comunque portare la base nuova"
    conn = connect(dati_rw)
    try:
        conn.execute("SELECT * FROM v_collaudo_spesa LIMIT 1")
    finally:
        conn.close()


def test_il_consolidamento_non_conta_come_modifica_a_mano(dati_rw: Path) -> None:
    """Se contasse, il catalogo base resterebbe indietro proprio dove serve.

    Il commit del consolidamento tocca solo la regione generata, che il
    reinnesto conserva parola per parola: trattarlo come una modifica a valle
    bloccherebbe l'aggiornamento senza proteggere niente.
    """
    _consolida_una_vista(dati_rw)

    assert _stato(confronta(dati_rw), VIEWS) != DIVERGENTE
