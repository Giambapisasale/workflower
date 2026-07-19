"""Registry dei tool Python consolidati (Fase 3, M15).

Terza forma di consolidamento del §3.6 — dopo la **vista** ``v_*`` e la **macro**
parametrica ``t_*`` viene il **tool Python** ``data/tools/<nome>/``: codice
deterministico che l'SQL non cattura (calcoli, normalizzazioni). Come le altre
due forme è **dato, non codice del runtime**:

* la fonte di verità è il ledger ``data/dataset/pytools.jsonl`` (metadati: nome,
  ciclo di vita, schema function-calling, casi di test, provenienza);
* il **sorgente** vive in ``data/tools/<nome>/tool.py`` — è un dato versionato,
  approvato dall'umano, **mai importato in-process**: chi lo esegue passa dalla
  sandbox (M14).

Questo modulo è la parte di sola lettura/preparazione (gemella di
``consolida.py``): scopre i tool posati in ``data/tools/`` e valida i metadati.
La scrittura (ledger + sorgente + commit) e la rete di sicurezza che esegue i
test in sandbox prima di committare sono del DAL (single-writer).
"""

import json
import re
from pathlib import Path
from typing import Any

LEDGER = "pytools.jsonl"

# Il ciclo di vita di un tool consolidato. Solo ``consolidata`` è instradabile a
# runtime; ``deprecata`` resta nel registro ma non è invocabile (fallback LLM).
CICLO_ESPLORATIVA = "esplorativa"
CICLO_CANDIDATA = "candidata"
CICLO_CONSOLIDATA = "consolidata"
CICLO_DEPRECATA = "deprecata"
CICLI = (CICLO_ESPLORATIVA, CICLO_CANDIDATA, CICLO_CONSOLIDATA, CICLO_DEPRECATA)

# Nome del tool: stesso identificatore sano di viste e macro (minuscole, cifre,
# underscore, iniziale alfabetica, 3–41 caratteri). Vincola anche il nome della
# cartella sorgente, quindi è la barriera contro path traversal via ``nome``.
NOME_PYTOOL = re.compile(r"^[a-z][a-z0-9_]{2,40}$")


class PyToolError(Exception):
    """Metadati di un tool Python non validi: proposta rifiutata prima del commit."""


def percorso_sorgente(data_dir: Path | str, nome: str) -> Path:
    """Percorso del sorgente del tool ``nome`` (``data/tools/<nome>/tool.py``)."""
    return Path(data_dir) / "tools" / nome / "tool.py"


def _voci_ledger(percorso: Path) -> list[dict[str, Any]]:
    """Le righe del ledger JSONL come dict (righe vuote/corrotte ignorate)."""
    if not percorso.is_file():
        return []
    voci: list[dict[str, Any]] = []
    for riga in percorso.read_text(encoding="utf-8").splitlines():
        if not riga.strip():
            continue
        try:
            voci.append(json.loads(riga))
        except ValueError:
            continue
    return voci


def leggi_pytools(data_dir: Path | str) -> list[dict[str, Any]]:
    """Il registro dei tool Python consolidati (solo metadati, senza sorgente)."""
    return _voci_ledger(Path(data_dir) / "dataset" / LEDGER)


def carica_pytools(data_dir: Path | str) -> list[dict[str, Any]]:
    """I tool consolidati pronti al caricamento: metadati + ``codice`` dal file.

    È ciò che il ``Toolset`` legge all'avvio di un run. **Difensiva per
    costruzione**: una riga senza nome valido, senza schema o senza un sorgente
    leggibile viene **saltata**, non fa esplodere il caricamento. Così una
    rimozione a metà, un file mancante o un ledger svuotato non spengono il
    runtime — al più un tool in meno, mai un crash.
    """
    base = Path(data_dir)
    pronti: list[dict[str, Any]] = []
    for voce in leggi_pytools(base):
        nome = voce.get("nome")
        if not isinstance(nome, str) or not NOME_PYTOOL.match(nome):
            continue
        if not isinstance(voce.get("schema"), dict):
            continue
        sorgente = percorso_sorgente(base, nome)
        if not sorgente.is_file():
            continue
        try:
            codice = sorgente.read_text(encoding="utf-8")
        except OSError:
            continue
        ciclo = voce.get("ciclo")
        pronti.append(
            {
                **voce,
                "ciclo": ciclo if ciclo in CICLI else CICLO_CONSOLIDATA,
                "codice": codice,
            }
        )
    return pronti


def prepara_pytool(
    nome: str, codice: str, schema: dict[str, Any], test: list[dict[str, Any]]
) -> dict[str, Any]:
    """Valida i metadati di un tool Python e li normalizza; non scrive nulla.

    Gemella di ``consolida.prepara``/``prepara_tool``: qui stanno i controlli di
    forma (nome, schema function-calling coerente, casi di test ben formati). La
    *validità del comportamento* — che il codice giri e i test passino — è
    garantita a valle dalla rete di sicurezza del DAL che li esegue in sandbox.
    """
    if not isinstance(nome, str) or not NOME_PYTOOL.match(nome):
        raise PyToolError(
            "nome non valido: usa lettere minuscole, numeri e underscore "
            "(3–41 caratteri, iniziale alfabetica)"
        )
    if not isinstance(codice, str) or "def esegui" not in codice:
        raise PyToolError("il sorgente deve definire una funzione «esegui»")
    if not isinstance(schema, dict):
        raise PyToolError("schema mancante o non valido")
    funzione = schema.get("function")
    if not isinstance(funzione, dict) or funzione.get("name") != nome:
        raise PyToolError(
            "lo schema function-calling deve avere function.name uguale al nome del tool"
        )
    if not isinstance(funzione.get("parameters"), dict):
        raise PyToolError("lo schema deve descrivere i parametri (function.parameters)")
    if not isinstance(test, list) or not test:
        raise PyToolError("servono uno o più casi di test (dai trace validati)")
    for caso in test:
        if not isinstance(caso, dict) or not isinstance(caso.get("argomenti"), dict):
            raise PyToolError("ogni caso di test è {argomenti: {...}, atteso: ...}")
        if "atteso" not in caso:
            raise PyToolError("ogni caso di test deve dichiarare il risultato «atteso»")
    return {"nome": nome, "codice": codice, "schema": schema, "test": test}
