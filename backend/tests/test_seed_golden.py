"""Il golden set deve nascere anche dove reportlab non c'è (immagine di produzione).

``reportlab`` è una dipendenza di sviluppo: nell'immagine Docker non è installata.
Il seed disegnava i PDF dei casi golden con reportlab e, quando mancava, li saltava
in silenzio — nel container il golden set restava **vuoto** e il replay di una patch
dell'Improver diceva `0/0`, cioè non dimostrava niente. Ora gli originali si copiano
dagli asset versionati.
"""

import builtins
from pathlib import Path

from app.core.golden import carica_golden
from app.seed import run_seed


def _senza_reportlab(monkeypatch) -> None:
    """Rende ``import reportlab`` un ModuleNotFoundError, come in produzione."""
    vero = builtins.__import__

    def finto(nome: str, *resto, **chiavi):
        if nome.split(".")[0] == "reportlab":
            raise ModuleNotFoundError("No module named 'reportlab'")
        return vero(nome, *resto, **chiavi)

    monkeypatch.setattr(builtins, "__import__", finto)


def test_golden_seminato_anche_senza_reportlab(tmp_path: Path, monkeypatch) -> None:
    _senza_reportlab(monkeypatch)
    data_dir = tmp_path / "data"
    run_seed(data_dir)

    casi = carica_golden(data_dir)
    assert len(casi) == 2, "senza casi golden il replay dell'Improver non verifica nulla"
    for caso in casi:
        assert caso.workflow == "carica-fattura"
        assert (data_dir / caso.doc).is_file(), "l'originale deve essere rieseguibile"
        assert caso.atteso["totale"] > 0
        # la fixture CON ritenuta è esclusa di proposito: è ciò che l'Improver impara
        assert not caso.atteso.get("ritenuta_acconto")


def test_seed_crea_la_cartella_degli_scartati(tmp_path: Path) -> None:
    """``scartati/`` sta fuori da ``entities/`` così nessuna vista la vede."""
    data_dir = tmp_path / "data"
    run_seed(data_dir)
    assert (data_dir / "scartati").is_dir()
    assert not (data_dir / "entities" / "scartati").exists()
