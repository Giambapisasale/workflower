import os
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import api_router
from app.core.gateway import Gateway
from app.core.logbook import configura_logging, ottieni_logger


def create_app(data_dir: Path | str | None = None, gateway: Gateway | None = None) -> FastAPI:
    """App FastAPI. ``data_dir`` e ``gateway`` sono iniettabili per i test.

    Il DAL nasce alla prima richiesta che ne ha bisogno (vedi api/deps.py):
    l'app parte anche senza repo dati, l'health check non lo richiede.
    """
    app = FastAPI(title="Workflower", version="0.1.0")
    app.state.data_dir = Path(data_dir or os.environ.get("DATA_DIR", "./data")).resolve()
    app.state.gateway = gateway or Gateway()
    livello = configura_logging(app.state.data_dir)
    ottieni_logger("avvio").info(
        "app avviata (data_dir=%s, log=%s)", app.state.data_dir, livello
    )
    _installa_osservabilita(app)
    app.include_router(api_router, prefix="/api")
    return app


def _installa_osservabilita(app: FastAPI) -> None:
    """Copre la fase *api*: ogni richiesta a log, ogni eccezione non gestita con traceback."""
    log = ottieni_logger("api")

    @app.middleware("http")
    async def traccia_richieste(request: Request, call_next):  # type: ignore[no-untyped-def]
        partenza = time.monotonic()
        try:
            risposta = await call_next(request)
        except Exception:
            # L'eccezione è già stata registrata dall'exception handler sotto:
            # qui la ri-solleviamo perché Starlette produca la risposta 500.
            raise
        durata_ms = int((time.monotonic() - partenza) * 1000)
        livello = log.warning if risposta.status_code >= 500 else log.debug
        livello(
            "%s %s → %s (%dms)",
            request.method,
            request.url.path,
            risposta.status_code,
            durata_ms,
            extra={"documento": request.url.path},
        )
        return risposta

    @app.exception_handler(Exception)
    async def eccezione_non_gestita(request: Request, exc: Exception):  # type: ignore[no-untyped-def]
        log.error(
            "eccezione non gestita su %s %s: %s",
            request.method,
            request.url.path,
            exc,
            exc_info=exc,
            extra={"documento": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "errore interno: ci pensa l'ufficio"},
        )


app = create_app()
