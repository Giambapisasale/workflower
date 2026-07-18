"""M9 — computo, collegamento righe→voci, scostamento previsto/consuntivo.

Il collegamento è deterministico (tool cerca_voce_computo, §3.6): niente LLM.
Lo scostamento nasce dalle righe abbinate — è il "confronto computo/consuntivo".
"""

from pathlib import Path

from aiuti import accedi
from fastapi.testclient import TestClient

from app.core.collega import Collega
from app.core.dal import DAL
from app.core.tools import computo
from app.core.views import query
from app.models.envelope import Envelope, Meta


def _fattura_bozza(dal: DAL, righe_descrizioni: list[str]) -> str:
    """Crea una fattura bozza (CNT-001) con righe date, voce_computo_id assente."""
    entity_id = dal.prossimo_id("fattura", 2026)
    righe = [
        {"descrizione": d, "quantita": None, "unita_misura": None, "importo": 1000.0,
         "voce_computo_id": None}
        for d in righe_descrizioni
    ]
    envelope = Envelope(
        id=entity_id,
        tipo="fattura",
        stato="bozza",
        dati={
            "fornitore_id": "FRN-001",
            "cantiere_id": "CNT-001",
            "numero": "TEST-1",
            "data": "2026-07-01",
            "imponibile": 1000.0 * len(righe),
            "iva": 0.0,
            "totale": 1000.0 * len(righe),
            "ritenuta_acconto": None,
            "righe": righe,
        },
        meta=Meta(run_id="run-collega"),
    )
    dal.create(envelope, run_id="run-collega")
    return entity_id


# ------------------------------------------------------------------ tool


def test_cerca_voce_computo_trova_la_voce(dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    risultati = computo.cerca_voce_computo(dal, "CNT-001", "calcestruzzo strutturale")["risultati"]
    assert risultati[0]["voce_id"] == "VC1-02"
    # cantiere senza computo → nessun candidato
    assert computo.cerca_voce_computo(dal, "CNT-003", "qualsiasi")["risultati"] == []


# ------------------------------------------------------------- collega service


def test_collega_abbina_le_righe_alla_bozza(dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    entity_id = _fattura_bozza(
        dal,
        ["Muratura di tamponamento in blocchi", "Scavo di sbancamento e splateamento"],
    )
    esito = Collega(dal).abbina("fattura", entity_id)
    assert esito["abbinate"] == 2

    righe = dal.read("fattura", entity_id).dati["righe"]
    assert righe[0]["voce_computo_id"] == "VC1-04"  # muratura
    assert righe[1]["voce_computo_id"] == "VC1-01"  # scavo
    # resta bozza: l'abbinamento non valida
    assert dal.read("fattura", entity_id).stato == "bozza"


def test_collega_senza_computo_non_abbina(dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    # CNT-003 non ha computo nel seed
    entity_id = dal.prossimo_id("fattura", 2026)
    dal.create(
        Envelope(
            id=entity_id,
            tipo="fattura",
            stato="bozza",
            dati={
                "fornitore_id": "FRN-001", "cantiere_id": "CNT-003", "numero": "T2",
                "data": "2026-07-01", "imponibile": 100.0, "iva": 0.0, "totale": 100.0,
                "ritenuta_acconto": None,
                "righe": [{"descrizione": "x", "quantita": None, "unita_misura": None,
                           "importo": 100.0, "voce_computo_id": None}],
            },
            meta=Meta(run_id="run-x"),
        ),
        run_id="run-x",
    )
    esito = Collega(dal).abbina("fattura", entity_id)
    assert esito["senza_computo"] is True and esito["abbinate"] == 0


# ----------------------------------------------------------------- viste


def test_scostamento_dal_seed(dati_rw: Path) -> None:
    voci = query(
        dati_rw,
        "SELECT voce_id, previsto, consuntivo FROM v_scostamento_voci "
        "WHERE cantiere_id = 'CNT-002' ORDER BY voce_id",
    )
    per_voce = {v["voce_id"]: v for v in voci}
    assert per_voce["VC2-02"]["consuntivo"] == 5718.0  # blocchi + malta (FT-2026-0002)
    assert per_voce["VC2-04"]["consuntivo"] == 2362.0  # impianti (FT-2026-0005)
    assert per_voce["VC2-01"]["consuntivo"] == 0.0     # nessuna spesa abbinata


# --------------------------------------------------------------- endpoint API


def test_dashboard_scostamenti(client: TestClient) -> None:
    intestazioni = accedi(client, "giovanna")
    risposta = client.get("/api/dashboard/scostamenti?cantiere_id=CNT-001", headers=intestazioni)
    corpo = risposta.json()
    assert {c["cantiere_id"] for c in corpo["per_cantiere"]} >= {"CNT-001", "CNT-002"}
    assert all(v["cantiere_id"] == "CNT-001" for v in corpo["voci"])
    calcestruzzo = next(v for v in corpo["voci"] if v["voce_id"] == "VC1-02")
    assert calcestruzzo["consuntivo"] == 8330.0  # FT-2026-0001


def test_endpoint_collega_solo_fattura_ddt(client: TestClient, dati_rw: Path) -> None:
    intestazioni = accedi(client, "giovanna")
    entity_id = _fattura_bozza(DAL(dati_rw), ["Impianto elettrico civile"])
    esito = client.post(f"/api/review/{entity_id}/collega", headers=intestazioni).json()
    assert esito["abbinate"] == 1
    # un SAL non è collegabile (niente righe/voce_computo_id)
    negato = client.post("/api/review/SAL-2026-0001/collega", headers=intestazioni)
    assert negato.status_code == 422
