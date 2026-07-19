"""Tool nativi dei workflow: registry degli schemi function-calling + dispatch."""

from typing import Any

from app.core.dal import DAL
from app.core.tools import computo, ocr_pdf, ricerca, salva_bozza
from app.core.tools.base import ToolError

__all__ = ["ToolError", "Toolset"]


class Toolset:
    """I tool disponibili a un run, legati al repo dati del DAL."""

    def __init__(self, dal: DAL) -> None:
        self._registro: dict[str, tuple[dict[str, Any], Any]] = {
            "ocr_pdf": (ocr_pdf.SCHEMA, lambda a: ocr_pdf.esegui(dal.data_dir, **a)),
            "cerca_fornitore": (
                ricerca.SCHEMA_FORNITORE,
                lambda a: ricerca.cerca_fornitore(dal, **a),
            ),
            "cerca_cantiere": (
                ricerca.SCHEMA_CANTIERE,
                lambda a: ricerca.cerca_cantiere(dal, **a),
            ),
            "cerca_voce_computo": (
                computo.SCHEMA,
                lambda a: computo.cerca_voce_computo(dal, **a),
            ),
            "salva_bozza": (salva_bozza.SCHEMA, lambda a: salva_bozza.esegui(dal, **a)),
        }

    def schemi(self, nomi: list[str]) -> list[dict[str, Any]]:
        """Schemi function-calling dei tool richiesti (per la chiamata LLM)."""
        return [self._schema(nome) for nome in nomi]

    def elenco(self) -> list[dict[str, str]]:
        """Nome e descrizione di ogni tool registrato (pagina Skills & Tools)."""
        voci = []
        for nome, (schema, _handler) in self._registro.items():
            funzione = schema.get("function", {})
            voci.append({"name": nome, "descrizione": funzione.get("description", "")})
        return voci

    def esegui(
        self, nome: str, argomenti: dict[str, Any], consentiti: list[str] | None = None
    ) -> Any:
        """Esegue un tool. ``consentiti`` limita ai tool dichiarati dallo step."""
        if consentiti is not None and nome not in consentiti:
            raise ToolError(f"tool non disponibile in questo step: {nome}")
        if nome not in self._registro:
            raise ToolError(f"tool sconosciuto: {nome}")
        _, handler = self._registro[nome]
        try:
            return handler(argomenti)
        except TypeError as exc:
            raise ToolError(f"argomenti non validi per {nome}: {exc}") from exc

    def _schema(self, nome: str) -> dict[str, Any]:
        if nome not in self._registro:
            raise ToolError(f"tool sconosciuto: {nome}")
        return self._registro[nome][0]
