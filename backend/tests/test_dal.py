"""DAL: CRUD, validazione schema e commit git verificato (AC M1)."""

from pathlib import Path
from typing import Any

import pytest
from git import Repo

from app.core.dal import (
    DAL,
    AlreadyExistsError,
    InvalidIdError,
    NotFoundError,
    SchemaValidationError,
    UnknownTypeError,
)
from app.models.envelope import Envelope, Meta


def fattura(entity_id: str = "FT-2026-0100", **dati_override: Any) -> Envelope:
    dati: dict[str, Any] = {
        "fornitore_id": "FRN-001",
        "cantiere_id": "CNT-001",
        "numero": "100/2026",
        "data": "2026-06-30",
        "imponibile": 100.0,
        "iva": 22.0,
        "totale": 122.0,
        "ritenuta_acconto": None,
        "righe": [{"descrizione": "Voce di prova", "importo": 100.0}],
    }
    dati.update(dati_override)
    return Envelope(id=entity_id, tipo="fattura", dati=dati, meta=Meta(run_id="run-test"))


def commit_count(data_dir: Path) -> int:
    return sum(1 for _ in Repo(data_dir).iter_commits())


def head_message(data_dir: Path) -> str:
    return str(Repo(data_dir).head.commit.message)


def test_create_e_read(data_repo: Path) -> None:
    dal = DAL(data_repo)
    before = commit_count(data_repo)
    creato = dal.create(fattura())

    assert (data_repo / "entities" / "fatture" / "2026" / "FT-2026-0100.json").is_file()
    letto = dal.read("fattura", "FT-2026-0100")
    assert letto.dati == creato.dati
    assert letto.stato == "bozza"
    assert letto.meta.created is not None
    assert letto.meta.created == letto.meta.updated
    # commit git verificato
    assert commit_count(data_repo) == before + 1
    assert head_message(data_repo) == "fattura FT-2026-0100: crea [run-test]"


def test_create_duplicato(data_repo: Path) -> None:
    dal = DAL(data_repo)
    dal.create(fattura())
    with pytest.raises(AlreadyExistsError):
        dal.create(fattura())


def test_update(data_repo: Path) -> None:
    dal = DAL(data_repo)
    creato = dal.create(fattura())

    modificata = fattura(imponibile=200.0, iva=44.0, totale=244.0)
    dal.update(modificata, run_id="run-upd")

    letto = dal.read("fattura", "FT-2026-0100")
    assert letto.dati["totale"] == 244.0
    assert letto.meta.created == creato.meta.created  # immutabile
    assert head_message(data_repo) == "fattura FT-2026-0100: aggiorna [run-upd]"


def test_update_inesistente(data_repo: Path) -> None:
    with pytest.raises(NotFoundError):
        DAL(data_repo).update(fattura())


def test_schema_respinto_e_nessun_commit(data_repo: Path) -> None:
    dal = DAL(data_repo)
    before = commit_count(data_repo)
    with pytest.raises(SchemaValidationError) as excinfo:
        dal.create(fattura(totale="centoventidue"))

    assert "totale" in str(excinfo.value)
    assert not (data_repo / "entities" / "fatture" / "2026" / "FT-2026-0100.json").exists()
    assert commit_count(data_repo) == before


def test_campo_extra_respinto(data_repo: Path) -> None:
    with pytest.raises(SchemaValidationError):
        DAL(data_repo).create(fattura(campo_inventato=1))


def test_campo_obbligatorio_mancante(data_repo: Path) -> None:
    env = fattura()
    del env.dati["ritenuta_acconto"]  # richiesto esplicito: se assente deve essere null
    with pytest.raises(SchemaValidationError):
        DAL(data_repo).create(env)


def test_tipo_sconosciuto(data_repo: Path) -> None:
    env = Envelope(id="ORD-001", tipo="ordine", dati={})
    with pytest.raises(UnknownTypeError):
        DAL(data_repo).create(env)


def test_id_non_valido(data_repo: Path) -> None:
    with pytest.raises(InvalidIdError):
        DAL(data_repo).read("fattura", "..\\..\\evil")


def test_read_mancante(data_repo: Path) -> None:
    with pytest.raises(NotFoundError):
        DAL(data_repo).read("fattura", "FT-2026-9999")


def test_set_validato(data_repo: Path) -> None:
    dal = DAL(data_repo)
    dal.create(fattura())

    env = dal.set_validato("fattura", "FT-2026-0100", validato_da="admin@aitho.it")

    assert env.stato == "validato"
    assert env.meta.validato_da == "admin@aitho.it"
    assert dal.read("fattura", "FT-2026-0100").stato == "validato"
    assert head_message(data_repo) == "fattura FT-2026-0100: valida [manual]"


def test_delete(data_repo: Path) -> None:
    dal = DAL(data_repo)
    dal.create(fattura())
    percorso = data_repo / "entities" / "fatture" / "2026" / "FT-2026-0100.json"
    assert percorso.is_file()
    before = commit_count(data_repo)

    dal.delete("fattura", "FT-2026-0100", tag="manual:giovanna")

    assert not percorso.exists()
    with pytest.raises(NotFoundError):
        dal.read("fattura", "FT-2026-0100")
    # commit git verificato (git rm), storia intatta per il rollback
    assert commit_count(data_repo) == before + 1
    assert head_message(data_repo) == "fattura FT-2026-0100: elimina [manual:giovanna]"


def test_delete_inesistente(data_repo: Path) -> None:
    with pytest.raises(NotFoundError):
        DAL(data_repo).delete("fattura", "FT-2026-9999")


def test_delete_id_non_valido(data_repo: Path) -> None:
    with pytest.raises(InvalidIdError):
        DAL(data_repo).delete("fattura", "..\\..\\evil")


def test_list_all(data_repo: Path) -> None:
    dal = DAL(data_repo)
    dal.create(fattura("FT-2026-0100"))
    dal.create(fattura("FT-2026-0101"))
    assert [e.id for e in dal.list_all("fattura")] == ["FT-2026-0100", "FT-2026-0101"]


def test_altri_tipi(data_repo: Path) -> None:
    dal = DAL(data_repo)
    cantiere = Envelope(
        id="CNT-100",
        tipo="cantiere",
        dati={
            "nome": "Cantiere di prova",
            "indirizzo": "Via Test 1",
            "comune": "Catania",
            "committente": "ACME",
            "budget": 1000.0,
            "data_inizio": "2026-01-01",
        },
    )
    dal.create(cantiere)
    assert (data_repo / "entities" / "cantieri" / "CNT-100.json").is_file()

    fornitore = Envelope(
        id="FRN-100",
        tipo="fornitore",
        dati={"ragione_sociale": "Prova S.r.l.", "partita_iva": "00000000000"},
    )
    dal.create(fornitore)
    assert dal.read("fornitore", "FRN-100").dati["ragione_sociale"] == "Prova S.r.l."
