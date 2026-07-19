"""Tool dei workflow: registry degli schemi function-calling + dispatch.

Due origini, una sola cornice. I tool **nativi** sono codice del runtime, con
firma stabile. I tool **consolidati** (Fase 3, M15) sono *dato*: sorgente in
``data/tools/<nome>/``, scoperti a ogni run dal loader e invocati **solo tramite
la sandbox** (M14), mai importati in-process. Aggiungere un tool consolidato non
tocca né questa classe né i tool nativi: è una riga nel ledger + un file.
"""

from typing import Any

from app.core.dal import DAL
from app.core.pytools import CICLO_CONSOLIDATA, carica_pytools
from app.core.sandbox import esegui_in_sandbox
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
        # Ciclo di vita e origine per la pagina Skills & Tools. ``_schemi_noti``
        # tiene lo schema anche dei consolidati non invocabili (es. deprecati),
        # che non stanno in ``_registro`` ma vanno comunque elencati.
        self._ciclo: dict[str, str] = dict.fromkeys(self._registro, CICLO_CONSOLIDATA)
        self._origine: dict[str, str] = dict.fromkeys(self._registro, "nativa")
        self._schemi_noti: dict[str, dict[str, Any]] = {}
        self._carica_consolidati(dal)

    def _carica_consolidati(self, dal: DAL) -> None:
        """Registra i tool Python consolidati (dato) accanto ai nativi.

        Solo i tool ``consolidata`` diventano invocabili: gli altri stati del
        ciclo compaiono nel registro ma restano non instradabili (fallback LLM).
        I nativi hanno la precedenza: un consolidato omonimo non li sovrascrive.
        Il loader è difensivo, quindi un ledger svuotato non spegne nulla.
        """
        for voce in carica_pytools(dal.data_dir):
            nome = voce["nome"]
            if nome in self._registro and self._origine.get(nome) == "nativa":
                continue
            self._ciclo[nome] = voce["ciclo"]
            self._origine[nome] = "pytool"
            self._schemi_noti[nome] = voce["schema"]
            if voce["ciclo"] == CICLO_CONSOLIDATA:
                codice = voce["codice"]
                self._registro[nome] = (
                    voce["schema"],
                    lambda a, _codice=codice: esegui_in_sandbox(_codice, a),
                )

    def schemi(self, nomi: list[str]) -> list[dict[str, Any]]:
        """Schemi function-calling dei tool richiesti (per la chiamata LLM)."""
        return [self._schema(nome) for nome in nomi]

    def elenco(self) -> list[dict[str, str]]:
        """Nome, descrizione, stato di ciclo e origine di ogni tool (pagina Skills & Tools).

        Include i consolidati non invocabili (es. ``deprecata``): sono nel
        registro come dato anche quando il runtime non li instrada.
        """
        voci = []
        nomi = list(self._registro)
        for nome in self._ciclo:
            if nome not in self._registro:
                nomi.append(nome)
        for nome in nomi:
            schema = self._schema_noto(nome)
            funzione = schema.get("function", {})
            voci.append(
                {
                    "name": nome,
                    "descrizione": funzione.get("description", ""),
                    "ciclo": self._ciclo.get(nome, CICLO_CONSOLIDATA),
                    "origine": self._origine.get(nome, "nativa"),
                }
            )
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

    def _schema_noto(self, nome: str) -> dict[str, Any]:
        """Lo schema di un tool anche se non invocabile (per l'elenco/registro)."""
        if nome in self._registro:
            return self._registro[nome][0]
        return self._schemi_noti.get(nome, {})
