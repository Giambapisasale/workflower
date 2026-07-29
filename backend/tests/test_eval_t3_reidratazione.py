"""Re-idratare i prompt e offrire le pagine come testo: valutare un T3 non multimodale.

Due limiti dell'harness che si vedono solo quando il candidato T3 è un modello
*piccolo* fine-tuned (FunctionGemma 270M):

1. I prompt di sistema restavano **troncati** — il trace li riduce a impronta
   perché superano i 400 caratteri. Si può ricostruirli dal repo dati (la skill e
   lo schema sono ancora lì), ma solo **verificando** l'impronta: se la skill è
   cambiata dopo il run (Improver), un prompt *diverso* falserebbe la misura,
   mentre uno troncato la limita in modo dichiarato. Ricostruire ≠ indovinare.
2. Le pagine venivano offerte solo come **immagini**. Un modello senza torre
   visiva non le legge: con ``LLM_T3_SOLO_TESTO=1`` arriva il testo, alla stessa
   maniera per entrambi i tier — altrimenti il confronto misurerebbe la modalità
   e non il modello.
"""

import json
from pathlib import Path

import pytest
import yaml
from aiuti import accedi
from fake_llm import FakeCompleter
from fastapi.testclient import TestClient

from app.core.dal import DAL
from app.core.eval_t3 import ENV_SOLO_TESTO, EvalT3, _impronta, _prompt_troncati, solo_testo
from app.core.gateway import Gateway
from app.core.tools import ocr_pdf
from app.core.tools.base import ToolError

WORKFLOW = "carica-fattura@1.0"


def _valutatore(dati: Path) -> EvalT3:
    return EvalT3(DAL(dati), Gateway(completer=FakeCompleter(dati), attesa_retry=0))


def _prompt_veri(dati: Path) -> list[str]:
    """La skill e il contratto che il runtime comporrebbe, presi dal repo."""
    return _valutatore(dati)._prompt_del_workflow(WORKFLOW)


# --------------------------------------------------- re-idratazione dei prompt


def test_i_prompt_del_workflow_si_ricostruiscono_dal_repo(dati_rw: Path) -> None:
    skill, contratto = _prompt_veri(dati_rw)
    manifest = yaml.safe_load(
        (dati_rw / "workflows" / "carica-fattura" / "manifest.yaml").read_text(encoding="utf-8")
    )
    step = next(s for s in manifest["steps"] if "skill" in s)
    # la skill è esattamente il file dichiarato dallo step, non una parafrasi
    assert skill == (dati_rw / "workflows" / "carica-fattura" / step["skill"]).read_text(
        encoding="utf-8"
    )
    # il contratto porta dentro lo schema dell'entità
    assert "Contratto di output" in contratto
    assert "confidence" in contratto
    assert json.loads((dati_rw / step["output_schema"]).read_text(encoding="utf-8"))


def test_reidrata_solo_se_l_impronta_combacia(dati_rw: Path) -> None:
    """Il digest è la prova: se combacia si sostituisce, se no si lascia troncato."""
    valutatore = _valutatore(dati_rw)
    skill, contratto = _prompt_veri(dati_rw)
    esempio = {
        "workflow": WORKFLOW,
        "messages": [
            {"role": "system", "content": f"<{len(skill)} caratteri, sha256:{_impronta(skill)}>"},
            {
                "role": "system",
                "content": f"<{len(contratto)} caratteri, sha256:{_impronta(contratto)}>",
            },
            {"role": "user", "content": "Documento da elaborare: blobs/x.pdf"},
        ],
    }
    messaggi = valutatore._reidrata_prompt(esempio)
    assert messaggi[0]["content"] == skill
    assert messaggi[1]["content"] == contratto
    assert valutatore._prompt_reidratati == 2
    assert _prompt_troncati(messaggi) == 0


def test_impronta_diversa_resta_troncata(dati_rw: Path) -> None:
    """Skill cambiata dopo il run: meglio un prompt dichiaratamente troncato che uno falso."""
    valutatore = _valutatore(dati_rw)
    segnaposto = "<3010 caratteri, sha256:000000000000>"
    esempio = {"workflow": WORKFLOW, "messages": [{"role": "system", "content": segnaposto}]}
    messaggi = valutatore._reidrata_prompt(esempio)
    assert messaggi[0]["content"] == segnaposto
    assert valutatore._prompt_reidratati == 0
    assert _prompt_troncati(messaggi) == 1


def test_reidratazione_non_inventa_su_workflow_sconosciuto(dati_rw: Path) -> None:
    valutatore = _valutatore(dati_rw)
    esempio = {
        "workflow": "workflow-che-non-esiste@9.9",
        "messages": [{"role": "system", "content": "<999 caratteri, sha256:abcabcabcabc>"}],
    }
    assert valutatore._reidrata_prompt(esempio) == esempio["messages"]
    assert valutatore._prompt_reidratati == 0


# ------------------------------------------------------- pagine come testo


def test_testo_pagine_legge_lo_strato_testuale(fixtures_dir: Path, tmp_path: Path) -> None:
    """La controparte testuale di ocr_pdf: stesse pagine, senza immagini."""
    origine = fixtures_dir / "fattura-studio-bianchi.pdf"
    (tmp_path / "blobs").mkdir()
    destinazione = tmp_path / "blobs" / "fattura.pdf"
    destinazione.write_bytes(origine.read_bytes())

    pagine = ocr_pdf.testo_pagine(tmp_path, "blobs/fattura.pdf")
    assert len(pagine) == 1
    testo = pagine[0]
    # i dati dello scenario M5 devono esserci: è il documento della ritenuta
    assert "Studio Tecnico Ing. Bianchi" in testo
    assert "4.880,00" in testo
    assert "Ritenuta" in testo


def test_testo_pagine_rifiuta_i_percorsi_fuori_dal_repo(tmp_path: Path) -> None:
    """Stessa validazione di ocr_pdf: il repo dati è il confine."""
    with pytest.raises(ToolError):
        ocr_pdf.testo_pagine(tmp_path, "../fuori.pdf")
    with pytest.raises(ToolError):
        ocr_pdf.testo_pagine(tmp_path, "blobs/inesistente.pdf")


def test_solo_testo_si_accende_dall_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    """Come i nomi dei modelli: dall'ambiente, mai deciso nel codice."""
    monkeypatch.delenv(ENV_SOLO_TESTO, raising=False)
    assert solo_testo() is False
    for valore in ("1", "true", "si", "sì", "TRUE"):
        monkeypatch.setenv(ENV_SOLO_TESTO, valore)
        assert solo_testo() is True, valore
    for valore in ("0", "", "no"):
        monkeypatch.setenv(ENV_SOLO_TESTO, valore)
        assert solo_testo() is False, valore


def test_pagine_testuali_rinuncia_senza_originale(dati_rw: Path) -> None:
    """Senza il documento non si misura: dichiarato non rigiocabile, non "pagina vuota"."""
    valutatore = _valutatore(dati_rw)
    esempio = {"run_id": "run-inesistente", "messages": []}
    assert valutatore._pagine_testuali(esempio) is None
    assert valutatore._pagine_testuali({"messages": []}) is None  # senza run_id


def _run_con_documento(dati: Path, fixtures_dir: Path, run_id: str) -> str:
    """Un run minimo: il blob del documento + il trace che lo nomina in run_start."""
    blob = f"blobs/caricati/2026/{run_id}.pdf"
    percorso = dati / blob
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_bytes((fixtures_dir / "fattura-studio-bianchi.pdf").read_bytes())
    trace = dati / "traces" / "2026" / "07" / f"{run_id}.jsonl"
    trace.parent.mkdir(parents=True, exist_ok=True)
    trace.write_text(
        json.dumps(
            {
                "ts": "2026-07-28T08:00:00.000+00:00",
                "run_id": run_id,
                "evento": "run_start",
                "workflow": "carica-fattura",
                "version": "1.0",
                "input": blob,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return blob


def test_pagine_testuali_sostituisce_l_immagine_col_testo(
    dati_rw: Path, fixtures_dir: Path
) -> None:
    """Il caso che rende valutabile un T3 senza torre visiva."""
    run_id = "run-solotesto01"
    _run_con_documento(dati_rw, fixtures_dir, run_id)
    valutatore = _valutatore(dati_rw)
    esempio = {
        "run_id": run_id,
        "messages": [
            {"role": "system", "content": "istruzioni"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Pagine del documento:"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "<95586 caratteri, sha256:f953a4d79ba3>"},
                    },
                ],
            },
        ],
    }
    messaggi = valutatore._pagine_testuali(esempio)
    assert messaggi is not None
    parti = messaggi[1]["content"]
    # nessuna immagine sopravvive, e il testo della pagina è al suo posto
    assert all(parte["type"] == "text" for parte in parti)
    assert parti[0]["text"] == "Pagine del documento:"
    assert "Studio Tecnico Ing. Bianchi" in parti[1]["text"]
    assert "4.880,00" in parti[1]["text"]
    # il messaggio di sistema non viene toccato da questo passo
    assert messaggi[0]["content"] == "istruzioni"


def test_pagine_testuali_non_indovina_se_i_conti_non_tornano(
    dati_rw: Path, fixtures_dir: Path
) -> None:
    """Due segnaposto per un documento di una pagina: non si accoppiano a caso."""
    run_id = "run-solotesto02"
    _run_con_documento(dati_rw, fixtures_dir, run_id)
    valutatore = _valutatore(dati_rw)
    segnaposto = {"type": "image_url", "image_url": {"url": "<9 caratteri, sha256:abcabcabcabc>"}}
    esempio = {
        "run_id": run_id,
        "messages": [{"role": "user", "content": [dict(segnaposto), dict(segnaposto)]}],
    }
    assert valutatore._pagine_testuali(esempio) is None


# ------------------------------------------------------------------ contratto


def test_il_report_dichiara_modalita_e_prompt_reidratati(client: TestClient) -> None:
    """Chi legge deve sapere *come* è stata fatta la misura, non solo il risultato."""
    admin = accedi(client, "giovanna")
    corpo = client.get("/api/dataset/eval-t3", headers=admin).json()
    assert corpo["modalita_documento"] == "immagini"
    assert corpo["prompt_reidratati"] == 0


def test_il_report_dichiara_la_modalita_testo(
    crea_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_SOLO_TESTO, "1")
    client = crea_client()
    admin = accedi(client, "giovanna")
    corpo = client.get("/api/dataset/eval-t3", headers=admin).json()
    assert corpo["modalita_documento"] == "testo"
