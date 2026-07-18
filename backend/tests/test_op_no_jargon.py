"""AC M3: nessuna stringa tecnica nella UI Operatore.

Il controllo è sul sorgente di ``frontend/src/op`` (ogni parola che
l'operatore può leggere nasce lì o nelle risposte API, verificate in
``test_documents_api``): più severo del grep sul bundle, che conterrebbe
stringhe di librerie terze mai mostrate all'utente.
"""

import re
from pathlib import Path

# "workflow(?!er)": il marchio WORKFLOWER in testata è il nome del prodotto,
# non gergo; "workflow" da solo invece sì.
VIETATE = re.compile(r"workflow(?!er)|json|confidence|bozza", re.IGNORECASE)
CARTELLA_OP = Path(__file__).parents[2] / "frontend" / "src" / "op"


def test_sorgente_operatore_senza_gergo() -> None:
    file_controllati = sorted(CARTELLA_OP.rglob("*.ts*"))
    assert file_controllati, f"cartella UI operatore non trovata: {CARTELLA_OP}"
    for percorso in file_controllati:
        for numero, riga in enumerate(percorso.read_text(encoding="utf-8").splitlines(), 1):
            trovata = VIETATE.search(riga)
            assert not trovata, (
                f"{percorso.name}:{numero} contiene {trovata.group(0)!r}: {riga.strip()!r}"
            )
