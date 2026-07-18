"""Seed: crea il repo dati ``data/`` (git separato) con schemi, viste e dati d'esempio.

Uso: ``make seed`` (o ``python -m app.seed``). Destinazione: ``$DATA_DIR``
(default ``./data``); la cartella non deve esistere già.
"""

import os
import shutil
import sys
from pathlib import Path

from git import Repo

from app.core.dal import DAL, GIT_AUTHOR
from app.models.envelope import Envelope, Meta
from app.seed_data import CANTIERI, FATTURE, FORNITORI

ASSETS = Path(__file__).parent / "seed_assets"

SKELETON = [
    "entities/cantieri",
    "entities/fornitori",
    "entities/fatture/2026",
    "blobs/fatture/2026",
    "schemas",
    "workflows",
    "traces/2026",
    "golden",
    "dataset",
    "issues",
    "config",
]

README = """# Repo dati Workflower

Fonte di verità del sistema (entità, blob, trace, workflow). Repo git separato
dall'applicazione: ogni mutazione è un commit. Non modificare i file a mano:
le scritture passano dal DAL (backend/app/core/dal.py).
"""


def init_data_repo(data_dir: Path) -> None:
    """Crea struttura, schemi, catalogo viste e primo commit del repo dati."""
    data_dir = Path(data_dir)
    for rel in SKELETON:
        cartella = data_dir / rel
        cartella.mkdir(parents=True, exist_ok=True)
        (cartella / ".gitkeep").touch()
    for schema in sorted((ASSETS / "schemas").glob("*.schema.json")):
        shutil.copy(schema, data_dir / "schemas" / schema.name)
    shutil.copy(ASSETS / "config" / "views.sql", data_dir / "config" / "views.sql")
    (data_dir / "dataset" / "toolcalls.jsonl").touch()
    (data_dir / "README.md").write_text(README, encoding="utf-8")
    repo = Repo.init(data_dir)
    with repo.config_writer() as cfg:
        cfg.set_value("user", "name", GIT_AUTHOR.name)
        cfg.set_value("user", "email", GIT_AUTHOR.email)
    repo.git.add(all=True)
    repo.index.commit(
        "init: struttura repo dati, schemi, viste [seed]",
        author=GIT_AUTHOR,
        committer=GIT_AUTHOR,
    )


def populate(data_dir: Path) -> None:
    """Inserisce i dati d'esempio via DAL: stato validato, un commit ciascuno."""
    dal = DAL(data_dir)
    per_tipo = (("cantiere", CANTIERI), ("fornitore", FORNITORI), ("fattura", FATTURE))
    for tipo, items in per_tipo:
        for item in items:
            envelope = Envelope(
                id=item["id"],
                tipo=tipo,
                stato="validato",
                dati=item["dati"],
                meta=Meta(validato_da="seed"),
            )
            dal.create(envelope, run_id="seed")


def run_seed(data_dir: Path) -> None:
    init_data_repo(data_dir)
    populate(data_dir)


def main() -> None:
    data_dir = Path(os.environ.get("DATA_DIR", "./data")).resolve()
    if data_dir.exists() and any(data_dir.iterdir()):
        print(f"ERRORE: {data_dir} esiste già e non è vuota; rimuoverla per rifare il seed.")
        sys.exit(1)
    run_seed(data_dir)
    print(f"Repo dati creato in {data_dir}:")
    print(f"  cantieri:  {len(CANTIERI)}")
    print(f"  fornitori: {len(FORNITORI)}")
    print(f"  fatture:   {len(FATTURE)} (validate)")


if __name__ == "__main__":
    main()
