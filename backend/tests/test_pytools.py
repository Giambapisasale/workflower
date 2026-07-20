"""M15 — Registry dei tool Python consolidati (dato) + ciclo di vita.

La terza forma di consolidamento del §3.6: un tool Python posato in
``data/tools/`` è caricato come dato, compare nel registro con stato di ciclo e
contatori, ed è invocabile da un workflow **solo attraverso la sandbox** (M14).
Il DAL è la rete di sicurezza: esegue i test in sandbox prima di committare.

Lo scenario canonico è la **ritenuta d'acconto** (M5): un calcolo deterministico
oggi affidato al prompt, il primo candidato naturale a diventare tool Python.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from aiuti import accedi
from fake_ask import FakeCompleterInterroga
from fastapi.testclient import TestClient

from app.core.dal import DAL, CatalogoNonValido
from app.core.pytools import (
    PyToolError,
    carica_pytools,
    leggi_pytools,
    percorso_sorgente,
    prepara_pytool,
)
from app.core.tools import ToolError, Toolset

# --- il tool canonico: ritenuta d'acconto, puro Decimal, nessun import di rete/FS

CODICE_RITENUTA = """\
from decimal import Decimal, ROUND_HALF_UP


def esegui(imponibile, aliquota):
    imp = Decimal(str(imponibile))
    ali = Decimal(str(aliquota))
    ritenuta = (imp * ali / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return {"ritenuta": float(ritenuta)}
"""

SCHEMA_RITENUTA = {
    "type": "function",
    "function": {
        "name": "calcola_ritenuta",
        "description": "Calcola la ritenuta d'acconto su un imponibile data l'aliquota.",
        "parameters": {
            "type": "object",
            "properties": {
                "imponibile": {"type": "number"},
                "aliquota": {"type": "number"},
            },
            "required": ["imponibile", "aliquota"],
        },
    },
}

TEST_RITENUTA = [
    {"argomenti": {"imponibile": 1000, "aliquota": 20}, "atteso": {"ritenuta": 200.0}},
    {"argomenti": {"imponibile": 1500, "aliquota": 20}, "atteso": {"ritenuta": 300.0}},
]


def _consolida_ritenuta(dal: DAL, *, ciclo: str = "consolidata") -> dict:
    return dal.consolida_pytool(
        nome="calcola_ritenuta",
        codice=CODICE_RITENUTA,
        schema=SCHEMA_RITENUTA,
        test=TEST_RITENUTA,
        fingerprint=None,
        creato_da="giovanna",
        ciclo=ciclo,
    )


# --------------------------------------------------------------- unit / prepare


def test_prepara_rifiuta_nome_non_valido() -> None:
    with pytest.raises(PyToolError, match="nome non valido"):
        prepara_pytool("Calcolo-Ritenuta", CODICE_RITENUTA, SCHEMA_RITENUTA, TEST_RITENUTA)


def test_prepara_rifiuta_schema_incoerente() -> None:
    schema = {"type": "function", "function": {"name": "altro", "parameters": {}}}
    with pytest.raises(PyToolError, match="function.name"):
        prepara_pytool("calcola_ritenuta", CODICE_RITENUTA, schema, TEST_RITENUTA)


def test_prepara_rifiuta_senza_test() -> None:
    with pytest.raises(PyToolError, match="casi di test"):
        prepara_pytool("calcola_ritenuta", CODICE_RITENUTA, SCHEMA_RITENUTA, [])


def test_prepara_rifiuta_sorgente_senza_esegui() -> None:
    with pytest.raises(PyToolError, match="esegui"):
        prepara_pytool("calcola_ritenuta", "x = 1\n", SCHEMA_RITENUTA, TEST_RITENUTA)


# ------------------------------------------------- posato a mano → caricato


def test_pytool_posato_a_mano_e_caricato_e_invocabile(dati_rw: Path) -> None:
    """AC principale: un tool posato in data/tools/ è caricato e invocabile via sandbox."""
    dal = DAL(dati_rw)
    voce = _consolida_ritenuta(dal)
    assert voce["ciclo"] == "consolidata"

    # il sorgente vive come dato in data/tools/<nome>/tool.py
    assert percorso_sorgente(dati_rw, "calcola_ritenuta").is_file()
    # ed è nel ledger
    assert any(v["nome"] == "calcola_ritenuta" for v in leggi_pytools(dati_rw))

    toolset = Toolset(dal)
    voci = {v["name"]: v for v in toolset.elenco()}
    assert voci["calcola_ritenuta"]["ciclo"] == "consolidata"
    assert voci["calcola_ritenuta"]["origine"] == "pytool"

    # invocabile e il risultato passa dalla sandbox (Decimal, arrotondamento incluso)
    assert toolset.esegui("calcola_ritenuta", {"imponibile": 1000, "aliquota": 20}) == {
        "ritenuta": 200.0
    }
    # e lo schema è esposto al modello
    assert toolset.schemi(["calcola_ritenuta"])[0]["function"]["name"] == "calcola_ritenuta"


def test_pytool_invocabile_solo_se_consentito_dallo_step(dati_rw: Path) -> None:
    """Il gating ``consentiti`` dello step vale anche per i pytool."""
    dal = DAL(dati_rw)
    _consolida_ritenuta(dal)
    toolset = Toolset(dal)
    # dichiarato dallo step → ok
    assert toolset.esegui(
        "calcola_ritenuta", {"imponibile": 200, "aliquota": 20}, consentiti=["calcola_ritenuta"]
    ) == {"ritenuta": 40.0}
    # non dichiarato → rifiutato
    with pytest.raises(ToolError, match="non disponibile"):
        toolset.esegui(
            "calcola_ritenuta", {"imponibile": 200, "aliquota": 20}, consentiti=["altro"]
        )


def test_i_nativi_hanno_la_precedenza(dati_rw: Path) -> None:
    """Un consolidato omonimo di un nativo non lo sovrascrive."""
    dal = DAL(dati_rw)
    codice = "def esegui(**k):\n    return {'preso': 'pytool'}\n"
    schema = {
        "type": "function",
        "function": {"name": "salva_bozza", "description": "x", "parameters": {"type": "object"}},
    }
    dal.consolida_pytool(
        nome="salva_bozza",
        codice=codice,
        schema=schema,
        test=[{"argomenti": {}, "atteso": {"preso": "pytool"}}],
        creato_da="giovanna",
    )
    voci = {v["name"]: v for v in Toolset(dal).elenco()}
    # resta nativo (una sola voce, origine nativa)
    assert voci["salva_bozza"]["origine"] == "nativa"
    assert [v["name"] for v in Toolset(dal).elenco()].count("salva_bozza") == 1


# ------------------------------------------------- rete di sicurezza (sandbox)


def test_rete_di_sicurezza_blocca_tool_che_non_passa_i_test(dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    with pytest.raises(CatalogoNonValido, match="test 1 non passa"):
        dal.consolida_pytool(
            nome="calcola_ritenuta",
            codice=CODICE_RITENUTA,
            schema=SCHEMA_RITENUTA,
            test=[
                {"argomenti": {"imponibile": 1000, "aliquota": 20}, "atteso": {"ritenuta": 999.0}}
            ],
            creato_da="giovanna",
        )
    # nulla è stato scritto: né ledger né sorgente
    assert leggi_pytools(dati_rw) == []
    assert not percorso_sorgente(dati_rw, "calcola_ritenuta").exists()
    assert "calcola_ritenuta" not in {v["name"] for v in Toolset(dal).elenco()}


def test_rete_di_sicurezza_blocca_codice_pericoloso(dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    codice = "import os\n\ndef esegui(**k):\n    return {'x': os.getpid()}\n"
    with pytest.raises(CatalogoNonValido, match="import non consentito"):
        dal.consolida_pytool(
            nome="cattivo",
            codice=codice,
            schema={
                "type": "function",
                "function": {
                    "name": "cattivo",
                    "description": "x",
                    "parameters": {"type": "object"},
                },
            },
            test=[{"argomenti": {}, "atteso": {"x": 0}}],
            creato_da="giovanna",
        )
    assert leggi_pytools(dati_rw) == []
    assert not percorso_sorgente(dati_rw, "cattivo").exists()


def test_consolida_rifiuta_nome_pericoloso(dati_rw: Path) -> None:
    """Il nome diventa una cartella: niente path traversal."""
    dal = DAL(dati_rw)
    with pytest.raises(ValueError, match="nome di tool non valido"):
        dal.consolida_pytool(
            nome="../evasione",
            codice=CODICE_RITENUTA,
            schema=SCHEMA_RITENUTA,
            test=TEST_RITENUTA,
            creato_da="giovanna",
        )


# ------------------------------------------------- rimozione / ciclo / robustezza


def test_rimozione_libera_e_non_rompe_il_runtime(dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    _consolida_ritenuta(dal)
    assert dal.elimina_pytool(nome="calcola_ritenuta", eliminato_da="giovanna") is True

    # sparito da ledger, sorgente e registro; i nativi restano
    assert leggi_pytools(dati_rw) == []
    assert not percorso_sorgente(dati_rw, "calcola_ritenuta").exists()
    nomi = {v["name"] for v in Toolset(dal).elenco()}
    assert "calcola_ritenuta" not in nomi
    assert {"ocr_pdf", "salva_bozza", "cerca_cantiere"} <= nomi
    # seconda rimozione → False
    assert dal.elimina_pytool(nome="calcola_ritenuta", eliminato_da="giovanna") is False


def test_svuotare_i_pytool_non_spegne_nulla(dati_rw: Path) -> None:
    """Senza alcun pytool il Toolset si costruisce e i nativi ci sono tutti."""
    dal = DAL(dati_rw)
    assert carica_pytools(dati_rw) == []
    nomi = {v["name"] for v in Toolset(dal).elenco()}
    attesi = {"ocr_pdf", "cerca_fornitore", "cerca_cantiere", "salva_bozza", "cerca_voce_computo"}
    assert attesi <= nomi
    assert all(v["ciclo"] == "consolidata" for v in Toolset(dal).elenco())


def test_ciclo_deprecata_compare_ma_non_e_invocabile(dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    _consolida_ritenuta(dal)  # consolidata → invocabile
    _consolida_ritenuta(dal, ciclo="deprecata")  # transizione di ciclo

    toolset = Toolset(dal)
    voci = {v["name"]: v for v in toolset.elenco()}
    # compare nel registro col suo stato
    assert voci["calcola_ritenuta"]["ciclo"] == "deprecata"
    # ma non è più instradabile: fallback all'LLM
    with pytest.raises(ToolError, match="sconosciuto"):
        toolset.esegui("calcola_ritenuta", {"imponibile": 1000, "aliquota": 20})


def test_consolida_idempotente_sul_nome(dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    _consolida_ritenuta(dal)
    _consolida_ritenuta(dal)
    assert [v["nome"] for v in leggi_pytools(dati_rw)].count("calcola_ritenuta") == 1


def test_riga_senza_sorgente_e_ignorata_senza_crash(dati_rw: Path) -> None:
    """Un ledger che punta a un sorgente mancante non fa esplodere il caricamento."""
    dal = DAL(dati_rw)
    _consolida_ritenuta(dal)
    # rimuovo il sorgente a mano lasciando la riga di ledger: simulo uno stato monco
    percorso_sorgente(dati_rw, "calcola_ritenuta").unlink()
    assert carica_pytools(dati_rw) == []  # saltata, niente eccezione
    nomi = {v["name"] for v in Toolset(dal).elenco()}
    assert "calcola_ritenuta" not in nomi
    assert "ocr_pdf" in nomi  # il runtime regge


# --------------------------------------------------------------- API / registry


def test_registry_mostra_il_pytool_con_ciclo(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    dal = DAL(dati_rw)
    _consolida_ritenuta(dal)
    client = crea_client(FakeCompleterInterroga("SELECT 1"))
    admin = accedi(client, "giovanna")

    corpo = client.get("/api/tools", headers=admin).json()
    per_nome = {t["name"]: t for t in corpo["tools"]}
    assert per_nome["calcola_ritenuta"]["ciclo"] == "consolidata"
    assert per_nome["calcola_ritenuta"]["origine"] == "pytool"
    assert per_nome["calcola_ritenuta"]["usi"] == 0
    # i nativi restano consolidati
    assert per_nome["ocr_pdf"]["ciclo"] == "consolidata"


def test_delete_pytool_via_api(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    dal = DAL(dati_rw)
    _consolida_ritenuta(dal)
    client = crea_client(FakeCompleterInterroga("SELECT 1"))
    admin = accedi(client, "giovanna")

    r = client.delete("/api/dataset/pytool/calcola_ritenuta", headers=admin)
    assert r.status_code == 200 and r.json()["rimosso"] == "calcola_ritenuta"
    corpo = client.get("/api/tools", headers=admin).json()
    assert "calcola_ritenuta" not in {t["name"] for t in corpo["tools"]}
    # inesistente → 404
    assert client.delete("/api/dataset/pytool/calcola_ritenuta", headers=admin).status_code == 404


def test_delete_pytool_riservato_admin(crea_client: Callable[..., TestClient]) -> None:
    client = crea_client(FakeCompleterInterroga("SELECT 1"))
    operatore = accedi(client, "salvo")
    assert client.delete("/api/dataset/pytool/x", headers=operatore).status_code == 403
