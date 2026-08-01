"""L'azienda corrente: dato in ``config/azienda.json``, non variabile d'ambiente.

Il punto delicato non è il salvataggio — è la **lettura**, che sta sulla strada
dell'ingestione: un file assente (repo dati creato prima che la sezione
esistesse) o corrotto non deve fermare l'elaborazione dei documenti.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from aiuti import accedi
from fake_llm import FakeCompleter
from fastapi.testclient import TestClient
from git import Repo

from app.core.azienda import RELATIVO, Azienda, AziendaNonValida, leggi, scrivi, valida
from app.core.dal import DAL
from app.core.gateway import Gateway
from app.core.runtime import WorkflowRuntime

DATI = {
    "denominazione": "Costruzioni Aitho S.r.l.",
    "indirizzo": "Viale Africa 31, 95129 Catania",
    "partita_iva": "04512340871",
}


# ------------------------------------------------------------------- lettura


def test_seed_configura_la_denominazione(dati_rw: Path) -> None:
    azienda = leggi(dati_rw)
    assert azienda.denominazione == "Costruzioni Aitho S.r.l."
    assert azienda.configurata()
    assert azienda.partita_iva == "", "il seed non deve inventare una partita IVA"


def test_file_assente_non_e_un_errore(tmp_path: Path) -> None:
    """Un repo dati creato prima di questa sezione: campi vuoti, nessuna eccezione."""
    azienda = leggi(tmp_path)
    assert azienda.come_dizionario() == {
        "denominazione": "",
        "indirizzo": "",
        "partita_iva": "",
    }
    assert not azienda.configurata()


def test_file_corrotto_degrada_e_non_ferma_l_ingestione(dati_rw: Path) -> None:
    (dati_rw / RELATIVO).write_text("{non è json", encoding="utf-8")
    assert not leggi(dati_rw).configurata()


# ----------------------------------------------------------------- validazione


def test_denominazione_obbligatoria() -> None:
    with pytest.raises(AziendaNonValida, match="denominazione"):
        valida({"denominazione": "   ", "indirizzo": "via Roma 1", "partita_iva": ""})


def test_spazi_intorno_ai_valori_non_contano() -> None:
    azienda = valida({"denominazione": "  Aitho S.r.l. ", "partita_iva": " 04512340871 "})
    assert azienda.denominazione == "Aitho S.r.l."
    assert azienda.partita_iva == "04512340871"


def test_partita_iva_estera_accettata() -> None:
    """Il campo serve a confrontare, non a certificare: una forma legittima ma
    inattesa non deve essere rifiutata."""
    assert valida({"denominazione": "Bau GmbH", "partita_iva": "DE123456789"}).partita_iva


def test_campo_troppo_lungo_rifiutato() -> None:
    with pytest.raises(AziendaNonValida, match="troppo lungo"):
        valida({"denominazione": "A" * 201})


# ------------------------------------------------------------------------ API


def test_lettura_e_scrittura_dalla_ui(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    client = crea_client()
    admin = accedi(client, "giovanna")

    corpo = client.put("/api/config/azienda", headers=admin, json=DATI).json()
    assert corpo["configurata"] is True
    assert corpo["partita_iva"] == "04512340871"

    assert client.get("/api/config/azienda", headers=admin).json() == corpo
    assert leggi(dati_rw).partita_iva == "04512340871"


def test_ogni_modifica_e_un_commit(crea_client: Callable[..., TestClient], dati_rw: Path) -> None:
    client = crea_client()
    prima = Repo(dati_rw).head.commit.hexsha

    client.put("/api/config/azienda", headers=accedi(client, "giovanna"), json=DATI)

    repo = Repo(dati_rw)
    assert repo.head.commit.hexsha != prima
    assert "giovanna" in str(repo.head.commit.message)
    assert not repo.is_dirty(), "il file deve restare committato, non sporcare il repo"


def test_denominazione_vuota_rifiutata_dall_api(crea_client: Callable[..., TestClient]) -> None:
    client = crea_client()
    risposta = client.put(
        "/api/config/azienda", headers=accedi(client, "giovanna"), json={"denominazione": ""}
    )
    assert risposta.status_code == 422
    assert "denominazione" in risposta.json()["detail"]


# ------------------------------------------------- riconoscimento sul documento


@pytest.mark.parametrize(
    "letto",
    [
        "Costruzioni Aitho S.r.l.",
        "COSTRUZIONI AITHO SRL",  # sigla e maiuscole a piacere del fornitore
        "Aitho Costruzioni S.r.l.",  # parole invertite
        "Costruzioni Aiho S.r.l.",  # refuso / scivolone dell'OCR
        "Spett.le Costruzioni Aitho S.r.l. - Viale Africa 31, Catania",  # riga intera
    ],
)
def test_varianti_dello_stesso_nome_sono_noi(letto: str) -> None:
    assert Azienda(denominazione="Costruzioni Aitho S.r.l.").riconosce(letto)


@pytest.mark.parametrize(
    "letto",
    [
        "Edil Sud S.r.l.",
        "Costruzioni Etna S.r.l.",  # condivide solo la parola generica
        "Costruzioni Delta S.r.l.",
        "Immobiliare Mediterranea S.r.l.",
    ],
)
def test_altre_imprese_non_passano(letto: str) -> None:
    assert not Azienda(denominazione="Costruzioni Aitho S.r.l.").riconosce(letto)


def test_partita_iva_batte_il_nome() -> None:
    """Se l'identificativo coincide, il nome non conta: è lo stesso soggetto."""
    azienda = Azienda(denominazione="Costruzioni Aitho S.r.l.", partita_iva="04512340871")
    assert azienda.riconosce("Ditta senza nome riconoscibile - P.IVA 04512340871")


def test_senza_configurazione_non_si_sospetta_di_nessuno() -> None:
    """Un controllo che non si può fare non deve diventare un sospetto: manderebbe
    in revisione ogni documento, e un allarme sempre acceso non lo guarda più nessuno."""
    assert Azienda().riconosce("Chiunque S.r.l.")
    assert Azienda(denominazione="Costruzioni Aitho S.r.l.").riconosce(None)
    assert Azienda(denominazione="Costruzioni Aitho S.r.l.").riconosce("  ")


# --------------------------------------------------------- effetto sul workflow


def _runtime(dati_rw: Path) -> WorkflowRuntime:
    return WorkflowRuntime(DAL(dati_rw), Gateway(completer=FakeCompleter(dati_rw)))


def _fattura_per(dati_rw: Path, fixtures_dir: Path, destinatario: str) -> str:
    """Una fattura delle fixture, reintestata a chi si vuole."""
    from app import fixtures

    nome = "fattura-calcestruzzi-etna.pdf"
    spec = next(f for f in fixtures.FIXTURES if f["file"] == nome)
    relativo = f"blobs/caricati/2026/{destinatario[:6].replace(' ', '')}-{nome}"
    percorso = dati_rw / relativo
    percorso.parent.mkdir(parents=True, exist_ok=True)
    originale = fixtures.DESTINATARIO
    try:
        fixtures.DESTINATARIO = destinatario
        fixtures.disegna(percorso, spec)
    finally:
        fixtures.DESTINATARIO = originale
    return relativo


def test_fattura_intestata_a_noi_passa_liscia(dati_rw: Path, fixtures_dir: Path) -> None:
    doc = _fattura_per(dati_rw, fixtures_dir, "Costruzioni Aitho S.r.l. - Viale Africa 31")
    esito = _runtime(dati_rw).esegui("carica-fattura", doc)

    assert esito.esito == "ok"
    assert esito.issue_id is None
    assert esito.richiede_revisione is False


def test_fattura_intestata_ad_altri_non_blocca_ma_segnala(
    dati_rw: Path, fixtures_dir: Path
) -> None:
    """Capita che un fornitore sbagli intestazione: si registra e si avvisa."""
    doc = _fattura_per(dati_rw, fixtures_dir, "Costruzioni Delta S.r.l. - Via Etnea 5")
    esito = _runtime(dati_rw).esegui("carica-fattura", doc)

    assert esito.esito == "ok", "un'intestazione sbagliata non deve fermare l'ingestione"
    assert esito.entity_id, "la bozza si salva comunque"
    assert esito.richiede_revisione is True
    assert esito.issue_id, "l'ufficio deve trovarne traccia nelle segnalazioni"

    issue = next(i for i in DAL(dati_rw).list_issues() if i.id == esito.issue_id)
    assert "Costruzioni Delta" in issue.testo
    assert "Costruzioni Aitho" in issue.testo


def test_azienda_non_configurata_spegne_il_controllo(dati_rw: Path, fixtures_dir: Path) -> None:
    scrivi(dati_rw, Azienda())
    doc = _fattura_per(dati_rw, fixtures_dir, "Costruzioni Delta S.r.l. - Via Etnea 5")

    esito = _runtime(dati_rw).esegui("carica-fattura", doc)
    assert esito.issue_id is None
    assert esito.richiede_revisione is False


def test_workflow_senza_la_dichiarazione_non_controlla_niente(
    dati_rw: Path, fixtures_dir: Path
) -> None:
    """Il controllo è dichiarato dal manifest: toglierlo riporta al comportamento
    di prima, senza toccare codice."""
    manifest = dati_rw / "workflows" / "carica-fattura" / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("verifica_destinatario: true", ""),
        encoding="utf-8",
    )
    doc = _fattura_per(dati_rw, fixtures_dir, "Costruzioni Delta S.r.l. - Via Etnea 5")

    esito = _runtime(dati_rw).esegui("carica-fattura", doc)
    assert esito.issue_id is None
    assert esito.richiede_revisione is False


def test_il_destinatario_letto_finisce_nella_bozza(dati_rw: Path, fixtures_dir: Path) -> None:
    doc = _fattura_per(dati_rw, fixtures_dir, "Costruzioni Delta S.r.l. - Via Etnea 5")
    esito = _runtime(dati_rw).esegui("carica-fattura", doc)

    dati = DAL(dati_rw).read("fattura", str(esito.entity_id)).dati
    assert dati["destinatario"] == "Costruzioni Delta S.r.l."


def test_riservata_all_ufficio(crea_client: Callable[..., TestClient]) -> None:
    """L'azienda è il riferimento con cui si giudicano i documenti: non la tocca
    chi carica le foto dal cantiere."""
    client = crea_client()
    salvo = accedi(client, "salvo")
    assert client.get("/api/config/azienda", headers=salvo).status_code == 403
    assert client.put("/api/config/azienda", headers=salvo, json=DATI).status_code == 403
    assert client.get("/api/config/azienda").status_code == 401
