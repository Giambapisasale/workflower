import os
import queue
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.core.gateway import Gateway
from app.core.logbook import configura_logging, ottieni_logger, registra_osservatore

# Attesa di raccolta prima di analizzare una raffica di errori (secondi).
_DEBOUNCE_DIAGNOSTICA = 3.0


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
    if os.environ.get("DIAGNOSTICA_AUTO", "").strip().lower() in ("1", "true", "on", "si"):
        _avvia_trigger_diagnostica(app)
    app.include_router(api_router, prefix="/api")
    _monta_frontend(app)
    return app


def _monta_frontend(app: FastAPI) -> None:
    """Serve il frontend buildato (``FRONTEND_DIST``) come SPA, dietro le API.

    In sviluppo/test la variabile è assente: FastAPI resta solo-API (il dev usa
    il proxy di Vite). In produzione l'immagine imposta ``FRONTEND_DIST`` sulla
    cartella ``dist``, così un singolo container serve API **e** interfaccia.
    """
    dist = os.environ.get("FRONTEND_DIST")
    if not dist:
        return
    radice = Path(dist)
    index = radice / "index.html"
    if not index.is_file():
        return
    if (radice / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=radice / "assets"), name="assets")

    @app.get("/{percorso:path}", include_in_schema=False)
    async def spa(percorso: str):  # type: ignore[no-untyped-def]
        if percorso.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        file = radice / percorso
        if percorso and file.is_file() and file.resolve().is_relative_to(radice.resolve()):
            return FileResponse(file)
        return FileResponse(index)  # fallback SPA per le rotte client (/admin, /op…)


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


def _avvia_trigger_diagnostica(app: FastAPI) -> None:
    """Il trigger: ogni errore risveglia (in background) l'analisi dei log.

    Opt-in (env ``DIAGNOSTICA_AUTO``) perché ogni analisi è una chiamata LLM.
    Un osservatore segnala gli errori; un worker daemon li assorbe con un piccolo
    debounce e apre/aggiorna una diagnosi per firma. Riusa il DAL condiviso
    dell'app (stesso lock di scrittura). Non tocca mai il flusso delle richieste.
    """
    from app.api.deps import dal_da_app
    from app.core.dal import DalError
    from app.core.diagnostico import Diagnostico

    log = ottieni_logger("diagnostico")
    segnali: queue.Queue[int] = queue.Queue()

    def osserva(voce: dict) -> None:  # type: ignore[type-arg]
        if voce.get("fase") != "diagnostico":  # niente cicli sull'analisi stessa
            segnali.put(1)

    def worker() -> None:
        while True:
            segnali.get()  # attende il primo errore
            time.sleep(_DEBOUNCE_DIAGNOSTICA)  # assorbe la raffica
            _svuota(segnali)
            try:
                dal = dal_da_app(app)
                Diagnostico(dal, app.state.gateway).analizza_recenti(giorni=1)
            except DalError:
                pass  # repo dati non ancora pronto: si riprova al prossimo errore
            except Exception as exc:  # l'analisi non deve mai far cadere il worker
                log.error("trigger di diagnostica fallito: %s", exc)

    registra_osservatore(osserva)
    threading.Thread(target=worker, name="diagnostica", daemon=True).start()
    log.info("trigger di diagnostica attivo (analisi automatica degli errori)")


def _svuota(coda: "queue.Queue[int]") -> None:
    try:
        while True:
            coda.get_nowait()
    except queue.Empty:
        return


app = create_app()
