"""Migrazione offline: archivio legacy → golden tool+risultati dell'agente.

Non legge né ripubblica le implementazioni storiche: usa soltanto il testo delle
domande e il catalogo semantico dell'agente. Le voci prodotte sono approvate come
baseline di migrazione e restano revisionabili dall'ufficio nel repo dati.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.core.agente_dati import RegistryToolDati
from app.core.dal import DAL
from app.core.golden import casi_domanda
from app.core.golden_agente import impronta_risultato


def _tool(domanda: str) -> str:
    testo = domanda.lower()
    if any(x in testo for x in ("ddt", "consegn", "materiale consegnato")):
        return "analizza_ddt"
    if any(x in testo for x in ("pagat", "scadenz")):
        return "pagamenti_e_scadenze"
    if any(x in testo for x in ("pozzett", "manufatt")):
        return "pozzetti_e_scadenze"
    if any(x in testo for x in ("sal", "avanzamento", "cronoprogramma", "ritardo")):
        return "sal_e_avanzamento"
    if any(x in testo for x in ("mezzo", "escavat", "manutenz")):
        return "mezzi_tco"
    if any(x in testo for x in ("dipendent", "lavorator", "ore", "manodopera", "mansione")):
        return "riepilogo_ore_manodopera"
    if any(x in testo for x in ("fornitor", "partita iva")):
        return "cerca_fornitori"
    if any(x in testo for x in ("computo", "scostamento", "preventivo", "budget", "margine")):
        return "analizza_scostamenti"
    if any(x in testo for x in ("materiali", "lavorazioni", "prezzario", "listino")):
        return "materiali_e_lavorazioni"
    if any(x in testo for x in ("fattur", "ritenuta", "iva", "spes", "costo")):
        return "riepilogo_costi" if any(x in testo for x in ("spes", "costo")) else "analizza_fatture"
    return "cerca_cantieri"


def _args(spec: dict) -> dict:
    return {nome: None for nome in (spec.get("parameters", {}).get("properties") or {})}


def migra(data_dir: Path) -> int:
    dal = DAL(data_dir)
    registry = RegistryToolDati(data_dir)
    cartella = data_dir / "agent_goldens"
    aggiornamenti: dict[Path, str] = {}
    for indice, caso in enumerate(casi_domanda(data_dir), 1):
        nome = _tool(caso.domanda or "")
        spec = registry._tools[nome]
        argomenti = _args(spec)
        risultato = registry.esegui(nome, argomenti, "admin", [])
        voce = {
            "id": f"AGOLD-{indice:04d}",
            "stato": "approvato",
            "legacy_golden_id": caso.id,
            "question": caso.domanda,
            "context": [],
            "role": "admin",
            "cantieri": [],
            "tool_calls": [
                {"name": nome, "arguments": argomenti, "result_hash": impronta_risultato(risultato)}
            ],
        }
        percorso = cartella / f"{voce['id']}.json"
        testo = json.dumps(voce, ensure_ascii=False, indent=2) + "\n"
        if not percorso.is_file() or percorso.read_text(encoding="utf-8") != testo:
            aggiornamenti[percorso] = testo
    if aggiornamenti:
        dal.commit_updates(aggiornamenti, message="agente dati: migra golden tool-first")
    return len(aggiornamenti)


def main() -> None:
    data_dir = Path(os.environ.get("DATA_DIR", "./data")).resolve()
    print(f"golden agente creati: {migra(data_dir)}")


if __name__ == "__main__":
    main()
