#!/usr/bin/env python
"""Collega i lavoratori dei rapportini già estratti all'anagrafica dipendenti.

Migrazione una-volta-sola. I rapportini estratti prima che la skill imparasse a
usare ``cerca_dipendente`` hanno ``dipendente_id`` sempre ``null``, e questo si
vede in due punti: la tariffa della manodopera arriva dal foglio invece che dal
profilo (``v_rapportini_righe.tariffa_applicata``), e ogni domanda su una persona
("quante ore ha fatto Torrisi?") non trova niente perché la join non aggancia.

Riesegue ``cerca_dipendente`` sui nominativi già trascritti — nessun LLM, nessun
costo, esito riproducibile — e scrive ``dipendente_id`` dove il punteggio arriva
alla stessa soglia che usa la skill. Non tocca mai il nominativo né il
``costo_orario``: restano ciò che il documento dice.

Tocca anche i **casi golden** dei rapportini. Il loro ``atteso`` è la trascrizione
validata dall'ufficio: lasciarlo col vecchio ``null`` significherebbe conservare
come "giusto" ciò che stiamo correggendo, e al primo replay l'Improver leggerebbe
il collegamento nuovo come uno scostamento dal golden — la rete di sicurezza
suonerebbe contro la correzione.

Idempotente: una riga già collegata non viene guardata. In sola lettura per
default; scrive (e committa, una revisione per file) solo con ``--applica``.

    python scripts/collega_dipendenti.py            # cosa farebbe
    python scripts/collega_dipendenti.py --applica   # lo fa
"""

import argparse
import json
import os
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "backend"))

from app.core.dal import DAL  # noqa: E402
from app.core.tools.ricerca import cerca_dipendente  # noqa: E402

# La stessa di data/workflows/carica-rapportino/skills/estrazione-rapportino.md:
# sotto questa somiglianza non si collega. Un collegamento sbagliato non dà
# errore, sposta ore e costi su un'altra persona.
SOGLIA = 0.75


def risolvi(dal: DAL, nominativo: str | None) -> tuple[str | None, float]:
    if not nominativo:
        return None, 0.0
    risultati = cerca_dipendente(dal, nominativo)["risultati"]
    migliore = risultati[0] if risultati else None
    if not migliore or migliore["punteggio"] < SOGLIA:
        return None, migliore["punteggio"] if migliore else 0.0
    return migliore["id"], migliore["punteggio"]


def _collega_righe(dal: DAL, etichetta: str, righe: list[dict]) -> int:
    """Riempie ``dipendente_id`` dove si può; ritorna quante righe ha collegato."""
    collegate = 0
    for riga in righe:
        if riga.get("dipendente_id"):
            continue
        nominativo = riga.get("nominativo")
        dipendente_id, punteggio = risolvi(dal, nominativo)
        if dipendente_id is None:
            print(f"  -    {etichetta} {str(nominativo):24} {punteggio:.2f}")
            continue
        riga["dipendente_id"] = dipendente_id
        collegate += 1
        print(f"  ->   {etichetta} {str(nominativo):24} {punteggio:.2f} {dipendente_id}")
    return collegate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--applica", action="store_true", help="scrive e committa")
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "./data"))
    argomenti = parser.parse_args()

    dal = DAL(Path(argomenti.data_dir).resolve())
    collegate = 0

    print("rapportini")
    for envelope in dal.list_all("rapportino"):
        quante = _collega_righe(dal, envelope.id, envelope.dati.get("righe") or [])
        collegate += quante
        if quante and argomenti.applica:
            dal.update(envelope, run_id="collega-dipendenti")

    print("\ncasi golden")
    for percorso in sorted((dal.data_dir / "golden").glob("*.json")):
        caso = json.loads(percorso.read_text(encoding="utf-8"))
        if caso.get("entity_tipo") != "rapportino":
            continue
        righe = (caso.get("atteso") or {}).get("righe") or []
        quante = _collega_righe(dal, caso["id"], righe)
        collegate += quante
        if quante and argomenti.applica:
            percorso.write_text(
                json.dumps(caso, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            dal.commit_paths(
                [percorso], f"golden {caso['id']}: collega i dipendenti [collega-dipendenti]"
            )

    print(f"\ncollegate {collegate} righe in tutto")
    if collegate and not argomenti.applica:
        print("(sola lettura: rilancia con --applica per scrivere)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
