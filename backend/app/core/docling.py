"""Client Docling: il documento come **testo strutturato**, non come pixel.

Docling gira in un **container affiancato con la GPU** (vedi ``docker-compose.yml``
e ``docs/deploy.md``), mai in-process: il container dell'app resta leggero e senza
PyTorch. Questo modulo è la cornice di accesso, gemella di ``erp.py``:

- **Config da env**, mai hard-coded (stesso principio dei tier LLM del Gateway):
  ``DOCLING_URL`` e basta. Se manca, :func:`docling_attivo` è falso, il tool
  ``leggi_documento`` non viene nemmeno registrato e il sistema si comporta
  **esattamente** come prima (l'LLM legge le pagine come immagini con ``ocr_pdf``).
- **Trasporto iniettabile** (come ``Gateway(completer=...)`` e ``ErpClient``): il
  default usa ``httpx``; i test iniettano un finto e non toccano mai un container.

La costruzione non fa I/O. Ogni fallimento — sidecar giù, timeout, HTTP >= 400,
corpo inatteso — diventa :class:`DoclingError`, che il tool traduce in ``ToolError``:
il modello lo riceve come risultato d'errore e prosegue con ``ocr_pdf``. **Il parser
non deve mai essere un single-point-of-failure sull'ingestione** (contratto di
``api/documents.py``: mai un errore bloccante per l'operatore).

Perché l'endpoint **sincrono** e non quello asincrono: la conversione misurata sta
sotto il secondo (13 pagine/s su RTX 3080) e la chiamata avviene già dentro un
``BackgroundTask``, quindi non blocca nessuna richiesta dell'operatore. L'endpoint
sincrono di docling-serve interroga però la coda interna ogni
``DOCLING_SERVE_SYNC_POLL_INTERVAL`` secondi (default 2): va portato a ``1`` nel
compose, altrimenti si pagano 2 secondi anche per una conversione da 130 ms.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.logbook import ottieni_logger

_log = ottieni_logger("docling")

# Trasporto: (url, *, files, data, timeout) -> risposta con .status_code e .json().
# Firma volutamente httpx-compatibile, così il default è un thin wrapper e il finto
# dei test è banale (vedi tests/fake_docling.py).
Transport = Callable[..., Any]

# Generoso: una scansione di 10 pagine costa ~1,2 s/pagina di OCR (su CPU, dentro
# il sidecar) più il pavimento della coda. Meglio un tetto alto e un fallimento
# raro che un timeout che scatta su un documento buono.
TIMEOUT_DEFAULT = 120.0

# Tetto al Markdown iniettato nel contesto. Il documento entra nel giro agentico
# (max 12 giri in runtime.py) e ci resta: un allegato tecnico da 200 pagine
# riempirebbe la finestra e farebbe fallire lo step. Oltre il tetto si tronca e
# **lo si dichiara** al modello, che così sa di non aver visto tutto.
MAX_CARATTERI_DEFAULT = 60_000

# Estensioni che ha senso mandare a Docling. Le immagini (foto da cantiere) NON
# sono qui di proposito: su una foto storta un modello vision legge meglio di
# OCR + layout, e quella strada resta `ocr_pdf` (vedi analisi-docling.md §5).
ESTENSIONI = frozenset({".pdf", ".docx", ".xlsx", ".pptx", ".html", ".htm", ".csv", ".md"})

# Giudizi di qualità che docling restituisce nel blocco `confidence`. Quelli bassi
# vengono passati al modello: è il segnale che il testo va preso con le molle e
# conviene guardare anche le pagine come immagini.
QUALITA_BASSA = frozenset({"poor", "fair"})


class DoclingError(Exception):
    """Errore verso il sidecar Docling: irraggiungibile, HTTP >= 400, corpo inatteso.

    ``stato`` porta il codice HTTP quando c'è stata una risposta, ``None`` quando
    non si è arrivati a parlare col server — la stessa distinzione di ``ErpError``:
    "ha detto di no" e "non lo so" sono due cose diverse per chi legge il log.
    """

    def __init__(self, messaggio: str, stato: int | None = None) -> None:
        super().__init__(messaggio)
        self.stato = stato


@dataclass(frozen=True)
class DoclingConfig:
    """Coordinate del sidecar, lette dall'ambiente.

    ``base_url`` è l'unica obbligatoria: senza, Docling è spento. In compose il
    valore è ``http://docling:5001`` (il nome del servizio). In sviluppo su Windows
    usare ``http://127.0.0.1:5001`` e **non** ``localhost``: il resolver tenta
    prima IPv6 e paga ~21 s di timeout prima di ripiegare su IPv4.
    """

    base_url: str
    timeout: float = TIMEOUT_DEFAULT
    max_caratteri: int = MAX_CARATTERI_DEFAULT

    @classmethod
    def da_env(cls) -> DoclingConfig | None:
        base = (os.environ.get("DOCLING_URL") or "").strip()
        if not base:
            return None
        return cls(
            base_url=base,
            timeout=_float_env("DOCLING_TIMEOUT", TIMEOUT_DEFAULT),
            max_caratteri=int(_float_env("DOCLING_MAX_CARATTERI", MAX_CARATTERI_DEFAULT)),
        )


def _float_env(nome: str, predefinito: float) -> float:
    """Un numero dall'ambiente; se illeggibile si tiene il default e si logga.

    Una variabile scritta male non deve spegnere il parser né far cadere l'avvio:
    è configurazione, non un invariante.
    """
    grezzo = (os.environ.get(nome) or "").strip()
    if not grezzo:
        return predefinito
    try:
        return float(grezzo)
    except ValueError:
        _log.warning("%s non è un numero (%r): uso %s", nome, grezzo, predefinito)
        return predefinito


def docling_attivo() -> bool:
    """Vero se il sidecar è cablato (``DOCLING_URL`` presente).

    Interruttore analogo a ``Gateway.t3_attivo`` e ``erp.erp_attivo``: finché è
    spento, il tool ``leggi_documento`` non esiste per il modello e i workflow
    girano come sempre.
    """
    return DoclingConfig.da_env() is not None


def _trasporto_httpx(
    url: str,
    *,
    files: dict[str, Any],
    data: dict[str, str],
    timeout: float = TIMEOUT_DEFAULT,
) -> httpx.Response:
    """Trasporto reale: un singolo POST multipart con ``httpx``."""
    return httpx.post(url, files=files, data=data, timeout=timeout)


class DoclingClient:
    """Accesso HTTP al sidecar Docling. Costruzione senza I/O.

    ``config`` default = :meth:`DoclingConfig.da_env`; ``transport`` default =
    ``httpx``. Entrambi iniettabili per i test.
    """

    def __init__(
        self,
        config: DoclingConfig | None = None,
        transport: Transport | None = None,
    ) -> None:
        # Nota: se ``config`` è None si tenta l'env, ma resta None se non configurato.
        self.config = config if config is not None else DoclingConfig.da_env()
        self._transport = transport or _trasporto_httpx

    def attivo(self) -> bool:
        return self.config is not None

    def converti(self, file: Path) -> dict[str, Any]:
        """Il documento come Markdown strutturato (tabelle comprese).

        Ritorna ``{"markdown", "troncato", "qualita", "secondi"}``. Solleva
        :class:`DoclingError` per qualunque fallimento: chi chiama deve poter
        ricadere su ``ocr_pdf`` senza distinguere il motivo.
        """
        corpo, markdown = self._chiedi(file, "md")
        troncato = len(markdown) > self._max_caratteri()
        if troncato:
            markdown = markdown[: self._max_caratteri()]
        return {
            "markdown": markdown,
            "troncato": troncato,
            "qualita": _qualita(corpo),
            "secondi": round(float(corpo.get("processing_time") or 0.0), 2),
        }

    def anteprima_html(self, file: Path) -> str:
        """Il documento come pagina HTML autonoma, per l'anteprima umana.

        Serve alla revisione: Word ed Excel il browser non li disegna (li fa
        scaricare), e chi controlla una bozza resta senza il documento a fianco.

        **Non è l'originale**: è la lettura che Docling ne ha fatto — la stessa
        da cui il modello ha estratto i campi. Per la revisione è un vantaggio
        (un errore del parser si vede subito, invece di dedurlo dai numeri), ma
        va detto a chi guarda, e chi chiama non deve spacciarla per l'originale.

        Nessun tetto ai caratteri: qui non si riempie la finestra di contesto di
        un modello, e troncare HTML a metà tag darebbe una pagina rotta. Il
        limite vero resta quello sulla dimensione dell'upload.
        """
        return self._chiedi(file, "html")[1]

    # ------------------------------------------------------------- interni

    def _max_caratteri(self) -> int:
        return self.config.max_caratteri if self.config else MAX_CARATTERI_DEFAULT

    def _chiedi(self, file: Path, formato: str) -> tuple[dict[str, Any], str]:
        """Un POST al sidecar; ritorna ``(corpo, contenuto)`` o solleva.

        Unico punto in cui si parla col sidecar: Markdown e HTML differiscono
        solo per il formato chiesto e per la chiave da leggere nella risposta.
        """
        if self.config is None:
            raise DoclingError("Docling non configurato (DOCLING_URL assente)")
        chiave = f"{formato}_content"

        url = self.config.base_url.rstrip("/") + "/v1/convert/file"
        try:
            with file.open("rb") as contenuto:
                risposta = self._transport(
                    url,
                    files={"files": (file.name, contenuto, "application/octet-stream")},
                    data={"to_formats": formato},
                    timeout=self.config.timeout,
                )
        except DoclingError:
            raise
        except Exception as exc:  # sidecar giù, timeout, DNS…
            raise DoclingError(f"Docling non raggiungibile ({file.name}): {exc}") from exc

        stato = getattr(risposta, "status_code", None)
        if stato is None or stato >= 400:
            raise DoclingError(
                f"Docling ha risposto {stato} su {file.name}: {_corpo_sicuro(risposta)}",
                stato=stato,
            )
        try:
            corpo = risposta.json()
        except Exception as exc:
            raise DoclingError(f"risposta di Docling non JSON su {file.name}: {exc}") from exc
        if not isinstance(corpo, dict):
            raise DoclingError(f"risposta di Docling inattesa su {file.name}")

        esito = str(corpo.get("status") or "").lower()
        documento = corpo.get("document")
        if not isinstance(documento, dict):
            raise DoclingError(f"Docling non ha prodotto un documento per {file.name}")
        contenuto_estratto = documento.get(chiave)
        if not isinstance(contenuto_estratto, str) or not contenuto_estratto.strip():
            # Non è un errore di trasporto ma il risultato è inutilizzabile: meglio
            # dirlo e lasciare che il modello guardi le pagine come immagini.
            raise DoclingError(
                f"Docling non ha estratto testo da {file.name} (status: {esito or '?'})"
            )
        if esito in ("failure", "error"):
            raise DoclingError(f"Docling ha fallito la conversione di {file.name}")
        return corpo, contenuto_estratto


def _qualita(corpo: dict[str, Any]) -> str | None:
    """Il giudizio *pessimista* di Docling sulla conversione (``low_grade``).

    Docling misura per conto suo quanto è andata bene (parse, layout, tabelle,
    OCR) e ne dà un voto. Si prende il peggiore, non la media: una pagina letta
    male in mezzo a dieci buone è esattamente il caso in cui il modello deve
    guardare anche l'immagine, e una media lo nasconderebbe.
    """
    confidenza = corpo.get("confidence")
    if not isinstance(confidenza, dict):
        return None
    voto = confidenza.get("low_grade") or confidenza.get("mean_grade")
    return str(voto) if voto else None


def _corpo_sicuro(risposta: Any) -> str:
    """Un estratto corto del corpo per il messaggio d'errore (mai il payload intero)."""
    testo = getattr(risposta, "text", "") or ""
    return testo[:200]
