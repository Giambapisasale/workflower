"""Base dei tool nativi."""

from pathlib import Path


class ToolError(Exception):
    """Errore d'uso di un tool: torna al modello come risultato, non esplode."""


def percorso_nel_repo(
    data_dir: Path | str,
    path: str,
    estensioni: frozenset[str] | set[str],
    attesi: str,
) -> Path:
    """Il file ``path`` dentro il repo dati, o :class:`ToolError`.

    Il confine è il repo dati: un percorso che ne esce viene rifiutato **prima**
    di toccare il filesystem. Il modello propone il percorso, quindi questa non è
    una validazione di forma — è il perimetro. Condivisa da tutti i tool che
    leggono un documento (``ocr_pdf``, ``leggi_documento``), perché il perimetro
    deve essere lo stesso ovunque: un tool più permissivo dell'altro sarebbe una
    porta di servizio.

    ``attesi`` è la descrizione dei formati per il messaggio d'errore, che il
    modello legge e usa per correggersi (es. ``"pdf/png/jpg"``).
    """
    base = Path(data_dir).resolve()
    file = (base / path).resolve()
    if not file.is_relative_to(base):
        raise ToolError(f"percorso fuori dal repo dati: {path}")
    if file.suffix.lower() not in estensioni:
        raise ToolError(f"formato non supportato: {file.suffix} (attesi {attesi})")
    if not file.is_file():
        raise ToolError(f"documento non trovato: {path}")
    return file
