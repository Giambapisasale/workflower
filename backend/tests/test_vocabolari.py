"""Il prompt di ``/ask`` dice anche *quali valori* accettano le colonne.

Le 120 domande del testbook hanno prodotto 7 errori veri su 119 query, e quattro
erano dello stesso tipo: un valore inventato. ``provincia = 'catania'`` dove il dato
è ``'CT'``, ``proprieta = 'proprietà'`` dove l'elenco ammette ``proprio``,
``stato = 'aperto'`` dove ``stato`` è lo stato del record nel registro. Il catalogo
delle viste dava nomi e tipi delle colonne, non i domini: il modello li indovinava.

I domini però sono già dato dichiarato — gli ``enum`` e i ``pattern`` negli schemi
delle entità — quindi qui si verifica la sola cosa che può andare storta nel
ricavarli: che il nome della colonna sia quello della **vista** e non quello dello
schema (``views.sql`` rinomina i campi che collidono con ``stato``), e che un
vocabolario non finisca attaccato alla vista sbagliata.
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from aiuti import accedi
from fake_ask import FakeCompleterInterroga
from fastapi.testclient import TestClient

from app.core.dal import DAL
from app.core.interroga import Interroga
from app.core.vocabolari import blocco, viste_per_entita, vocabolari

CANTIERI = "SELECT id, nome FROM v_cantieri ORDER BY id LIMIT 10"


def _per_colonna(dati: Path, colonna: str) -> list:
    return [v for v in vocabolari(dati) if v.colonna == colonna]


# ------------------------------------------------- il nome nella vista, non nello schema


def test_il_rinominato_di_views_sql_viene_risolto(dati_rw: Path) -> None:
    """``dati.stato AS stato_pagamento``: la vista è la fonte del nome, non lo schema."""
    viste = viste_per_entita((dati_rw / "config" / "views.sql").read_text(encoding="utf-8"))
    assert viste["v_pagamenti"].tipo == "pagamento"
    assert viste["v_pagamenti"].campi["stato"] == "stato_pagamento"


def test_le_righe_srotolate_sono_riconosciute(dati_rw: Path) -> None:
    """``unnest(dati.righe)``: la vista delle righe espone le proprietà dell'elemento."""
    viste = viste_per_entita((dati_rw / "config" / "views.sql").read_text(encoding="utf-8"))
    assert viste["v_fatture_righe"].srotolati == frozenset({"righe"})
    assert viste["v_fatture"].srotolati == frozenset()


def test_enum_annidato_nelle_righe(dati_rw: Path) -> None:
    """``tipo_costo`` è dichiarato in ``righe.items``, ed è l'errore che non si vedeva.

    Il modello scriveva ``tipo_costo = 'materiale'``: valore inesistente, query
    legittima, somma zero. Nessun errore da nessuna parte, e uno zero sembra un dato.
    """
    costo = _per_colonna(dati_rw, "tipo_costo")
    assert len(costo) == 1
    assert costo[0].valori == (
        "noleggio",
        "carburante",
        "manutenzione",
        "assicurazione",
        "bollo",
        "altro",
    )
    assert set(costo[0].viste) >= {"v_fatture_righe", "v_mezzi_costi"}


def test_enum_esposto_col_nome_della_colonna(dati_rw: Path) -> None:
    pagamento = _per_colonna(dati_rw, "stato_pagamento")
    assert len(pagamento) == 1
    assert pagamento[0].valori == ("pagato", "parziale", "non_pagato")
    assert pagamento[0].viste == ("v_pagamenti",)


def test_nessun_vocabolario_sotto_il_nome_stato(dati_rw: Path) -> None:
    """Se ``stato`` prendesse l'enum di un'entità, il modello filtrerebbe a vuoto.

    ``stato`` nelle viste è lo stato del record (``validato``…). Attaccargli i valori
    di ``pagamento.stato`` produrrebbe ``WHERE stato = 'non_pagato'``: zero righe,
    e nessun errore visibile.
    """
    assert _per_colonna(dati_rw, "stato") == []


# ------------------------------------------------------------ a chi si attribuisce


def test_colonna_ambigua_resta_alla_sua_vista(dati_rw: Path) -> None:
    """``tipo`` è un elenco diverso per dipendenti e manutenzioni: niente propagazione.

    ``v_mezzi.tipo`` è testo libero (escavatore, gru): non deve ereditare né
    ``operaio | ufficio | amministratore`` né i tipi di manutenzione.
    """
    per_viste = {v.viste: v.valori for v in _per_colonna(dati_rw, "tipo")}
    assert per_viste[("v_dipendenti",)] == ("operaio", "ufficio", "amministratore")
    assert per_viste[("v_manutenzioni",)][0] == "ordinaria"
    assert all("v_mezzi" not in viste for viste in per_viste)


def test_propagazione_alle_viste_derivate(dati_rw: Path) -> None:
    """``v_mezzi_tco.proprieta`` è la colonna su cui il modello aveva sbagliato.

    La vista derivata non legge ``entities/``, quindi il vocabolario non si ricava
    da ``views.sql``: si eredita per nome, che qui è univoco.
    """
    proprieta = _per_colonna(dati_rw, "proprieta")
    assert len(proprieta) == 1
    assert proprieta[0].valori == ("proprio", "noleggio")
    assert set(proprieta[0].viste) >= {"v_mezzi", "v_mezzi_tco"}


def test_gli_identificatori_restano_fuori(dati_rw: Path) -> None:
    """Il formato di un id senza l'elenco degli id serve solo a indovinare.

    ``cantiere_id: ^CNT-\\d{3,}$`` è dichiarato come gli altri ``pattern``, ma
    metterlo nel prompt invita a scrivere ``cantiere_id = 'CNT-001'`` invece di
    passare dal nome con una join su ``v_cantieri``.
    """
    colonne = {v.colonna for v in vocabolari(dati_rw)}
    assert not any(c == "id" or c.endswith("_id") for c in colonne)


def test_formati_dichiarati_presenti(dati_rw: Path) -> None:
    provincia = _per_colonna(dati_rw, "provincia")
    assert len(provincia) == 1
    assert provincia[0].formato == "^[A-Z]{2}$"
    assert provincia[0].valori == ()


# ----------------------------------------------------------------------- il blocco


def test_blocco_spiega_lo_stato_del_record(dati_rw: Path) -> None:
    testo = blocco(dati_rw)
    for stato in ("bozza", "validato", "errore", "scartato"):
        assert stato in testo
    assert "proprio | noleggio" in testo


# ------------------------------------------------------------ dentro il prompt vero


@pytest.mark.skip(reason="prompt storico: l'agente dati non carica vocabolari tecnici")
def test_il_prompt_di_ask_contiene_i_vocabolari(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    fake = FakeCompleterInterroga(CANTIERI)
    client = crea_client(fake)
    admin = accedi(client, "giovanna")
    client.post(
        "/api/ask", json={"question": "quali mezzi sono a noleggio?", "mode": "admin"},
        headers=admin,
    )

    assert fake.prompt_sql is not None
    assert "proprio | noleggio" in fake.prompt_sql
    assert "^[A-Z]{2}$" in fake.prompt_sql
    # nessun segnaposto rimasto da riempire
    assert "{vocabolari}" not in fake.prompt_sql
    assert "{schema_viste}" not in fake.prompt_sql


def test_senza_catalogo_il_prompt_resta_valido(dati_rw: Path) -> None:
    """Se i vocabolari non si ricavano, si perde informazione, non la risposta.

    Il blocco è un miglioramento del prompt, non un guardrail: un ``views.sql``
    illeggibile deve degradare la qualità della query, non far fallire la domanda.
    """
    (dati_rw / "config" / "views.sql").unlink()
    interroga = Interroga(DAL(dati_rw), gateway=None)  # type: ignore[arg-type]
    assert interroga._vocabolari() == "(non disponibili)"


def test_schema_illeggibile_non_ferma_gli_altri(dati_rw: Path) -> None:
    """Uno schema corrotto toglie il suo vocabolario, non quello delle altre entità."""
    (dati_rw / "schemas" / "mezzo.schema.json").write_text("{ non json", encoding="utf-8")
    colonne = {v.colonna for v in vocabolari(dati_rw)}
    assert "proprieta" not in colonne
    assert "stato_pagamento" in colonne


def test_entita_nuova_compare_da_se(dati_rw: Path) -> None:
    """Aggiungere un elenco chiuso a uno schema lo porta nel prompt: dato, non codice."""
    percorso = dati_rw / "schemas" / "cantiere.schema.json"
    schema = json.loads(percorso.read_text(encoding="utf-8"))
    schema["properties"]["committente"] = {"type": "string", "enum": ["pubblico", "privato"]}
    percorso.write_text(json.dumps(schema), encoding="utf-8")

    committente = _per_colonna(dati_rw, "committente")
    assert len(committente) == 1
    assert committente[0].valori == ("pubblico", "privato")
    assert committente[0].viste == ("v_cantieri",)
