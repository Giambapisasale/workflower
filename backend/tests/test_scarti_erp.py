"""Scarto di un documento già arrivato in contabilità: la guardia sull'ERP.

La regola concordata: **finché il documento esiste a valle, qui non si scarta**.
Altrimenti Workflower direbbe "questa fattura non esiste" e ERPNext continuerebbe
a tenerla nei conti — due verità in disaccordo, e il disaccordo lo scoprirebbe il
commercialista.

La verifica è una **lettura** del ``docstatus``: nessuna scrittura verso l'ERP,
l'ADR sulla sincronizzazione mono-direzionale resta intatto. Verificato contro
l'istanza reale: Workflower crea i documenti come **bozza** (``docstatus`` 0), che
in Frappe non si annulla ma si elimina — perciò l'istruzione cambia con lo stato.
"""

from pathlib import Path

import pytest
from aiuti import accedi
from fake_erp import ErpServerFinto

from app.core.dal import DAL
from app.core.erp import ErpClient, ErpConfig

pytestmark = pytest.mark.erp

CONFIG = ErpConfig(
    base_url="http://erp.test",
    api_key="k",
    api_secret="s",
    company="Edile SpA",
    conto_ritenuta="Ritenute - E",
    conto_iva="IVA ns credito - E",
    item_ddt="MATERIALE-GENERICO",
)


def _bozza_da_seed(dati_rw: Path):
    dal = DAL(dati_rw)
    sorgente = next(e for e in dal.list_all("fattura") if e.dati.get("fornitore_id"))
    return dal.crea_progressivo("fattura", dict(sorgente.dati), stato="bozza")


def _valida_e_sincronizza(crea_client, dati_rw: Path):
    """Valida una bozza con l'ERP collegato: ritorna (client, admin, id, erp_id, server)."""
    bozza = _bozza_da_seed(dati_rw)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")
    esito = client.post(f"/api/review/{bozza.id}/validate", headers=admin)
    assert esito.status_code == 200, esito.text
    erp_id = DAL(dati_rw).read("fattura", bozza.id).meta.erp_id
    assert erp_id, "la sincronizzazione doveva valorizzare meta.erp_id"
    return client, admin, bozza.id, erp_id, server


def _scarta(client, admin, entity_id: str):
    return client.post(
        f"/api/review/{entity_id}/scarta", headers=admin, json={"motivo": "sbagliata"}
    )


# ------------------------------------------------------------------ bloccato


def test_bozza_a_valle_blocca_e_dice_di_eliminarla(crea_client, dati_rw: Path) -> None:
    """Il caso normale: la Purchase Invoice è Draft, quindi si *elimina*, non si annulla."""
    client, admin, entity_id, erp_id, _server = _valida_e_sincronizza(crea_client, dati_rw)

    risposta = _scarta(client, admin, entity_id)
    assert risposta.status_code == 409
    dettaglio = risposta.json()["detail"]
    assert erp_id in dettaglio
    assert "eliminala" in dettaglio.lower()
    assert "annullala" not in dettaglio.lower()  # su una bozza sarebbe un'istruzione impossibile
    # e non è stato spostato niente
    assert DAL(dati_rw).read("fattura", entity_id).stato == "validato"


def test_confermata_a_valle_blocca_e_dice_di_annullarla(crea_client, dati_rw: Path) -> None:
    client, admin, entity_id, erp_id, server = _valida_e_sincronizza(crea_client, dati_rw)
    server.conferma("Purchase Invoice", erp_id)

    risposta = _scarta(client, admin, entity_id)
    assert risposta.status_code == 409
    dettaglio = risposta.json()["detail"]
    assert "annullala" in dettaglio.lower()
    assert "cancel" in dettaglio.lower()


def test_erp_giu_blocca_senza_indovinare(crea_client, dati_rw: Path) -> None:
    """Non sapere non è come sapere che va bene: si blocca e si dice di riprovare."""
    client, admin, entity_id, _erp_id, server = _valida_e_sincronizza(crea_client, dati_rw)
    server.guasta("Purchase Invoice")

    risposta = _scarta(client, admin, entity_id)
    assert risposta.status_code == 409
    assert "riprova" in risposta.json()["detail"].lower()
    assert DAL(dati_rw).read("fattura", entity_id).stato == "validato"


# ------------------------------------------------------------------ permesso


def test_annullata_a_valle_si_scarta(crea_client, dati_rw: Path) -> None:
    client, admin, entity_id, erp_id, server = _valida_e_sincronizza(crea_client, dati_rw)
    server.annulla("Purchase Invoice", erp_id)

    risposta = _scarta(client, admin, entity_id)
    assert risposta.status_code == 200, risposta.text
    assert DAL(dati_rw).leggi_scartato("fattura", entity_id).stato == "scartato"


def test_eliminata_a_valle_si_scarta(crea_client, dati_rw: Path) -> None:
    """404 a valle: non c'è più nulla da tenere allineato."""
    client, admin, entity_id, erp_id, server = _valida_e_sincronizza(crea_client, dati_rw)
    server.elimina("Purchase Invoice", erp_id)

    risposta = _scarta(client, admin, entity_id)
    assert risposta.status_code == 200, risposta.text
    assert DAL(dati_rw).leggi_scartato("fattura", entity_id).stato == "scartato"


def test_mai_arrivata_a_valle_si_scarta(crea_client, dati_rw: Path) -> None:
    """Senza ``meta.erp_id`` non c'è niente da verificare: nessuna chiamata all'ERP."""
    bozza = _bozza_da_seed(dati_rw)
    server = ErpServerFinto()
    client = crea_client(erp=ErpClient(config=CONFIG, transport=server))
    admin = accedi(client, "giovanna")
    prima = len(server.chiamate)

    assert _scarta(client, admin, bozza.id).status_code == 200
    assert len(server.chiamate) == prima  # nessuna lettura inutile a valle


def test_integrazione_spenta_blocca_solo_i_sincronizzati(crea_client, dati_rw: Path) -> None:
    """Con l'ERP spento non si può verificare: chi è già a valle resta fermo, gli altri no."""
    # 1) una bozza mai sincronizzata si scarta anche a integrazione spenta
    mai_vista = _bozza_da_seed(dati_rw)
    client = crea_client()  # nessun erp= → client inattivo
    admin = accedi(client, "giovanna")
    assert _scarta(client, admin, mai_vista.id).status_code == 200

    # 2) una con erp_id valorizzato no: manca il modo di sapere com'è a valle
    sincronizzata = _bozza_da_seed(dati_rw)
    dal = DAL(dati_rw)
    envelope = dal.read("fattura", sincronizzata.id)
    envelope.meta.erp_id = "ACC-PINV-2026-00042"
    dal.update(envelope)

    client2 = crea_client()
    admin2 = accedi(client2, "giovanna")
    risposta = _scarta(client2, admin2, sincronizzata.id)
    assert risposta.status_code == 409
    assert "spenta" in risposta.json()["detail"].lower()
