"""Base dei tool nativi."""


class ToolError(Exception):
    """Errore d'uso di un tool: torna al modello come risultato, non esplode."""
