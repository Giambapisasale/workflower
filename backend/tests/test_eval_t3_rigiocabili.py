"""L'harness T3 non deve mai rispondere 500, e non deve mentire sulla copertura.

Scoperto usando la pagina che prima non c'era: ``GET /api/dataset/eval-t3`` andava in
**500**. La causa è strutturale, non un caso limite — il trace **oscura** le stringhe
lunghe (``<184320 caratteri, sha256:…>``), e rigiocare un esempio con un ``image_url``
finto lo fa rifiutare dal provider con un 400.

La distinzione che rende la misura possibile: un **testo** oscurato è un payload
valido (inutile, ma valido), un'**immagine** oscurata no. Le immagini si ricostruiscono
rifacendo l'OCR dell'originale; i prompt troncati si dichiarano, perché abbassano
l'accuratezza assoluta di *entrambi* i tier — il confronto resta onesto, il numero va
letto sapendolo.
"""

from pathlib import Path

from aiuti import accedi
from fake_llm import FakeCompleter
from fastapi.testclient import TestClient

from app.core.dal import DAL
from app.core.eval_t3 import (
    EvalT3,
    _immagini_oscurate,
    _oscurato,
    _prompt_troncati,
)
from app.core.gateway import Gateway

SEGNAPOSTO = "<184320 caratteri, sha256:ab12cd34ef56>"


def _messaggi(*, immagine: str, sistema: str) -> list[dict]:
    return [
        {"role": "system", "content": sistema},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "leggi le pagine"},
                {"type": "image_url", "image_url": {"url": immagine}},
            ],
        },
    ]


# ------------------------------------------------------------- riconoscimento


def test_riconosce_il_segnaposto_del_trace() -> None:
    assert _oscurato(SEGNAPOSTO)
    assert _oscurato({"image_url": {"url": "<12 caratteri, sha256:deadbeef>"}})
    assert _oscurato([{"a": "ok"}, {"b": "<9 caratteri, sha256:abc123>"}])
    # nessun falso positivo su testo che somiglia ma non è il segnaposto
    assert not _oscurato("data:image/png;base64,iVBORw0KGgo=")
    assert not _oscurato("<qualcosa fra parentesi angolari>")
    assert not _oscurato("184320 caratteri, sha256:ab12cd34ef56")
    assert not _oscurato(None)


def test_distingue_immagini_da_testo() -> None:
    """È la distinzione che separa "non si può misurare" da "si misura con un limite"."""
    solo_testo = _messaggi(immagine="data:image/png;base64,iVBORw0", sistema=SEGNAPOSTO)
    assert _immagini_oscurate(solo_testo) == []
    assert _prompt_troncati(solo_testo) == 1

    solo_immagine = _messaggi(immagine=SEGNAPOSTO, sistema="istruzioni vere")
    assert len(_immagini_oscurate(solo_immagine)) == 1
    assert _prompt_troncati(solo_immagine) == 0


def test_prompt_troncati_conta_anche_le_parti_di_testo() -> None:
    messaggi = [
        {"role": "system", "content": SEGNAPOSTO},
        {"role": "user", "content": [{"type": "text", "text": SEGNAPOSTO}]},
    ]
    assert _prompt_troncati(messaggi) == 2


# --------------------------------------------------------------- ricostruzione


def test_reidratazione_rinuncia_senza_originale(dati_rw: Path) -> None:
    """Senza il documento non si indovina: meglio un esempio in meno di un contesto finto."""
    ev = EvalT3(DAL(dati_rw), Gateway(completer=FakeCompleter(dati_rw), attesa_retry=0))
    esempio = {"run_id": "run-inesistente", "messages": _messaggi(immagine=SEGNAPOSTO, sistema="x")}
    assert ev._reidrata(esempio) is None
    assert ev._reidrata({"messages": esempio["messages"]}) is None  # senza run_id


# ------------------------------------------------------------------- contratto


def test_eval_t3_risponde_sempre_e_dichiara_i_limiti(client: TestClient) -> None:
    """Mai 500, e sempre con i contatori che dicono quanto copre la misura."""
    admin = accedi(client, "giovanna")
    risposta = client.get("/api/dataset/eval-t3", headers=admin)
    assert risposta.status_code == 200, risposta.text
    corpo = risposta.json()
    for chiave in (
        "esempi",
        "non_rigiocabili",
        "prompt_troncati",
        "t3_configurato",
        "workflow",
        "soglia",
    ):
        assert chiave in corpo, f"il report deve dichiarare {chiave}"
    # sul solo seed non ci sono run: nessun esempio, e nessun errore
    assert corpo["esempi"] == 0
    assert corpo["workflow"] == {}
    # senza LLM_T3_MODEL il gateway ricade su T1: il report non deve tacerlo
    assert corpo["t3_configurato"] is False


def test_eval_t3_solo_admin(client: TestClient) -> None:
    op = accedi(client, "salvo")
    assert client.get("/api/dataset/eval-t3", headers=op).status_code == 403
    assert client.get("/api/dataset/eval-t3").status_code == 401
