"""Seed: crea il repo dati ``data/`` (git separato) con schemi, viste e dati d'esempio.

Uso: ``make seed`` (o ``python -m app.seed``). Destinazione: ``$DATA_DIR``
(default ``./data``); la cartella non deve esistere già.
"""

import json
import os
import shutil
import sys
from pathlib import Path

from git import Repo

from app.core.auth import hash_pin
from app.core.dal import DAL, GIT_AUTHOR
from app.models.envelope import Envelope, Meta
from app.seed_data import (
    CANTIERI,
    COMPUTI,
    CRONOPROGRAMMI,
    DDT,
    FATTURE,
    FORNITORI,
    LAVORAZIONI,
    MATERIALI,
    MEZZI,
    POZZETTI,
    RAPPORTINI,
    SAL,
    SCADENZE,
    UTENTI,
)

ASSETS = Path(__file__).parent / "seed_assets"

SKELETON = [
    "entities/cantieri",
    "entities/fornitori",
    "entities/computi",
    "entities/materiali",
    "entities/mezzi",
    "entities/lavorazioni",
    "entities/scadenze",
    "entities/pozzetti",
    "entities/cronoprogrammi",
    "entities/fatture/2026",
    "entities/ddt/2026",
    "entities/sal/2026",
    "entities/rapportini/2026",
    "entities/documenti",
    "blobs/fatture/2026",
    "blobs/caricati",
    "schemas",
    "workflows",
    "traces/2026",
    "golden",
    "dataset",
    "issues",
    "patches",
    "diagnoses",
    "config",
]

README = """# Repo dati Workflower

Fonte di verità del sistema (entità, blob, trace, workflow). Repo git separato
dall'applicazione: ogni mutazione è un commit. Non modificare i file a mano:
le scritture passano dal DAL (backend/app/core/dal.py).
"""

# I log applicativi (logbook) vivono in ``logs/`` dentro la SoT ma sono
# diagnostici, non stato: gitignorati, quindi non producono commit (e non
# rendono "sporco" il repo dati). Il livello persistito sta in ``logs/livello``.
GITIGNORE = "logs/\n"


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
    # Sentinella per le viste su insiemi vuoti (vedi core/views.py): con un
    # delete una cartella entità può restare senza file e ``read_json`` sul
    # glob vuoto fallirebbe; questo ``[]`` le dà zero righe tipizzate.
    (data_dir / "config" / "vuoto.json").write_text("[]", encoding="utf-8")
    (data_dir / "config" / "utenti.json").write_text(
        json.dumps(_utenti_config(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copytree(ASSETS / "workflows", data_dir / "workflows", dirs_exist_ok=True)
    (data_dir / "dataset" / "toolcalls.jsonl").touch()
    (data_dir / "README.md").write_text(README, encoding="utf-8")
    (data_dir / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
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


def _utenti_config() -> list[dict[str, object]]:
    """Gli utenti demo con il PIN sostituito dal suo hash."""
    utenti = []
    for spec in UTENTI:
        record = {k: v for k, v in spec.items() if k != "pin"}
        record["pin_pbkdf2"] = hash_pin(spec["username"], spec["pin"])
        utenti.append(record)
    return utenti


def populate(data_dir: Path) -> None:
    """Inserisce i dati d'esempio via DAL: stato validato, un commit ciascuno."""
    dal = DAL(data_dir)
    per_tipo = (
        ("cantiere", CANTIERI),
        ("fornitore", FORNITORI),
        ("computo", COMPUTI),
        ("materiale", MATERIALI),
        ("mezzo", MEZZI),
        ("lavorazione", LAVORAZIONI),
        ("scadenza", SCADENZE),
        ("fattura", FATTURE),
        ("ddt", DDT),
        ("sal", SAL),
        ("rapportino", RAPPORTINI),
        ("pozzetto", POZZETTI),
        ("cronoprogramma", CRONOPROGRAMMI),
    )
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
    _seed_golden(dal)


def _seed_golden(dal: DAL) -> None:
    """Golden set d'esempio: le due fixture senza ritenuta (regressione di base).

    La fixture CON ritenuta è volutamente esclusa: è lo scenario che l'Improver
    dovrà imparare a gestire (M5), non un caso già validato in passato.
    """
    try:
        from app import fixtures
    except Exception:
        return  # reportlab assente (dipendenza dev): il golden serve a demo/M5
    cartella = dal.data_dir / "blobs" / "golden"
    cartella.mkdir(parents=True, exist_ok=True)
    for spec in fixtures.FIXTURES:
        if spec["ritenuta"] is not None:
            continue
        percorso = cartella / spec["file"]
        fixtures.disegna(percorso, spec)
        dal.commit_paths([percorso], f"golden: allega originale {spec['file']} [seed]")
        dal.crea_golden(
            workflow="carica-fattura",
            version="1.0",
            doc=f"blobs/golden/{spec['file']}",
            entity_tipo="fattura",
            atteso=fixtures.dati_attesi(spec),
            validato_da="seed",
        )


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
    print(f"  computi:   {len(COMPUTI)} (validati)")
    print(f"  fatture:   {len(FATTURE)} (validate)")
    print(f"  ddt:       {len(DDT)} (validate)")
    print(f"  sal:       {len(SAL)} (validati)")
    print(f"  rapportini:{len(RAPPORTINI)} (validati)")
    print(f"  utenti:    {len(UTENTI)} (PIN demo in app/seed_data.py)")


if __name__ == "__main__":
    main()
