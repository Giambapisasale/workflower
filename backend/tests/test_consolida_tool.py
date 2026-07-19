"""Consolidamento di un candidato in tool parametrico ``t_*`` (§3.6, branca "query parametrica").

Il tool è una **macro tabellare** DuckDB (dato, non codice Python): generalizza sui
valori che variavano — dove una vista cablerebbe il letterale dell'esempio.
"""

from collections.abc import Callable
from pathlib import Path

import duckdb
import pytest
from aiuti import accedi
from fake_ask import FakeCompleterInterroga
from fastapi.testclient import TestClient

from app.core.consolida import ConsolidaError, letterali, prepara, prepara_tool
from app.core.dal import DAL, CatalogoNonValido
from app.core.views import query

# Un esempio parametrico "spesa del comune X" (con un letterale nella clausola WHERE).
SPESA_PER_COMUNE = (
    "SELECT c.nome AS cantiere, COALESCE(SUM(f.totale), 0) AS speso "
    "FROM v_cantieri c LEFT JOIN v_fatture f ON f.cantiere_id = c.id "
    "WHERE c.comune = 'Catania' GROUP BY c.nome ORDER BY speso DESC LIMIT 100"
)


def _sql_spesa_comune(comune: str) -> str:
    return (
        "SELECT c.nome AS cantiere, COALESCE(SUM(f.totale), 0) AS speso "
        "FROM v_cantieri c LEFT JOIN v_fatture f ON f.cantiere_id = c.id "
        f"WHERE c.comune = '{comune}' GROUP BY c.nome ORDER BY speso DESC LIMIT 100"
    )


def _due_comuni(dati_rw: Path) -> tuple[str, str]:
    comuni = [
        r["comune"]
        for r in query(
            dati_rw, "SELECT DISTINCT comune FROM v_cantieri WHERE comune IS NOT NULL ORDER BY 1"
        )
    ]
    assert len(comuni) >= 2, "il seed deve avere almeno due comuni distinti"
    return comuni[0], comuni[1]


def _registra(client: TestClient, headers: dict[str, str], domanda: str) -> dict:
    """Registra una query via /ask admin e ritorna il suo gruppo-fingerprint."""
    risposta = client.post(
        "/api/ask", json={"question": domanda, "mode": "admin"}, headers=headers
    )
    assert risposta.status_code == 200, risposta.text
    return client.get("/api/dataset/queries", headers=headers).json()["gruppi"][0]


def _norm(righe: list[dict]) -> list[tuple]:
    return sorted((r["cantiere"], r["speso"]) for r in righe)


# --------------------------------------------------------------- unit


def test_letterali_estrae_stringhe_e_numeri() -> None:
    lett = letterali("SELECT * FROM v_x WHERE nome = 'Le Palme' AND n > 10")
    assert "'Le Palme'" in lett and "10" in lett
    # un numero dentro una stringa non è un letterale a sé
    assert letterali("SELECT * FROM v_x WHERE id = 'CNT-001'") == ["'CNT-001'"]


def test_prepara_tool_rifiuta_senza_parametri(dati_rw: Path) -> None:
    with pytest.raises(ConsolidaError, match="almeno un parametro"):
        prepara_tool(dati_rw, "spesa_comune", SPESA_PER_COMUNE, [])


def test_prepara_tool_rifiuta_parametro_che_ombreggia(dati_rw: Path) -> None:
    # "cantiere" è già un alias di output: come parametro ombreggerebbe la colonna
    with pytest.raises(ConsolidaError, match="compare già"):
        prepara_tool(
            dati_rw,
            "spesa_comune",
            SPESA_PER_COMUNE,
            [{"valore": "'Catania'", "nome": "cantiere"}],
        )


def test_prepara_tool_rifiuta_valore_assente(dati_rw: Path) -> None:
    with pytest.raises(ConsolidaError, match="non compare"):
        prepara_tool(
            dati_rw,
            "spesa_comune",
            SPESA_PER_COMUNE,
            [{"valore": "'Palermo'", "nome": "comune"}],
        )


def test_prepara_tool_rifiuta_query_non_sicura(dati_rw: Path) -> None:
    # stessi guardrail di /ask: solo viste v_* / tool t_*
    with pytest.raises(ConsolidaError):
        prepara_tool(
            dati_rw,
            "cattivo",
            "SELECT * FROM sqlite_master WHERE tbl_name = 'x'",
            [{"valore": "'x'", "nome": "cerca"}],
        )


# --------------------------------------------------------------- e2e


def test_consolida_tool_crea_macro_interrogabile(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    c1, c2 = _due_comuni(dati_rw)
    client = crea_client(FakeCompleterInterroga(_sql_spesa_comune(c1)))
    admin = accedi(client, "giovanna")
    gruppo = _registra(client, admin, f"quanto si è speso a {c1}?")
    assert f"'{c1}'" in gruppo["letterali"]  # il letterale è offerto come parametro

    risposta = client.post(
        "/api/dataset/consolida-tool",
        headers=admin,
        json={
            "fingerprint": gruppo["fingerprint"],
            "nome": "spesa_comune",
            "parametri": [{"valore": f"'{c1}'", "nome": "comune"}],
        },
    )
    assert risposta.status_code == 200, risposta.text
    corpo = risposta.json()
    assert corpo["macro"] == "t_spesa_comune" and corpo["parametri"] == ["comune"]

    # è interrogabile come una tabella e il parametro cambia davvero i risultati
    m1 = query(dati_rw, "SELECT * FROM t_spesa_comune(?)", [c1])
    m2 = query(dati_rw, "SELECT * FROM t_spesa_comune(?)", [c2])
    atteso = query(
        dati_rw,
        "SELECT c.nome AS cantiere, COALESCE(SUM(f.totale), 0) AS speso "
        "FROM v_cantieri c LEFT JOIN v_fatture f ON f.cantiere_id = c.id "
        "WHERE c.comune = ? GROUP BY c.nome",
        [c1],
    )
    assert m1 and _norm(m1) == _norm(atteso)
    assert _norm(m1) != _norm(m2)

    # il candidato risulta consolidato e il tool compare nel registro
    reg = client.get("/api/tools", headers=admin).json()
    candidato = next(c for c in reg["candidati"] if c["fingerprint"] == gruppo["fingerprint"])
    assert candidato["consolidato"] == "t_spesa_comune"
    assert any(m["macro"] == "t_spesa_comune" for m in reg["macro"])


def test_tool_esposto_nel_catalogo_del_modello(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    """Dopo il consolidamento, il tool compare nel prompt di generazione SQL."""
    c1, _ = _due_comuni(dati_rw)

    class CompleterCattura(FakeCompleterInterroga):
        def __init__(self, sql: str) -> None:
            super().__init__(sql)
            self.sistema_sql: str | None = None

        def __call__(self, *, model, messages, **k):  # type: ignore[no-untyped-def]
            sistema = str(messages[0]["content"])
            if "Generazione SQL" in sistema:
                self.sistema_sql = sistema
            return super().__call__(model=model, messages=messages, **k)

    completer = CompleterCattura(_sql_spesa_comune(c1))
    client = crea_client(completer)
    admin = accedi(client, "giovanna")
    gruppo = _registra(client, admin, f"spesa a {c1}")
    client.post(
        "/api/dataset/consolida-tool",
        headers=admin,
        json={
            "fingerprint": gruppo["fingerprint"],
            "nome": "spesa_comune",
            "parametri": [{"valore": f"'{c1}'", "nome": "comune"}],
        },
    )
    # una nuova domanda vede il catalogo aggiornato con la macro
    client.post("/api/ask", json={"question": "ancora", "mode": "admin"}, headers=admin)
    assert completer.sistema_sql is not None
    assert "t_spesa_comune(comune)" in completer.sistema_sql


def test_consolida_tool_idempotente_sullo_stesso_nome(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    c1, _ = _due_comuni(dati_rw)
    client = crea_client(FakeCompleterInterroga(_sql_spesa_comune(c1)))
    admin = accedi(client, "giovanna")
    gruppo = _registra(client, admin, f"spesa a {c1}")

    for _ in range(2):
        r = client.post(
            "/api/dataset/consolida-tool",
            headers=admin,
            json={
                "fingerprint": gruppo["fingerprint"],
                "nome": "spesa_comune",
                "parametri": [{"valore": f"'{c1}'", "nome": "comune"}],
            },
        )
        assert r.status_code == 200, r.text

    reg = client.get("/api/tools", headers=admin).json()
    assert [m["macro"] for m in reg["macro"]].count("t_spesa_comune") == 1
    assert query(dati_rw, "SELECT * FROM t_spesa_comune(?)", [c1]) is not None


def test_consolida_tool_riservato_agli_admin(crea_client: Callable[..., TestClient]) -> None:
    client = crea_client(FakeCompleterInterroga(SPESA_PER_COMUNE))
    operatore = accedi(client, "salvo")
    risposta = client.post(
        "/api/dataset/consolida-tool",
        headers=operatore,
        json={
            "fingerprint": "qualsiasi",
            "nome": "prova",
            "parametri": [{"valore": "'x'", "nome": "p"}],
        },
    )
    assert risposta.status_code == 403


# --------------------------------------------------- rimozione / modifica


def _crea_tool(client: TestClient, admin: dict[str, str], fp: str, nome: str, comune: str):
    return client.post(
        "/api/dataset/consolida-tool",
        headers=admin,
        json={
            "fingerprint": fp,
            "nome": nome,
            "parametri": [{"valore": f"'{comune}'", "nome": "comune"}],
        },
    )


def test_rimuovi_tool_smarca_candidato_e_ricreabile(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    c1, _ = _due_comuni(dati_rw)
    client = crea_client(FakeCompleterInterroga(_sql_spesa_comune(c1)))
    admin = accedi(client, "giovanna")
    fp = _registra(client, admin, f"spesa a {c1}")["fingerprint"]
    assert _crea_tool(client, admin, fp, "spesa_comune", c1).status_code == 200

    reg = client.get("/api/tools", headers=admin).json()
    candidato = next(x for x in reg["candidati"] if x["fingerprint"] == fp)
    assert candidato["consolidato"] == "t_spesa_comune"

    # rimozione
    r = client.delete("/api/dataset/tool/t_spesa_comune", headers=admin)
    assert r.status_code == 200 and r.json()["rimosso"] == "t_spesa_comune"

    reg = client.get("/api/tools", headers=admin).json()
    assert next(x for x in reg["candidati"] if x["fingerprint"] == fp)["consolidato"] is None
    assert reg["macro"] == []
    # non più interrogabile
    with pytest.raises(duckdb.Error):
        query(dati_rw, "SELECT * FROM t_spesa_comune(?)", [c1])

    # "modifica" = ricrea (qui con un nome diverso): il candidato è di nuovo libero
    r2 = _crea_tool(client, admin, fp, "spesa_zona", c1)
    assert r2.status_code == 200 and r2.json()["macro"] == "t_spesa_zona"


def test_rimuovi_tool_inesistente(crea_client: Callable[..., TestClient]) -> None:
    client = crea_client(FakeCompleterInterroga(SPESA_PER_COMUNE))
    admin = accedi(client, "giovanna")
    assert client.delete("/api/dataset/tool/t_non_esiste", headers=admin).status_code == 404


def test_rimuovi_tool_riservato_agli_admin(crea_client: Callable[..., TestClient]) -> None:
    client = crea_client(FakeCompleterInterroga(SPESA_PER_COMUNE))
    operatore = accedi(client, "salvo")
    assert client.delete("/api/dataset/tool/t_x", headers=operatore).status_code == 403


def test_rimuovi_vista_via_api(crea_client: Callable[..., TestClient], dati_rw: Path) -> None:
    client = crea_client(FakeCompleterInterroga("SELECT id, nome FROM v_cantieri LIMIT 100"))
    admin = accedi(client, "giovanna")
    fp = _registra(client, admin, "elenco cantieri")["fingerprint"]
    assert client.post(
        "/api/dataset/consolida", headers=admin, json={"fingerprint": fp, "nome": "elenco_cantieri"}
    ).status_code == 200
    assert any(
        v["vista"] == "v_elenco_cantieri"
        for v in client.get("/api/tools", headers=admin).json()["viste"]
    )
    r = client.delete("/api/dataset/vista/v_elenco_cantieri", headers=admin)
    assert r.status_code == 200
    assert client.get("/api/tools", headers=admin).json()["viste"] == []


def test_rimuovi_vista_bloccata_se_un_tool_dipende(dati_rw: Path) -> None:
    """La verifica del catalogo impedisce di rompere una dipendenza (rollback)."""
    dal = DAL(dati_rw)
    vista = prepara(dati_rw, "base_cantieri", "SELECT id, nome FROM v_cantieri LIMIT 100")
    dal.consolida_vista(
        nome="base_cantieri",
        vista=vista["vista"],
        corpo=vista["corpo"],
        fingerprint="fp-vista",
        esempio="SELECT id, nome FROM v_cantieri LIMIT 100",
        creato_da="giovanna",
    )
    tool = prepara_tool(
        dati_rw,
        "cant_per_nome",
        "SELECT id, nome FROM v_base_cantieri WHERE nome = 'Le Palme' LIMIT 100",
        [{"valore": "'Le Palme'", "nome": "cerca"}],
    )
    dal.consolida_tool(
        nome="cant_per_nome",
        macro=tool["macro"],
        corpo=tool["corpo"],
        parametri=tool["parametri"],
        fingerprint="fp-tool",
        esempio="SELECT id, nome FROM v_base_cantieri WHERE nome = 'Le Palme' LIMIT 100",
        creato_da="giovanna",
    )
    # rimuovere la vista base romperebbe il tool che la referenzia → bloccata
    with pytest.raises(CatalogoNonValido):
        dal.elimina_vista(vista="v_base_cantieri", eliminato_da="giovanna")
    # nulla è stato tolto: catalogo ancora valido
    assert query(dati_rw, "SELECT count(*) AS n FROM v_base_cantieri")[0]["n"] >= 0
    assert query(dati_rw, "SELECT count(*) AS n FROM t_cant_per_nome('Le Palme')")[0]["n"] >= 0
