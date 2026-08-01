"""Docling: client del sidecar, tool ``leggi_documento``, effetti sull'ingestione.

L'invariante che questi test difendono più di ogni altro: **senza sidecar, nulla
cambia**. Il tool non esiste, i formati d'ufficio restano rifiutati, i manifest
che dichiarano ``leggi_documento`` non fanno fallire nessun run. La capacità in
più non deve poter diventare una capacità in meno.
"""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from aiuti import accedi
from fake_docling import FakeDocling, RispostaFinta, corpo_ok
from fastapi.testclient import TestClient

from app.core.classificatore import Classificatore
from app.core.dal import DAL
from app.core.docling import DoclingClient, DoclingConfig, DoclingError, docling_attivo
from app.core.gateway import Gateway
from app.core.runtime import WorkflowRuntime
from app.core.tools import Toolset
from app.core.tools.base import ToolError

DOCX = (
    b"PK\x03\x04"  # una firma zip: basta perché il file esista ed abbia l'estensione
    b"finto-documento-word"
)


def client_docling(trasporto: FakeDocling | None = None, **config: object) -> DoclingClient:
    """Un ``DoclingClient`` attivo, col trasporto finto al posto di httpx."""
    return DoclingClient(
        config=DoclingConfig(base_url="http://docling-finto:5001", **config),  # type: ignore[arg-type]
        transport=trasporto or FakeDocling(),
    )


def _blob(dati_rw: Path, nome: str, contenuto: bytes) -> str:
    relativo = f"blobs/caricati/2026/{nome}"
    percorso = dati_rw / relativo
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_bytes(contenuto)
    return relativo


def _blob_da_fixture(dati_rw: Path, fixtures_dir: Path, nome: str) -> str:
    relativo = f"blobs/caricati/2026/{nome}"
    percorso = dati_rw / relativo
    percorso.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixtures_dir / nome, percorso)
    return relativo


# ------------------------------------------------------------------- interruttore


def test_spento_senza_variabile_ambiente() -> None:
    """L'unica cosa che accende Docling è ``DOCLING_URL`` (la conftest la toglie)."""
    assert docling_attivo() is False
    assert DoclingClient().attivo() is False


def test_acceso_da_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCLING_URL", "http://docling:5001")
    assert docling_attivo() is True
    config = DoclingConfig.da_env()
    assert config is not None and config.base_url == "http://docling:5001"


def test_config_numerica_illeggibile_non_spegne_nulla(monkeypatch: pytest.MonkeyPatch) -> None:
    """Una variabile scritta male è configurazione sbagliata, non un guasto."""
    monkeypatch.setenv("DOCLING_URL", "http://docling:5001")
    monkeypatch.setenv("DOCLING_TIMEOUT", "un-attimo")
    config = DoclingConfig.da_env()
    assert config is not None and config.timeout == 120.0


# ------------------------------------------------------------------------ client


def test_converte_e_riporta_qualita(tmp_path: Path) -> None:
    file = tmp_path / "fattura.pdf"
    file.write_bytes(b"%PDF-1.4 finto")
    trasporto = FakeDocling()

    esito = client_docling(trasporto).converti(file)

    assert "Ritenuta d'acconto" in esito["markdown"]
    assert "| Descrizione" in esito["markdown"], "la tabella deve arrivare come tabella"
    assert esito["troncato"] is False
    assert esito["qualita"] == "good"
    assert esito["secondi"] == 0.13
    # il file è stato mandato davvero, all'endpoint giusto
    assert trasporto.chiamate[0]["url"].endswith("/v1/convert/file")
    assert trasporto.chiamate[0]["nome"] == "fattura.pdf"
    assert trasporto.chiamate[0]["byte"] > 0
    assert trasporto.chiamate[0]["data"] == {"to_formats": "md"}


def test_tronca_e_lo_dichiara(tmp_path: Path) -> None:
    """Un documento lunghissimo non deve riempire la finestra di contesto."""
    file = tmp_path / "capitolato.pdf"
    file.write_bytes(b"%PDF-1.4 finto")
    lungo = RispostaFinta(200, corpo_ok("x" * 5_000))

    esito = client_docling(FakeDocling([lungo]), max_caratteri=1_000).converti(file)

    assert esito["troncato"] is True
    assert len(esito["markdown"]) == 1_000


@pytest.mark.parametrize(
    ("risposte", "errore", "atteso"),
    [
        ([], ConnectionError("connessione rifiutata"), "non raggiungibile"),
        ([RispostaFinta(503, {"detail": "modello in caricamento"})], None, "ha risposto 503"),
        ([RispostaFinta(200, ...)], None, "non JSON"),
        ([RispostaFinta(200, {"status": "success"})], None, "non ha prodotto un documento"),
        ([RispostaFinta(200, corpo_ok("   "))], None, "non ha estratto testo"),
    ],
)
def test_ogni_fallimento_diventa_docling_error(
    tmp_path: Path, risposte: list, errore: Exception | None, atteso: str
) -> None:
    """Sidecar giù, 5xx, corpo malformato, testo vuoto: un solo tipo d'errore."""
    file = tmp_path / "doc.pdf"
    file.write_bytes(b"%PDF-1.4 finto")
    client = client_docling(FakeDocling(risposte, errore=errore))
    with pytest.raises(DoclingError, match=atteso):
        client.converti(file)


def test_client_spento_non_prova_nemmeno(tmp_path: Path) -> None:
    file = tmp_path / "doc.pdf"
    file.write_bytes(b"%PDF-1.4 finto")
    with pytest.raises(DoclingError, match="non configurato"):
        DoclingClient(config=None, transport=FakeDocling()).converti(file)


# -------------------------------------------------------------------------- tool


def test_tool_registrato_solo_col_sidecar(dati_rw: Path) -> None:
    dal = DAL(dati_rw)
    assert "leggi_documento" not in {v["name"] for v in Toolset(dal).elenco()}
    con_sidecar = Toolset(dal, docling=client_docling())
    assert "leggi_documento" in {v["name"] for v in con_sidecar.elenco()}
    # e resta un tool *nativo*: non è un pytool consolidato del Toolsmith
    voce = next(v for v in con_sidecar.elenco() if v["name"] == "leggi_documento")
    assert voce["origine"] == "nativa"
    assert "leggi_documento" not in con_sidecar.nomi_consolidati()


def test_tool_legge_un_pdf(dati_rw: Path, fixtures_dir: Path) -> None:
    doc = _blob_da_fixture(dati_rw, fixtures_dir, "fattura-studio-bianchi.pdf")
    toolset = Toolset(DAL(dati_rw), docling=client_docling())

    risultato = toolset.esegui("leggi_documento", {"path": doc})

    assert "Ritenuta d'acconto" in risultato["markdown"]
    assert risultato["pagine"] == 1
    assert "avviso" not in risultato and "avviso_qualita" not in risultato
    # niente immagini: è la chiave su cui si ramifica runtime._risultato_per_llm,
    # e questo risultato deve passare per la strada del JSON semplice
    assert "immagini_png_base64" not in risultato


def test_tool_legge_un_docx(dati_rw: Path) -> None:
    """Il formato che il sistema, senza sidecar, non sa nemmeno accettare."""
    doc = _blob(dati_rw, "computo.docx", DOCX)
    toolset = Toolset(DAL(dati_rw), docling=client_docling())
    assert "TOTALE" in toolset.esegui("leggi_documento", {"path": doc})["markdown"]


def test_tool_rifiuta_le_foto(dati_rw: Path) -> None:
    """Le foto vanno a ``ocr_pdf``: qui il rifiuto è una scelta, non una mancanza."""
    doc = _blob(dati_rw, "foto.jpg", b"\xff\xd8\xff finto jpeg")
    toolset = Toolset(DAL(dati_rw), docling=client_docling())
    with pytest.raises(ToolError, match="non supportato"):
        toolset.esegui("leggi_documento", {"path": doc})


def test_tool_stesso_perimetro_di_ocr_pdf(dati_rw: Path) -> None:
    toolset = Toolset(DAL(dati_rw), docling=client_docling())
    with pytest.raises(ToolError, match="fuori dal repo dati"):
        toolset.esegui("leggi_documento", {"path": "../segreti.pdf"})
    with pytest.raises(ToolError, match="non trovato"):
        toolset.esegui("leggi_documento", {"path": "blobs/caricati/2026/inesistente.pdf"})


def test_tool_ferma_i_documenti_troppo_lunghi(dati_rw: Path, fixtures_dir: Path) -> None:
    """Il tetto di pagine scatta *prima* di occupare la GPU del sidecar."""
    import pymupdf

    relativo = "blobs/caricati/2026/capitolato.pdf"
    percorso = dati_rw / relativo
    percorso.parent.mkdir(parents=True, exist_ok=True)
    lungo = pymupdf.open()
    with pymupdf.open(fixtures_dir / "fattura-studio-bianchi.pdf") as sorgente:
        for _ in range(11):
            lungo.insert_pdf(sorgente)
    lungo.save(percorso)
    lungo.close()

    trasporto = FakeDocling()
    toolset = Toolset(DAL(dati_rw), docling=client_docling(trasporto))
    with pytest.raises(ToolError, match="troppe pagine"):
        toolset.esegui("leggi_documento", {"path": relativo})
    assert trasporto.chiamate == [], "il sidecar non doveva nemmeno essere interpellato"


def test_errore_del_sidecar_indirizza_il_modello_su_ocr_pdf(
    dati_rw: Path, fixtures_dir: Path
) -> None:
    """Il messaggio d'errore è per il modello: deve dirgli cosa fare dopo."""
    doc = _blob_da_fixture(dati_rw, fixtures_dir, "fattura-studio-bianchi.pdf")
    spento = client_docling(FakeDocling(errore=ConnectionError("nessuna rotta")))
    toolset = Toolset(DAL(dati_rw), docling=spento)
    with pytest.raises(ToolError, match="ocr_pdf"):
        toolset.esegui("leggi_documento", {"path": doc})


def test_qualita_bassa_viene_dichiarata(dati_rw: Path, fixtures_dir: Path) -> None:
    """Se Docling non si è fidato di sé, il modello deve saperlo."""
    doc = _blob_da_fixture(dati_rw, fixtures_dir, "fattura-studio-bianchi.pdf")
    scarsa = RispostaFinta(200, corpo_ok(qualita="poor"))
    toolset = Toolset(DAL(dati_rw), docling=client_docling(FakeDocling([scarsa])))

    risultato = toolset.esegui("leggi_documento", {"path": doc})
    assert "ocr_pdf" in risultato["avviso_qualita"]


# ----------------------------------------------------------------------- runtime


def test_manifest_che_dichiara_il_tool_regge_senza_sidecar(
    dati_rw: Path, fixtures_dir: Path
) -> None:
    """Il caso che romperebbe tutto: manifest scritto per la macchina con la GPU.

    I manifest di serie dichiarano ``leggi_documento``. Su una macchina senza
    sidecar quel nome non esiste nel registro, e ``schemi()`` solleverebbe: senza
    la selezione dei disponibili, **ogni** run fallirebbe.
    """
    from fake_llm import FakeCompleter

    manifest = dati_rw / "workflows" / "carica-fattura" / "manifest.yaml"
    assert "leggi_documento" in manifest.read_text(encoding="utf-8")

    doc = _blob_da_fixture(dati_rw, fixtures_dir, "fattura-calcestruzzi-etna.pdf")
    dal = DAL(dati_rw)
    runtime = WorkflowRuntime(dal, Gateway(completer=FakeCompleter(dati_rw), attesa_retry=0))
    assert runtime.toolset.disponibili(["leggi_documento"]) == ([], ["leggi_documento"])

    esito = runtime.esegui("carica-fattura", doc, run_id="run-senza-sidecar")
    assert esito.esito == "ok", esito.errore
    assert esito.entity_id


def test_run_completo_passando_dal_sidecar(dati_rw: Path) -> None:
    """Il giro intero su un ``.docx``: leggi_documento → ricerche → bozza salvata.

    È la prova che serve: un formato che il sistema, senza sidecar, non sa nemmeno
    aprire, attraversa tutto il workflow e diventa una fattura in anagrafica.
    """
    from fake_llm import FakeCompleter

    doc = _blob(dati_rw, "fattura.docx", DOCX)
    dal = DAL(dati_rw)
    trasporto = FakeDocling()
    runtime = WorkflowRuntime(
        dal,
        Gateway(completer=FakeCompleter(dati_rw), attesa_retry=0),
        docling=client_docling(trasporto),
    )

    esito = runtime.esegui("carica-fattura", doc, run_id="run-docling")

    assert esito.esito == "ok", esito.errore
    assert len(trasporto.chiamate) == 1, "il documento va letto una volta sola"

    fattura = dal.read("fattura", esito.entity_id or "").dati
    assert fattura["numero"] == "15/2026"
    assert fattura["data"] == "2026-07-08"
    assert (fattura["imponibile"], fattura["iva"], fattura["totale"]) == (4000.0, 880.0, 4880.0)
    # le ricerche hanno lavorato sul testo di Docling, non su un PDF
    assert fattura["fornitore_id"] == "FRN-007"
    assert fattura["cantiere_id"] == "CNT-001"
    # e la riga della tabella è arrivata come riga, non come testo appiattito
    assert [r["descrizione"] for r in fattura["righe"]] == [
        "Direzione lavori strutture - II acconto"
    ]


def test_sidecar_giu_a_meta_run_non_ferma_niente(dati_rw: Path, fixtures_dir: Path) -> None:
    """Il fallback vero: Docling fallisce, il modello ripiega su ``ocr_pdf``, il run chiude.

    È l'invariante di ``api/documents.py`` — mai un errore bloccante — verificato
    dove conta, cioè dentro al giro agentico e non in un unit test del client.
    """
    from fake_llm import FakeCompleter

    doc = _blob_da_fixture(dati_rw, fixtures_dir, "fattura-studio-bianchi.pdf")
    dal = DAL(dati_rw)
    rotto = client_docling(FakeDocling(errore=ConnectionError("sidecar spento")))
    runtime = WorkflowRuntime(
        dal, Gateway(completer=FakeCompleter(dati_rw), attesa_retry=0), docling=rotto
    )

    esito = runtime.esegui("carica-fattura", doc, run_id="run-ripiego")

    assert esito.esito == "ok", esito.errore
    fattura = dal.read("fattura", esito.entity_id or "").dati
    assert fattura["totale"] == 4880.0  # letta lo stesso, dalle pagine come immagini

    # e la storia resta leggibile: prima il tentativo fallito, poi il ripiego
    from app.core.tracer import leggi_eventi

    chiamate = [
        (e["name"], e["ok"])
        for e in leggi_eventi(dati_rw, "run-ripiego", {"tool_call"})
    ]
    assert ("leggi_documento", False) in chiamate
    assert ("ocr_pdf", True) in chiamate


# ----------------------------------------------------------------- classificatore


def test_classificatore_preferisce_il_testo(dati_rw: Path, fixtures_dir: Path) -> None:
    """Per dire "è una fattura" bastano le prime righe: niente pagine come immagini."""
    from fake_llm import FakeCompleter

    doc = _blob_da_fixture(dati_rw, fixtures_dir, "fattura-studio-bianchi.pdf")
    trasporto = FakeDocling()
    gateway = Gateway(completer=FakeCompleter(dati_rw), attesa_retry=0)
    classificatore = Classificatore(DAL(dati_rw), gateway, docling=client_docling(trasporto))

    parti = classificatore._parti_documento(doc)

    assert len(trasporto.chiamate) == 1
    assert [p["type"] for p in parti] == ["text"]
    assert "Ritenuta d'acconto" in parti[0]["text"]


def test_classificatore_ricade_sulle_immagini(dati_rw: Path, fixtures_dir: Path) -> None:
    """Sidecar giù: si torna alle pagine come immagini, senza far rumore."""
    from fake_llm import FakeCompleter

    doc = _blob_da_fixture(dati_rw, fixtures_dir, "fattura-studio-bianchi.pdf")
    spento = client_docling(FakeDocling(errore=ConnectionError("giù")))
    gateway = Gateway(completer=FakeCompleter(dati_rw), attesa_retry=0)
    classificatore = Classificatore(DAL(dati_rw), gateway, docling=spento)

    parti = classificatore._parti_documento(doc)
    assert [p["type"] for p in parti] == ["text", "image_url"]


# -------------------------------------------------------------------- ingestione


def test_docx_rifiutato_senza_sidecar(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    """Accettare un file che poi nessuno sa leggere sarebbe peggio che rifiutarlo."""
    client = crea_client()
    intestazioni = accedi(client, "giovanna")
    corpo = client.post(
        "/api/documents",
        headers=intestazioni,
        files={"file": ("computo.docx", DOCX, "application/octet-stream")},
    ).json()

    documento = DAL(dati_rw).read("documento", corpo["doc_id"])
    assert documento.dati["esito"] == "errore"
    assert documento.dati["issue_id"], "serve una issue: se ne occupa l'ufficio"


def test_docx_accettato_col_sidecar(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    client = crea_client(docling=client_docling())
    intestazioni = accedi(client, "giovanna")
    corpo = client.post(
        "/api/documents",
        headers=intestazioni,
        files={"file": ("computo.docx", DOCX, "application/octet-stream")},
    ).json()

    documento = DAL(dati_rw).read("documento", corpo["doc_id"])
    assert documento.dati["esito"] != "errore"
    assert documento.dati["issue_id"] is None


# -------------------------------------------------------- anteprima in revisione


def _docx_da_rivedere(client: TestClient, dati_rw: Path) -> str:
    corpo = client.post(
        "/api/documents",
        headers=accedi(client, "giovanna"),
        files={"file": ("fattura.docx", DOCX, "application/octet-stream")},
    ).json()
    entity_id = DAL(dati_rw).read("documento", corpo["doc_id"]).dati["entity_id"]
    assert entity_id, "senza entità non c'è niente da revisionare"
    return str(entity_id)


def test_anteprima_docx_e_html_non_un_download(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    """Word il browser lo scarica: chi revisiona resterebbe senza documento."""
    client = crea_client(docling=client_docling())
    entity_id = _docx_da_rivedere(client, dati_rw)

    risposta = client.get(f"/api/review/{entity_id}/originale", headers=accedi(client, "giovanna"))
    assert risposta.status_code == 200
    assert risposta.headers["content-type"].startswith("text/html")
    assert "<table" in risposta.text


def test_anteprima_chiede_html_non_markdown(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    """Il formato chiesto al sidecar è quello che serve al browser."""
    trasporto = FakeDocling()
    client = crea_client(docling=client_docling(trasporto))
    entity_id = _docx_da_rivedere(client, dati_rw)
    trasporto.chiamate.clear()

    client.get(f"/api/review/{entity_id}/originale", headers=accedi(client, "giovanna"))
    assert [c["data"]["to_formats"] for c in trasporto.chiamate] == ["html"]


def test_sidecar_giu_non_toglie_il_documento_a_chi_revisiona(
    crea_client: Callable[..., TestClient], dati_rw: Path
) -> None:
    """Peggio del previsto (il file com'è), mai un 500 in faccia all'ufficio."""
    client = crea_client(docling=client_docling())
    entity_id = _docx_da_rivedere(client, dati_rw)
    client.app.state.docling = client_docling(FakeDocling(errore=RuntimeError("sidecar giù")))

    risposta = client.get(f"/api/review/{entity_id}/originale", headers=accedi(client, "giovanna"))
    assert risposta.status_code == 200
    assert risposta.content == DOCX


def test_pdf_resta_il_file_originale(
    crea_client: Callable[..., TestClient], dati_rw: Path, fixtures_dir: Path
) -> None:
    """Il PDF il browser lo disegna: convertirlo perderebbe l'originale per nulla."""
    client = crea_client(docling=client_docling())
    corpo = client.post(
        "/api/documents",
        headers=accedi(client, "giovanna"),
        files={
            "file": (
                "fattura-calcestruzzi-etna.pdf",
                (fixtures_dir / "fattura-calcestruzzi-etna.pdf").read_bytes(),
                "application/pdf",
            )
        },
    ).json()
    entity_id = DAL(dati_rw).read("documento", corpo["doc_id"]).dati["entity_id"]

    risposta = client.get(f"/api/review/{entity_id}/originale", headers=accedi(client, "giovanna"))
    assert risposta.headers["content-type"] == "application/pdf"
    assert risposta.content[:4] == b"%PDF"


def test_registro_tool_mostra_il_sidecar(
    crea_client: Callable[..., TestClient],
) -> None:
    """La pagina Skills & Tools deve dire la verità su *questa* macchina."""

    def nomi_tool(client: TestClient) -> set[str]:
        corpo = client.get("/api/tools", headers=accedi(client, "giovanna")).json()
        return {t["name"] for t in corpo["tools"]}

    assert "leggi_documento" not in nomi_tool(crea_client())
    assert "leggi_documento" in nomi_tool(crea_client(docling=client_docling()))
