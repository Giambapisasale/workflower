"""API di gestione manuale dei dati (M13): CRUD admin generico + guardie.

Copre: RBAC (operatore sempre 403), creazione validata con autore, controllo
esistenza dei riferimenti, rifiuto schema con messaggio amichevole, modifica con
round-trip completo dei dati, eliminazione bloccata quando referenziata, e la
regressione chiave — svuotare un tipo NON deve spegnere cruscotto/registro.
"""

from pathlib import Path

from aiuti import accedi
from fastapi.testclient import TestClient
from git import Repo

from app.core.dal import DAL

FORNITORE = {"ragione_sociale": "Nuova Ditta S.r.l.", "partita_iva": "12345678901"}


def _fattura_manuale(fornitore_id: str, voce: str | None = None) -> dict:
    return {
        "fornitore_id": fornitore_id,
        "cantiere_id": "CNT-001",
        "numero": "999/M",
        "data": "2026-07-01",
        "imponibile": 100.0,
        "iva": 22.0,
        "totale": 122.0,
        "ritenuta_acconto": None,
        "righe": [{"descrizione": "voce a mano", "importo": 100.0, "voce_computo_id": voce}],
    }


def head(dati_rw: Path) -> str:
    return str(Repo(dati_rw).head.commit.message)


# --------------------------------------------------------------------- RBAC


def test_operatore_mai_su_entities(client: TestClient) -> None:
    op = accedi(client, "salvo")
    for metodo, percorso in (
        ("get", "/api/entities/meta"),
        ("get", "/api/entities/fornitore"),
        ("get", "/api/entities/fornitore/FRN-001"),
        ("post", "/api/entities/fornitore"),
        ("put", "/api/entities/fornitore/FRN-001"),
        ("delete", "/api/entities/fornitore/FRN-001"),
    ):
        extra = {"json": {"dati": {}}} if metodo in ("post", "put") else {}
        r = getattr(client, metodo)(percorso, headers=op, **extra)
        assert r.status_code == 403, f"{metodo} {percorso} → {r.status_code}"


# ---------------------------------------------------------------------- meta


def test_meta_tipi_gestibili(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    tipi = {t["tipo"]: t for t in client.get("/api/entities/meta", headers=admin).json()["tipi"]}
    assert "documento" not in tipi  # il wrapper di sistema non si gestisce a mano
    assert tipi["fornitore"]["is_master"] is True
    assert tipi["fattura"]["is_master"] is False
    assert tipi["fattura"]["riferimenti"] == {
        "fornitore_id": "fornitore",
        "cantiere_id": "cantiere",
    }
    assert tipi["cantiere"]["schema"]["title"] == "Cantiere"  # schema per il form


# ------------------------------------------------------------------ create


def test_crea_fornitore_validato_con_autore(client: TestClient, dati_rw: Path) -> None:
    admin = accedi(client, "giovanna")
    r = client.post("/api/entities/fornitore", headers=admin, json={"dati": FORNITORE})
    assert r.status_code == 200
    fid = r.json()["id"]
    assert r.json()["stato"] == "validato"
    env = DAL(dati_rw).read("fornitore", fid)
    assert env.stato == "validato" and env.meta.validato_da == "giovanna"
    assert env.meta.run_id is None  # niente run finto: è manuale
    assert head(dati_rw) == f"fornitore {fid}: crea [manual:giovanna]"


def test_crea_fattura_a_mano_entra_nel_cruscotto(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    prima = client.get("/api/dashboard/costs", headers=admin).json()["totali"]["n_fatture"]
    r = client.post(
        "/api/entities/fattura", headers=admin, json={"dati": _fattura_manuale("FRN-001")}
    )
    assert r.status_code == 200
    dopo = client.get("/api/dashboard/costs", headers=admin).json()["totali"]["n_fatture"]
    assert dopo == prima + 1  # le viste rileggono i file: subito nel cruscotto


def test_crea_riferimento_inesistente_422(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    r = client.post(
        "/api/entities/fattura", headers=admin, json={"dati": _fattura_manuale("FRN-999")}
    )
    assert r.status_code == 422
    assert "FRN-999" in r.json()["detail"]


def test_crea_schema_invalido_422_amichevole(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    cattivo = {"ragione_sociale": "X", "partita_iva": "non-valida"}
    r = client.post("/api/entities/fornitore", headers=admin, json={"dati": cattivo})
    assert r.status_code == 422
    assert "partita_iva" in r.json()["detail"]


def test_tipo_non_gestibile_404(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    assert client.get("/api/entities/documento", headers=admin).status_code == 404


# ------------------------------------------------------------------ update


def test_aggiorna_conserva_stato_e_campi_non_mostrati(client: TestClient, dati_rw: Path) -> None:
    admin = accedi(client, "giovanna")
    # FT-2026-0001 (seed, validata) ha una riga con voce_computo_id VC1-02
    prima = DAL(dati_rw).read("fattura", "FT-2026-0001")
    assert prima.dati["righe"][0]["voce_computo_id"] == "VC1-02"
    # modifico il numero rimandando indietro l'intero dati (round-trip completo)
    nuovo = {**prima.dati, "numero": "126-BIS"}
    r = client.put("/api/entities/fattura/FT-2026-0001", headers=admin, json={"dati": nuovo})
    assert r.status_code == 200
    dopo = DAL(dati_rw).read("fattura", "FT-2026-0001")
    assert dopo.dati["numero"] == "126-BIS"
    assert dopo.dati["righe"][0]["voce_computo_id"] == "VC1-02"  # collegamento preservato
    assert dopo.stato == "validato"  # stato conservato
    assert head(dati_rw) == "fattura FT-2026-0001: aggiorna [manual:giovanna]"


def test_aggiorna_inesistente_404(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    r = client.put("/api/entities/fornitore/FRN-999", headers=admin, json={"dati": FORNITORE})
    assert r.status_code == 404


# ------------------------------------------------------------------ delete


def test_elimina_bloccata_poi_consentita(client: TestClient, dati_rw: Path) -> None:
    admin = accedi(client, "giovanna")
    # FRN-001 è usato da fatture/ddt del seed → bloccato
    r = client.delete("/api/entities/fornitore/FRN-001", headers=admin)
    assert r.status_code == 409
    assert "usato" in r.json()["detail"]
    # creo un fornitore libero e lo elimino
    fid = client.post(
        "/api/entities/fornitore", headers=admin, json={"dati": FORNITORE}
    ).json()["id"]
    r = client.delete(f"/api/entities/fornitore/{fid}", headers=admin)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert head(dati_rw) == f"fornitore {fid}: elimina [manual:giovanna]"
    assert client.get(f"/api/entities/fornitore/{fid}", headers=admin).status_code == 404


def test_elimina_computo_referenziato_da_voce(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    # CMP-001 ha voci (VC1-*) usate da righe di FT-2026-0001/0004 → bloccato
    r = client.delete("/api/entities/computo/CMP-001", headers=admin)
    assert r.status_code == 409


def test_elimina_cantiere_referenziato(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    r = client.delete("/api/entities/cantiere/CNT-001", headers=admin)
    assert r.status_code == 409


def test_elimina_transazionale_scollega_il_documento(
    client: TestClient, dati_rw: Path, fixtures_dir: Path
) -> None:
    # un upload produce una fattura + il wrapper `documento` che la punta
    salvo = accedi(client, "salvo")
    pdf = (fixtures_dir / "fattura-calcestruzzi-etna.pdf").read_bytes()
    corpo = client.post(
        "/api/documents", headers=salvo, files={"file": ("f.pdf", pdf, "application/pdf")}
    ).json()
    doc_id = corpo["doc_id"]
    entity_id = DAL(dati_rw).read("documento", doc_id).dati["entity_id"]
    assert entity_id  # l'estrazione ha collegato una fattura

    admin = accedi(client, "giovanna")
    assert client.delete(f"/api/entities/fattura/{entity_id}", headers=admin).status_code == 200
    # eliminata l'entità, il wrapper non punta più al nulla
    doc = DAL(dati_rw).read("documento", doc_id)
    assert doc.dati["entity_id"] is None
    assert doc.dati["entity_tipo"] is None


# ------------------------------------------- regressione: tipo svuotato → cruscotto vivo


def test_svuotare_un_tipo_non_spegne_il_cruscotto(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    sal = client.get("/api/entities/sal", headers=admin).json()["voci"]
    assert sal  # il seed ne ha
    for voce in sal:
        assert client.delete(f"/api/entities/sal/{voce['id']}", headers=admin).status_code == 200
    # tipo sal ora vuoto: viste, cruscotto e registro devono reggere
    assert client.get("/api/entities/sal", headers=admin).json()["voci"] == []
    assert client.get("/api/dashboard/costs", headers=admin).status_code == 200
    assert client.get("/api/cantieri/CNT-001/registro", headers=admin).status_code == 200
