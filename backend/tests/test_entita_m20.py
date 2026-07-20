"""M20 — entità di dominio come puro dato (materiale, mezzo, lavorazione, scadenza).

Riprova l'invariante §1 su scala: aggiungere un'entità = schema + riga in
ENTITY_TYPES + vista, zero codice nel runtime. Ogni entità è creabile dalla CRUD
generica (M13), compare nelle viste e nel catalogo dei tipi gestibili.
"""


from aiuti import accedi
from fastapi.testclient import TestClient

from app.core.dal import ENTITY_TYPES, tipo_da_id
from app.core.views import query

NUOVE = ["materiale", "mezzo", "lavorazione", "scadenza"]


def test_registrate_nel_registry_dato() -> None:
    """Le nuove entità vivono in ENTITY_TYPES (registry-dato) con id riconoscibili."""
    for tipo in NUOVE:
        assert tipo in ENTITY_TYPES
    assert tipo_da_id("MAT-001") == "materiale"
    assert tipo_da_id("MEZ-001") == "mezzo"
    assert tipo_da_id("LAV-001") == "lavorazione"
    assert tipo_da_id("SCAD-001") == "scadenza"


def test_compaiono_nelle_viste(client: TestClient, dati_rw) -> None:
    # popolate dal seed e interrogabili come ogni altra vista
    assert len(query(dati_rw, "SELECT * FROM v_materiali")) >= 3
    assert len(query(dati_rw, "SELECT * FROM v_mezzi")) >= 2
    assert len(query(dati_rw, "SELECT * FROM v_lavorazioni")) >= 3
    assert len(query(dati_rw, "SELECT * FROM v_scadenze WHERE stato_adempimento = 'aperta'")) >= 2


def test_catalogo_tipi_gestibili(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    tipi = {t["tipo"]: t for t in client.get("/api/entities/meta", headers=admin).json()["tipi"]}
    for tipo in NUOVE:
        assert tipo in tipi
        assert tipi[tipo]["is_master"] is True  # anagrafiche, non documenti d'ingresso
    # il riferimento a cantiere della scadenza è riconosciuto dallo schema
    assert tipi["scadenza"]["riferimenti"].get("cantiere_id") == "cantiere"


def test_crud_crea_materiale(client: TestClient, dati_rw) -> None:
    admin = accedi(client, "giovanna")
    r = client.post(
        "/api/entities/materiale",
        headers=admin,
        json={"dati": {"descrizione": "Guaina bituminosa", "unita_misura": "mq",
                       "prezzo_unitario": 8.5}},
    )
    assert r.status_code == 200, r.text
    nuovo = r.json()["id"]
    assert tipo_da_id(nuovo) == "materiale"
    # compare subito nella vista (i dati sono la fonte, la vista li rilegge)
    ids = {row["id"] for row in query(dati_rw, "SELECT id FROM v_materiali")}
    assert nuovo in ids


def test_crud_scadenza_verifica_riferimento(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    # cantiere inesistente → 422 (lo schema valida il formato, il DAL l'esistenza)
    r = client.post(
        "/api/entities/scadenza",
        headers=admin,
        json={"dati": {"descrizione": "x", "data_scadenza": "2026-12-31",
                       "cantiere_id": "CNT-999"}},
    )
    assert r.status_code == 422
    # cantiere valido → creata
    ok = client.post(
        "/api/entities/scadenza",
        headers=admin,
        json={"dati": {"descrizione": "Collaudo statico", "data_scadenza": "2026-11-30",
                       "cantiere_id": "CNT-001", "stato": "aperta"}},
    )
    assert ok.status_code == 200, ok.text


def test_schema_rifiuta_dati_non_conformi(client: TestClient) -> None:
    admin = accedi(client, "giovanna")
    # manca unita_misura (required) → 422
    r = client.post(
        "/api/entities/lavorazione",
        headers=admin,
        json={"dati": {"descrizione": "Posa pavimenti"}},
    )
    assert r.status_code == 422
