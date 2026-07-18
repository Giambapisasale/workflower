from pathlib import Path

import pytest

from app.seed import init_data_repo, run_seed


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
