import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from fake_llm import FakeCompleter
from fastapi.testclient import TestClient

from app import fixtures_docs
from app.core.gateway import Gateway
from app.fixtures import genera
from app.main import create_app
from app.seed import init_data_repo, run_seed

ERP_ENV = (
    "ERP_BASE_URL",
    "ERP_API_KEY",
    "ERP_API_SECRET",
    "ERP_COMPANY",
    "ERP_CONTO_RITENUTA",
    "ERP_CONTO_IVA",
    "ERP_CONTO_COSTO",
    "ERP_PARENT_COST_CENTER",
    "ERP_ITEM_DDT",
    "ERP_SUPPLIER_GROUP",
)


@pytest.fixture(autouse=True)
def erp_non_configurato(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nessun test parte con l'ERP dello sviluppatore già collegato.

    **litellm chiama ``load_dotenv()`` all'import**: importare il gateway porta
    dentro al processo il ``.env`` del progetto, ``ERP_*`` comprese. Senza questa
    pulizia un test che crede l'integrazione spenta la troverebbe accesa e
    puntata sull'istanza reale — nel migliore dei casi fallirebbe a caso, nel
    peggiore scriverebbe documenti veri.

    Chi *vuole* un ERP lo inietta (``crea_client(erp=...)``) o imposta le env da
    sé con ``monkeypatch``, dentro al corpo del test: succede dopo questa fixture.

    L'import di ``Gateway`` qui sopra ha già fatto scattare il ``load_dotenv``: a
    questo punto le variabili ci sono, e vanno tolte.
    """
    for nome in ERP_ENV:
        monkeypatch.delenv(nome, raising=False)


@pytest.fixture(scope="session")
def seeded_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Repo dati completo di seed, condiviso dai test in sola lettura (viste)."""
    data_dir = tmp_path_factory.mktemp("workflower") / "data"
    run_seed(data_dir)
    return data_dir


@pytest.fixture
def data_repo(tmp_path: Path) -> Path:
    """Repo dati vuoto (struttura + schemi + git) per i test che scrivono."""
    data_dir = tmp_path / "data"
    init_data_repo(data_dir)
    return data_dir


@pytest.fixture
def dati_rw(seeded_dir: Path, tmp_path: Path) -> Path:
    """Copia usa-e-getta del repo dati completo, per i test che scrivono."""
    destinazione = tmp_path / "data"
    shutil.copytree(seeded_dir, destinazione)
    return destinazione


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """I 3 PDF fattura sintetici di `make fixtures`, generati una volta sola."""
    cartella = tmp_path_factory.mktemp("fixtures")
    genera(cartella)
    return cartella


@pytest.fixture(scope="session")
def fixtures_docs_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """I documenti sintetici di Fase 2 (DDT, SAL, …), generati una volta sola."""
    cartella = tmp_path_factory.mktemp("fixtures_docs")
    fixtures_docs.genera(cartella)
    return cartella


@pytest.fixture
def ambiente_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier LLM configurati con modelli finti (il trasporto nei test è il fake)."""
    monkeypatch.setenv("LLM_T1_MODEL", "test/finto-t1")
    monkeypatch.setenv("LLM_T2_MODEL", "test/finto-t2")


@pytest.fixture
def crea_client(dati_rw: Path, ambiente_llm: None) -> Callable[..., TestClient]:
    """Factory di TestClient sull'app, con i trasporti (LLM ed ERP) che servono al test."""

    def _crea(completer: object | None = None, erp: object | None = None) -> TestClient:
        gateway = Gateway(completer=completer or FakeCompleter(dati_rw), attesa_retry=0)
        return TestClient(create_app(data_dir=dati_rw, gateway=gateway, erp=erp))

    return _crea


@pytest.fixture
def client(crea_client: Callable[..., TestClient]) -> TestClient:
    """App con il fake che sa leggere le fatture delle fixtures."""
    return crea_client()
