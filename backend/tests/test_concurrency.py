"""Scritture concorrenti serializzate dalla coda single-writer (AC M1)."""

import threading
from pathlib import Path

from test_dal import commit_count, fattura

from app.core.dal import DAL


def _esegui_in_parallelo(n: int, target) -> list[Exception]:
    barrier = threading.Barrier(n)
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            barrier.wait()
            target(i)
        except Exception as exc:  # noqa: BLE001 — raccolti e asseriti vuoti
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors


def test_create_concorrenti(data_repo: Path) -> None:
    dal = DAL(data_repo)
    before = commit_count(data_repo)
    n = 12

    errors = _esegui_in_parallelo(
        n, lambda i: dal.create(fattura(f"FT-2026-{100 + i:04d}"), run_id=f"run-{i}")
    )

    assert errors == []
    assert len(dal.list_all("fattura")) == n  # tutti i file scritti e validi
    assert commit_count(data_repo) == before + n  # un commit per scrittura, nessuno perso


def test_update_concorrenti_stessa_entita(data_repo: Path) -> None:
    dal = DAL(data_repo)
    dal.create(fattura())
    before = commit_count(data_repo)
    n = 8

    def aggiorna(i: int) -> None:
        importo = 100.0 + i
        dal.update(
            fattura(imponibile=importo, iva=0.0, totale=importo, righe=[
                {"descrizione": "Voce aggiornata", "importo": importo},
            ]),
            run_id=f"run-{i}",
        )

    errors = _esegui_in_parallelo(n, aggiorna)

    assert errors == []
    finale = dal.read("fattura", "FT-2026-0100")
    assert finale.dati["totale"] in {100.0 + i for i in range(n)}  # file integro
    assert commit_count(data_repo) == before + n
