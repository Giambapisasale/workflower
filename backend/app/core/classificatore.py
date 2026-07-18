"""Classificatore documenti (Fase 2, M7): instrada un upload al workflow giusto.

È la "classificazione documenti (T2)" di §3.1: prima di estrarre bisogna sapere
*che documento è*. Il catalogo dei tipi è auto-scoperto dai manifest che dichiarano
un blocco ``ingest`` — aggiungere un tipo documento (nuovo manifest) lo rende
classificabile senza toccare questo codice (invariante di Fase 2).

Contratto verso il chiamante: ``workflow_per`` non solleva mai. Qualunque cosa vada
storta (modello incerto, rete, documento illeggibile) instrada sul ``fallback`` del
manifest: l'operatore non riceve mai un errore bloccante (§3.4).
"""

import logging
from typing import Any

import yaml

from app.core.dal import DAL
from app.core.gateway import Gateway, estrai_json
from app.core.tools import ocr_pdf

logger = logging.getLogger("workflower.classificatore")

FALLBACK_PREDEFINITO = "carica-fattura"


class Classificatore:
    def __init__(self, dal: DAL, gateway: Gateway) -> None:
        self.dal = dal
        self.data_dir = dal.data_dir
        self.gateway = gateway
        self.wf_dir = self.data_dir / "workflows" / "classifica-documento"

    # ------------------------------------------------------------- pubblico

    def catalogo(self) -> list[dict[str, str]]:
        """I workflow d'ingresso disponibili, dai manifest con blocco ``ingest``."""
        voci: list[dict[str, str]] = []
        for manifest_path in sorted((self.data_dir / "workflows").glob("*/manifest.yaml")):
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            ingest = manifest.get("ingest")
            if not isinstance(ingest, dict) or not ingest.get("label"):
                continue
            voci.append(
                {
                    "label": str(ingest["label"]).strip().lower(),
                    "descrizione": str(ingest.get("descrizione", "")).strip(),
                    "workflow": str(manifest.get("name", manifest_path.parent.name)),
                }
            )
        return voci

    def workflow_per(self, doc: str) -> str:
        """Il workflow d'ingresso adatto al documento ``doc`` (mai un'eccezione)."""
        catalogo = self.catalogo()
        default = self._fallback(catalogo)
        if len(catalogo) <= 1:
            return default  # un solo tipo: niente da classificare
        try:
            label = self._chiedi(catalogo, doc)
        except Exception:
            logger.exception("classificazione fallita per %s: instrado sul fallback", doc)
            return default
        for voce in catalogo:
            if voce["label"] == label:
                return voce["workflow"]
        return default

    # ------------------------------------------------------------- interni

    def _fallback(self, catalogo: list[dict[str, str]]) -> str:
        manifest = self._manifest()
        candidato = manifest.get("fallback") if manifest else None
        if candidato:
            return str(candidato)
        return catalogo[0]["workflow"] if catalogo else FALLBACK_PREDEFINITO

    def _chiedi(self, catalogo: list[dict[str, str]], doc: str) -> str | None:
        manifest = self._manifest()
        skill = (self.wf_dir / manifest["skill"]).read_text(encoding="utf-8")
        skill = skill.replace("{catalogo}", self._catalogo_testo(catalogo))
        immagini = ocr_pdf.esegui(self.data_dir, doc).get("immagini_png_base64") or []
        parti: list[dict[str, Any]] = [
            {"type": "text", "text": f"Documento da classificare: {doc}"}
        ]
        parti += [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}}
            for img in immagini
        ]
        risposta = self.gateway.complete(
            tier=manifest.get("tier", "T2"),
            messages=[
                {"role": "system", "content": skill},
                {"role": "user", "content": parti},
            ],
        )
        dato = estrai_json(risposta.text or "")
        tipo = str(dato.get("tipo", "")).strip().lower() if isinstance(dato, dict) else ""
        return tipo or None

    @staticmethod
    def _catalogo_testo(catalogo: list[dict[str, str]]) -> str:
        return "\n".join(f"- `{v['label']}`: {v['descrizione']}" for v in catalogo)

    def _manifest(self) -> dict[str, Any]:
        percorso = self.wf_dir / "manifest.yaml"
        if not percorso.is_file():
            return {}
        return yaml.safe_load(percorso.read_text(encoding="utf-8")) or {}
