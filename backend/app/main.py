import os
from pathlib import Path

from fastapi import FastAPI

from app.api import api_router
from app.core.gateway import Gateway


def create_app(data_dir: Path | str | None = None, gateway: Gateway | None = None) -> FastAPI:
    """App FastAPI. ``data_dir`` e ``gateway`` sono iniettabili per i test.

    Il DAL nasce alla prima richiesta che ne ha bisogno (vedi api/deps.py):
    l'app parte anche senza repo dati, l'health check non lo richiede.
    """
    app = FastAPI(title="Workflower", version="0.1.0")
    app.state.data_dir = Path(data_dir or os.environ.get("DATA_DIR", "./data")).resolve()
    app.state.gateway = gateway or Gateway()
    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
