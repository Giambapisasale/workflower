"""Misurare un tier sull'interrogazione: domanda → query, giudicata sul risultato.

Il punto difficile non è far girare la misura, è **decidere quando una query è
giusta**. Confrontare le stringhe SQL non funziona: cambia un alias o l'ordine
delle righe e due risposte identiche sembrano diverse. Si confronta il
risultato, eseguendo riferimento e candidato sugli stessi dati nello stesso
istante.

E si dichiara cosa non si è potuto misurare: un caso il cui riferimento non
trova più niente non è un caso superato, è un caso **degenere** — lo pareggerebbe
qualunque modello muto.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from aiuti import accedi
from fake_ask import FakeCompleterInterroga
from fastapi.testclient import TestClient

from app.core.dal import DAL
from app.core.eval_interroga import EvalInterroga, normalizza, risposte_equivalenti, unisci
from app.core.gateway import Gateway
from app.core.golden import carica_golden, casi_domanda

T3 = "test/finto-t3"
CANTIERI = "SELECT id, nome FROM v_cantieri ORDER BY id LIMIT 10"
# stessa risposta, scritta in un altro modo: alias diversi, ordine righe diverso
CANTIERI_ALIAS = "SELECT id AS codice, nome AS titolo FROM v_cantieri ORDER BY nome DESC LIMIT 10"
# risposta diversa: le colonne sono scambiate di ruolo
CANTIERI_SCAMBIATI = "SELECT nome, id FROM v_cantieri ORDER BY id LIMIT 10"


class FakePerTier:
    """Doppio che risponde con una query diversa secondo il modello interpellato.

    Serve a simulare il caso interessante: T1 azzecca, T3 no (o viceversa).
    """

    def __init__(self, per_modello: dict[str, str], default: str) -> None:
        self.per_modello = per_modello
        self.default = default

    def __call__(
        self, *, model: str, messages: list[dict[str, Any]], **_ignorati: Any
    ) -> dict[str, Any]:
        sql = self.per_modello.get(model, self.default)
        return {
            "choices": [{"message": {"role": "assistant", "content": f"```sql\n{sql}\n```"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            "model": model,
            "_hidden_params": {"response_cost": 0.0001},
        }


def _valutatore(dati: Path, completer: object) -> EvalInterroga:
    return EvalInterroga(DAL(dati), Gateway(completer=completer, attesa_retry=0))


def _crea_caso(client: TestClient, domanda: str, sql: str) -> dict[str, Any]:
    admin = accedi(client, "giovanna")
    risposta = client.post(
        "/api/golden/domande", json={"domanda": domanda, "sql": sql}, headers=admin
    )
    assert risposta.status_code == 201, risposta.text
    return risposta.json()


# ------------------------------------------------------- equivalenza dei risultati


def test_alias_e_ordine_delle_righe_non_contano() -> None:
    """Due query che rispondono la stessa cosa scritta diversamente sono uguali."""
    a = [{"cantiere": "CNT-1", "speso": 1000.0}, {"cantiere": "CNT-2", "speso": 2000.0}]
    b = [{"id": "CNT-2", "totale": 2000.0}, {"id": "CNT-1", "totale": 1000.0}]
    assert risposte_equivalenti(a, b)


def test_l_ordine_delle_colonne_invece_conta() -> None:
    """Confondere previsto e consuntivo non è un dettaglio cosmetico."""
    previsto_consuntivo = [{"previsto": 100.0, "consuntivo": 200.0}]
    scambiati = [{"previsto": 200.0, "consuntivo": 100.0}]
    assert not risposte_equivalenti(previsto_consuntivo, scambiati)


def test_interi_e_decimali_sono_la_stessa_risposta() -> None:
    """``3`` e ``3.0`` sono lo stesso numero di fatture."""
    assert risposte_equivalenti([{"n": 3}], [{"n": 3.0}])
    # e il rumore in virgola mobile delle somme DOUBLE non è una differenza
    assert risposte_equivalenti([{"tot": 1000.0}], [{"tot": 1000.0000000001}])
    assert not risposte_equivalenti([{"tot": 1000.0}], [{"tot": 1000.01}])


def test_righe_in_piu_o_in_meno_sono_una_risposta_diversa() -> None:
    assert not risposte_equivalenti([{"n": 1}], [{"n": 1}, {"n": 2}])
    assert not risposte_equivalenti([], [{"n": 1}])


def test_normalizza_ignora_i_nomi_ma_non_i_valori() -> None:
    assert normalizza([{"a": 1, "b": "x"}]) == [(1.0, "x")]


# --------------------------------------------------- creazione dei casi golden


def test_una_domanda_e_la_sua_query_diventano_un_caso(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    caso = _crea_caso(client, "quali cantieri abbiamo?", CANTIERI)

    assert caso["id"].startswith("GOLD-")
    assert caso["righe"] > 0
    assert caso["validato_da"] == "giovanna"
    salvati = casi_domanda(dati_rw)
    assert [c.id for c in salvati] == [caso["id"]]
    assert salvati[0].tipo == "domanda"
    # l'atteso è la query approvata, non le righe: le righe invecchiano
    assert salvati[0].sql_riferimento == CANTIERI
    assert salvati[0].doc is None


def test_una_query_senza_righe_non_e_un_riferimento(
    crea_client: Callable[..., TestClient],
) -> None:
    """Un riferimento vuoto lo pareggia qualunque candidato muto: va rifiutato subito."""
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    admin = accedi(client, "giovanna")
    risposta = client.post(
        "/api/golden/domande",
        json={"domanda": "cantieri inesistenti?", "sql": "SELECT id FROM v_cantieri WHERE 1=0"},
        headers=admin,
    )
    assert risposta.status_code == 400
    assert "non restituisce righe" in risposta.json()["detail"]


def test_i_guardrail_valgono_anche_qui(crea_client: Callable[..., TestClient]) -> None:
    """Il server non si fida della query che riceve: la rivalida e la esegue."""
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    admin = accedi(client, "giovanna")
    for sql in ("DELETE FROM v_fatture", "SELECT * FROM entities", "SELECT nope FROM v_cantieri"):
        risposta = client.post(
            "/api/golden/domande", json={"domanda": "x", "sql": sql}, headers=admin
        )
        assert risposta.status_code == 400, sql


def test_l_operatore_non_puo_fissare_i_casi(crea_client: Callable[..., TestClient]) -> None:
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    op = accedi(client, "salvo")
    risposta = client.post(
        "/api/golden/domande", json={"domanda": "x", "sql": CANTIERI}, headers=op
    )
    assert risposta.status_code == 403


def test_i_due_tipi_di_caso_convivono_e_si_filtrano(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    """L'Improver rigioca documenti: un caso-domanda non deve finirgli fra i piedi."""
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    documenti_del_seed = carica_golden(dati_rw, tipo="documento")
    assert documenti_del_seed, "il seed porta casi-documento: è il termine di paragone"
    nuovo = _crea_caso(client, "quali cantieri?", CANTIERI)

    # il caso-domanda si aggiunge senza mescolarsi con quelli sui documenti
    assert len(carica_golden(dati_rw)) == len(documenti_del_seed) + 1
    assert carica_golden(dati_rw, tipo="documento") == documenti_del_seed
    assert [c.id for c in carica_golden(dati_rw, tipo="domanda")] == [nuovo["id"]]
    # e l'elenco per l'ufficio non si rompe sul caso senza documento
    admin = accedi(client, "giovanna")
    elenco = client.get("/api/golden", headers=admin).json()["golden"]
    voce = next(v for v in elenco if v["id"] == nuovo["id"])
    assert voce["tipo"] == "domanda"
    assert voce["doc"] is None
    assert voce["originale_presente"] is True
    assert {v["tipo"] for v in elenco} == {"domanda", "documento"}


# ------------------------------------------------------------------ la misura


def test_stesso_modello_sui_due_tier_nessuna_regressione(
    crea_client: Callable[..., TestClient], dati_rw: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    _crea_caso(client, "quali cantieri abbiamo?", CANTIERI)
    monkeypatch.setenv("LLM_T3_MODEL", T3)

    report = _valutatore(dati_rw, FakePerTier({}, CANTIERI)).valuta()

    assert report["casi"] == 1
    assert report["degeneri"] == 0
    assert report["candidato"] == {"eseguibile": 1.0, "risposta_uguale": 1.0}
    assert report["riferimento"] == {"eseguibile": 1.0, "risposta_uguale": 1.0}
    assert report["regressione"] is False
    assert report["pronto_per_t3"] is True


def test_una_query_scritta_diversamente_conta_come_giusta(
    crea_client: Callable[..., TestClient], dati_rw: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """È il senso di tutto: si giudica la risposta, non il testo della query."""
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    _crea_caso(client, "quali cantieri abbiamo?", CANTIERI)
    monkeypatch.setenv("LLM_T3_MODEL", T3)

    report = _valutatore(dati_rw, FakePerTier({T3: CANTIERI_ALIAS}, CANTIERI)).valuta()

    assert report["candidato"]["risposta_uguale"] == 1.0
    assert report["dettaglio"][0]["candidato"]["sql"] != CANTIERI


def test_un_candidato_che_risponde_altro_e_una_regressione(
    crea_client: Callable[..., TestClient], dati_rw: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    _crea_caso(client, "quali cantieri abbiamo?", CANTIERI)
    monkeypatch.setenv("LLM_T3_MODEL", T3)

    report = _valutatore(dati_rw, FakePerTier({T3: CANTIERI_SCAMBIATI}, CANTIERI)).valuta()

    # la query gira (è SQL valido) ma la risposta è un'altra: i due numeri divergono
    assert report["candidato"] == {"eseguibile": 1.0, "risposta_uguale": 0.0}
    assert report["riferimento"]["risposta_uguale"] == 1.0
    assert report["regressione"] is True
    assert report["pronto_per_t3"] is False


def test_un_candidato_che_non_produce_sql_valido(
    crea_client: Callable[..., TestClient], dati_rw: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"Non ha prodotto una query" e "ha risposto un'altra cosa" sono due guasti diversi."""
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    _crea_caso(client, "quali cantieri abbiamo?", CANTIERI)
    monkeypatch.setenv("LLM_T3_MODEL", T3)

    report = _valutatore(
        dati_rw, FakePerTier({T3: "SELECT colonna_che_non_esiste FROM v_cantieri"}, CANTIERI)
    ).valuta()

    esito = report["dettaglio"][0]["candidato"]
    assert esito["eseguibile"] == 0
    assert esito["risposta_uguale"] == 0
    assert "errore" in esito


def test_un_caso_il_cui_riferimento_non_gira_piu_e_degenere(
    crea_client: Callable[..., TestClient], dati_rw: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Il catalogo delle viste è cambiato sotto il caso: escluso e dichiarato."""
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    creato = _crea_caso(client, "quali cantieri?", CANTIERI)
    # il caso viene salvato valido, poi si rompe il riferimento a mano
    caso = dati_rw / "golden" / f"{creato['id']}.json"
    caso.write_text(
        caso.read_text(encoding="utf-8").replace("v_cantieri", "v_sparita"), encoding="utf-8"
    )
    monkeypatch.setenv("LLM_T3_MODEL", T3)

    report = _valutatore(dati_rw, FakePerTier({}, CANTIERI)).valuta()

    assert report["casi"] == 0
    assert report["casi_totali"] == 1
    assert report["degeneri"] == 1
    # senza casi validi non si promuove niente: l'assenza di prove non è una prova
    assert report["pronto_per_t3"] is False


def test_senza_casi_non_si_promuove_niente(
    crea_client: Callable[..., TestClient], dati_rw: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_T3_MODEL", T3)
    report = _valutatore(dati_rw, FakePerTier({}, CANTIERI)).valuta()
    assert report == {
        "casi": 0,
        "casi_totali": 0,
        "degeneri": 0,
        "candidato": {"eseguibile": 0.0, "risposta_uguale": 0.0},
        "riferimento": {"eseguibile": 0.0, "risposta_uguale": 0.0},
        "regressione": False,
        "pronto_per_t3": False,
        "dettaglio": [],
    }


# ------------------------------------------------------------ un solo verdetto


def test_l_interrogazione_entra_nel_verdetto_unico() -> None:
    """``pronti`` e ``regressioni`` restano l'unico posto da leggere."""
    documenti = {"pronti": ["carica-fattura@1.0"], "regressioni": []}
    unito = unisci(documenti, {"pronto_per_t3": True, "regressione": False})
    assert unito["pronti"] == ["carica-fattura@1.0", "interroga"]
    assert unito["regressioni"] == []

    unito = unisci(documenti, {"pronto_per_t3": False, "regressione": True})
    assert unito["pronti"] == ["carica-fattura@1.0"]
    assert unito["regressioni"] == ["interroga"]
    # le metriche non si mescolano: misurano cose diverse
    assert unito["interrogazione"]["regressione"] is True


def test_il_report_dell_api_contiene_le_due_misure(
    crea_client: Callable[..., TestClient],
) -> None:
    client = crea_client(FakeCompleterInterroga(CANTIERI))
    _crea_caso(client, "quali cantieri?", CANTIERI)
    admin = accedi(client, "giovanna")

    corpo = client.get("/api/dataset/eval-t3", headers=admin).json()

    assert corpo["interrogazione"]["casi"] == 1
    assert "workflow" in corpo  # la misura sui documenti è ancora al suo posto
    assert "modalita_documento" in corpo
