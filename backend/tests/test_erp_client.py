"""Client ERP (Integrazione ERP, M23). Copre gli AC della milestone:

config da env (mai hard-coded), interruttore ``erp_attivo`` come ``t3_attivo``,
client con trasporto iniettabile (nessun ERP reale), gestione degli errori come
``ErpError``. La costruzione non fa mai I/O.
"""

import pytest
from fake_erp import FakeTrasporto, RispostaFinta

from app.core.erp import ErpClient, ErpConfig, ErpError, erp_attivo


@pytest.fixture
def env_erp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ERP_BASE_URL", "https://erp.example.com")
    monkeypatch.setenv("ERP_API_KEY", "chiave")
    monkeypatch.setenv("ERP_API_SECRET", "segreto")


# ---------------------------------------------------------------- config / switch


def test_config_da_env_assente_e_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ERP_BASE_URL", raising=False)
    monkeypatch.delenv("ERP_API_KEY", raising=False)
    monkeypatch.delenv("ERP_API_SECRET", raising=False)
    assert ErpConfig.da_env() is None
    assert erp_attivo() is False


def test_config_da_env_parziale_e_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ERP_BASE_URL", "https://erp.example.com")
    monkeypatch.delenv("ERP_API_KEY", raising=False)
    monkeypatch.delenv("ERP_API_SECRET", raising=False)
    assert ErpConfig.da_env() is None  # una env manca → non attivo
    assert erp_attivo() is False


def test_config_da_env_completa(env_erp: None) -> None:
    config = ErpConfig.da_env()
    assert config is not None
    assert config.base_url == "https://erp.example.com"
    assert erp_attivo() is True


def test_costruzione_senza_config_non_fa_io(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ERP_BASE_URL", raising=False)
    monkeypatch.delenv("ERP_API_KEY", raising=False)
    monkeypatch.delenv("ERP_API_SECRET", raising=False)
    client = ErpClient()  # nessuna eccezione, nessuna rete
    assert client.attivo() is False


# ---------------------------------------------------------------- richieste


def test_richiesta_non_configurato_solleva() -> None:
    client = ErpClient(config=None, transport=FakeTrasporto())
    with pytest.raises(ErpError, match="non configurato"):
        client.richiesta("GET", "/api/resource/Supplier")


def test_richiesta_ok_ritorna_json(env_erp: None) -> None:
    trasporto = FakeTrasporto([RispostaFinta(200, {"data": {"name": "FORN-1"}})])
    client = ErpClient(transport=trasporto)
    corpo = client.richiesta("POST", "/api/resource/Supplier", json={"supplier_name": "ACME"})
    assert corpo == {"data": {"name": "FORN-1"}}


def test_richiesta_header_auth_e_url(env_erp: None) -> None:
    trasporto = FakeTrasporto([RispostaFinta(200, {"data": {}})])
    client = ErpClient(transport=trasporto)
    client.richiesta("GET", "api/resource/Supplier")  # senza slash iniziale
    chiamata = trasporto.chiamate[0]
    assert chiamata["url"] == "https://erp.example.com/api/resource/Supplier"
    assert chiamata["headers"]["Authorization"] == "token chiave:segreto"


def test_richiesta_http_400_solleva(env_erp: None) -> None:
    trasporto = FakeTrasporto([RispostaFinta(417, {"exc": "ValidationError"})])
    client = ErpClient(transport=trasporto)
    with pytest.raises(ErpError, match="417"):
        client.richiesta("POST", "/api/resource/Purchase Invoice", json={})


def test_richiesta_trasporto_giu_solleva(env_erp: None) -> None:
    trasporto = FakeTrasporto(errore=ConnectionError("connessione rifiutata"))
    client = ErpClient(transport=trasporto)
    with pytest.raises(ErpError, match="non raggiungibile"):
        client.richiesta("GET", "/api/resource/Supplier")
