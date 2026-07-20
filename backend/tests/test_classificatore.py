"""Classificatore documenti (Fase 2, M7): catalogo, scorciatoia e fallback.

L'instradamento vero (upload → classifica → workflow) è coperto e2e da
``test_ddt_e2e`` e ``test_sal_rapportino_e2e``; qui si coprono i rami di
contorno: catalogo auto-scoperto dai manifest, scorciatoia col catalogo unitario
e il contratto "mai un'eccezione" (fallback su errore).
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.classificatore import FALLBACK_PREDEFINITO, Classificatore
from app.core.dal import DAL
from app.core.gateway import Gateway


def _esplodi(**_kwargs: object) -> object:
    raise AssertionError("il classificatore non doveva interrogare il modello")


def _clf(dati_rw: Path, completer=_esplodi) -> Classificatore:
    return Classificatore(DAL(dati_rw), Gateway(completer=completer, attesa_retry=0))


def test_catalogo_auto_scoperto_dai_manifest(dati_rw: Path) -> None:
    catalogo = _clf(dati_rw).catalogo()
    per_label = {v["label"]: v["workflow"] for v in catalogo}
    # ogni workflow con blocco `ingest` è classificabile senza codice nuovo
    assert per_label["fattura"] == "carica-fattura"
    assert per_label["ddt"] == "carica-ddt"
    assert {"sal", "rapportino"} <= set(per_label)
    # il classificatore stesso (senza `ingest`) non entra nel catalogo
    assert "classifica-documento" not in per_label.values()


def test_catalogo_unitario_non_interroga(dati_rw: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Con un solo tipo non c'è nulla da classificare: si instrada senza LLM."""
    clf = _clf(dati_rw)  # completer che esplode se chiamato
    unico = [{"label": "fattura", "descrizione": "", "workflow": "carica-fattura"}]
    monkeypatch.setattr(clf, "catalogo", lambda: unico)
    assert clf.workflow_per("qualsiasi.pdf") == "carica-fattura"


def test_fallback_su_errore_non_solleva(dati_rw: Path) -> None:
    """Documento illeggibile → nessuna eccezione, si instrada sul fallback."""
    clf = _clf(dati_rw)  # doc inesistente: l'OCR fallisce prima di ogni chiamata LLM
    workflow = clf.workflow_per("blobs/non-esiste.pdf")
    assert workflow == "carica-fattura"  # fallback del manifest


def test_fallback_predefinito_se_manifest_assente(
    dati_rw: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clf = _clf(dati_rw)
    monkeypatch.setattr(clf, "_manifest", dict)  # manifest vuoto → nessun fallback dichiarato
    monkeypatch.setattr(
        clf,
        "catalogo",
        lambda: [
            {"label": "a", "descrizione": "", "workflow": "wf-a"},
            {"label": "b", "descrizione": "", "workflow": "wf-b"},
        ],
    )
    # errore in classificazione + nessun fallback nel manifest → primo del catalogo
    monkeypatch.setattr(clf, "_chiedi", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("giù")))
    assert clf.workflow_per("x.pdf") == "wf-a"
    assert FALLBACK_PREDEFINITO == "carica-fattura"


def test_endpoint_documenti_instrada(client: TestClient, fixtures_docs_dir: Path) -> None:
    """Sanity e2e: un DDT sintetico viene riconosciuto e instradato a carica-ddt."""
    from aiuti import accedi

    admin = accedi(client, "giovanna")
    ddt = next(fixtures_docs_dir.glob("ddt-*.pdf"))
    corpo = client.post(
        "/api/documents",
        headers=admin,
        files={"file": (ddt.name, ddt.read_bytes(), "application/pdf")},
    ).json()
    doc = client.get(f"/api/documents/{corpo['doc_id']}", headers=admin).json()["documento"]
    assert doc["dati"].get("entity_tipo") == "ddt"
