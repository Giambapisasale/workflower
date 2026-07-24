"""Accesso in sola lettura al *proprio* codice sorgente (per il Diagnostico).

Come fa il sistema a "leggere se stesso"? Gli errori nel logbook portano il
**traceback** completo, e un traceback contiene i percorsi e le righe esatte dei
frame che hanno originato l'eccezione. Da lì risaliamo ai file del package
``app`` e ne estraiamo l'intorno della riga incriminata: è il contesto che il
Diagnostico dà all'LLM per capire se il problema sta nel *dato* (skill/tool/
schema, modificabili) o nell'**architettura** (il codice-cornice, sola analisi).

Confinamento: si leggono **solo** file dentro il package ``app``. Un frame che
punta a librerie di terze parti o fuori dall'albero viene ignorato — niente
letture arbitrarie del filesystem.
"""

import re
from pathlib import Path

import app as _app_pkg

# Radice del codice leggibile: la cartella del package ``app`` (…/backend/app).
RADICE_CODICE = Path(_app_pkg.__file__).resolve().parent
# Radice del repo, per mostrare percorsi leggibili (…/backend/app → repo/…).
_REPO_ROOT = RADICE_CODICE.parent.parent

_RIGA_TRACEBACK = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>.+)')

# Fallback quando l'errore non ha un traceback (validazioni, fallimenti di
# dominio): la fase indica i sorgenti più probabilmente coinvolti.
_FILE_PER_FASE: dict[str, tuple[str, ...]] = {
    "gateway": ("core/gateway.py",),
    "runtime": ("core/runtime.py",),
    "dal": ("core/dal.py",),
    "sandbox": ("core/sandbox.py",),
    "toolsmith": ("core/toolsmith.py", "core/pytools.py"),
    "interroga": ("core/interroga.py",),
    "dataset": ("core/dataset.py",),
    "improver": ("core/improver.py",),
    "tool": ("core/tools/base.py",),
    "auth": ("core/auth.py",),
    "api": ("api/deps.py",),
}

MAX_RIGHE_FILE = 220  # oltre, senza una riga a fuoco si tronca


def percorso_leggibile(percorso: Path) -> str:
    """Percorso relativo al repo (``backend/app/...``) quando possibile."""
    percorso = percorso.resolve()
    for base in (_REPO_ROOT, RADICE_CODICE):
        try:
            rel = percorso.relative_to(base)
        except ValueError:
            continue
        return (Path(base.name) / rel).as_posix() if base is RADICE_CODICE else rel.as_posix()
    return percorso.name


def _entro_radice(percorso: Path) -> Path | None:
    """Il percorso risolto se sta dentro il package ``app``, altrimenti ``None``."""
    try:
        risolto = (percorso if percorso.is_absolute() else RADICE_CODICE / percorso).resolve()
    except OSError:
        return None
    try:
        risolto.relative_to(RADICE_CODICE)
    except ValueError:
        return None
    return risolto if risolto.is_file() else None


def frame_da_traceback(traceback: str) -> list[dict[str, object]]:
    """I frame del traceback che cadono nel package ``app``, in ordine.

    L'ultimo è di norma l'origine dell'eccezione. Ogni voce: ``file`` (leggibile),
    ``lineno``, ``funzione``.
    """
    frame: list[dict[str, object]] = []
    for riga in traceback.splitlines():
        match = _RIGA_TRACEBACK.search(riga)
        if not match:
            continue
        risolto = _entro_radice(Path(match.group("file")))
        if risolto is None:
            continue
        frame.append(
            {
                "file": percorso_leggibile(risolto),
                "lineno": int(match.group("line")),
                "funzione": match.group("func").strip(),
            }
        )
    return frame


def estratto(percorso: str | Path, lineno: int | None = None, contesto: int = 30) -> str | None:
    """L'intorno della riga ``lineno`` del file (numerato), o ``None`` se fuori radice.

    Senza ``lineno`` ritorna il file intero (troncato a ``MAX_RIGHE_FILE``). La riga
    a fuoco è marcata con ``»``.
    """
    risolto = _entro_radice(Path(percorso))
    if risolto is None:
        return None
    righe = risolto.read_text(encoding="utf-8", errors="replace").splitlines()
    if lineno is None:
        troncato = righe[:MAX_RIGHE_FILE]
        corpo = "\n".join(f"{i + 1:5d}  {t}" for i, t in enumerate(troncato))
        if len(righe) > MAX_RIGHE_FILE:
            corpo += f"\n… ({len(righe) - MAX_RIGHE_FILE} righe non mostrate)"
        return corpo
    inizio = max(0, lineno - contesto - 1)
    fine = min(len(righe), lineno + contesto)
    fuori = []
    for i in range(inizio, fine):
        marca = "»" if (i + 1) == lineno else " "
        fuori.append(f"{marca}{i + 1:5d}  {righe[i]}")
    return "\n".join(fuori)


def sorgenti_per_voce(voce: dict[str, object], max_file: int = 4) -> list[dict[str, object]]:
    """I sorgenti coinvolti da una voce di log: dal traceback, o dalla fase.

    Ritorna una lista di ``{file, lineno, estratto}`` (dedup per file), pronta come
    contesto per l'LLM di analisi.
    """
    sorgenti: list[dict[str, object]] = []
    visti: set[str] = set()

    eccezione = voce.get("eccezione")
    if isinstance(eccezione, str) and eccezione:
        # dai frame più vicini all'origine (in coda) verso l'alto
        for frame in reversed(frame_da_traceback(eccezione)):
            file = str(frame["file"])
            if file in visti:
                continue
            testo = estratto(file, int(frame["lineno"]))
            if testo is None:
                continue
            visti.add(file)
            sorgenti.append({"file": file, "lineno": frame["lineno"], "estratto": testo})
            if len(sorgenti) >= max_file:
                return sorgenti

    if not sorgenti:
        for rel in _FILE_PER_FASE.get(str(voce.get("fase", "")), ()):  # fallback per fase
            testo = estratto(rel)
            if testo is None:
                continue
            sorgenti.append({"file": percorso_leggibile(RADICE_CODICE / rel), "estratto": testo})
    return sorgenti
