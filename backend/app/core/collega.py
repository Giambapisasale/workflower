"""Collegamento righe → voci di computo (Fase 2, M9).

Abbina le righe di una fattura/DDT alle voci del computo del cantiere in modo
deterministico (tool ``cerca_voce_computo``, fuzzy match). Scrive
``voce_computo_id`` sulla bozza — che resta bozza: l'abbinamento è revisionabile
dall'ufficio, non è una validazione. Da qui nasce lo scostamento
previsto/consuntivo, il "confronto computo/consuntivo" richiesto dal cliente.

Consolidamento in tool (§3.6): niente LLM, esito riproducibile.
"""

from typing import Any

from app.core.dal import DAL
from app.core.tools.computo import cerca_voce_computo, voci_cantiere

# Sotto questa somiglianza non si abbina: meglio "non abbinata" che abbinata male.
SOGLIA = 0.45


class Collega:
    def __init__(self, dal: DAL) -> None:
        self.dal = dal

    def abbina(self, tipo: str, entity_id: str) -> dict[str, Any]:
        """Abbina le righe dell'entità alle voci di computo; aggiorna la bozza."""
        envelope = self.dal.read(tipo, entity_id)
        cantiere_id = envelope.dati.get("cantiere_id")
        righe = envelope.dati.get("righe") or []
        if not voci_cantiere(self.dal, cantiere_id):
            return {"abbinate": 0, "totali": len(righe), "senza_computo": True, "dettaglio": []}

        dettaglio: list[dict[str, Any]] = []
        abbinate = 0
        for indice, riga in enumerate(righe):
            descrizione = str(riga.get("descrizione") or "")
            candidati = cerca_voce_computo(self.dal, cantiere_id, descrizione)["risultati"]
            migliore = candidati[0] if candidati else None
            punteggio = migliore["punteggio"] if migliore else 0.0
            voce_id = None
            if migliore and punteggio >= SOGLIA:
                voce_id = migliore["voce_id"]
                riga["voce_computo_id"] = voce_id
                abbinate += 1
            dettaglio.append({"riga": indice, "voce_id": voce_id, "punteggio": punteggio})

        if abbinate:
            self.dal.update(envelope, run_id=envelope.meta.run_id)
        return {"abbinate": abbinate, "totali": len(righe), "dettaglio": dettaglio}
