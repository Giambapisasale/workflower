"""Data Access Layer: ogni scrittura su ``data/`` passa da qui (piano §3.1).

Coda single-writer: un unico lock serializza scrittura file + commit git,
perché ogni mutazione produce un commit sullo stesso repo dati e l'indice
git non tollera scritture concorrenti. La granularità per cantiere diventa
utile solo quando i commit saranno raggruppabili; a questa scala non serve.
"""

import json
import re
import threading
from pathlib import Path
from typing import Any

from git import Actor, Repo
from jsonschema import Draft202012Validator, FormatChecker

from app.models.envelope import Envelope, now_iso
from app.models.issue import Issue

GIT_AUTHOR = Actor("Workflower", "bot@workflower.local")

# Registry dei tipi entità: cartella, formato id, partizione per anno e le
# righe del riepilogo che l'operatore vede (etichetta + campo + tipo).
# Nuova entità = una riga qui + schema in data/schemas/<tipo>.schema.json:
# così il riepilogo si mostra da sé, senza toccare l'API né la UI.
# Tipi di riga: "testo"/"euro"/"percento"/"data" (la UI li formatta),
# "fornitore"/"cantiere" (rimando risolto nel nome) e "conteggio" (n. righe).
ENTITY_TYPES: dict[str, dict[str, Any]] = {
    "cantiere": {
        "dir": "cantieri",
        "id": re.compile(r"^CNT-\d{3,}$"),
        "per_anno": False,
        "fmt": lambda anno, n: f"CNT-{n:03d}",
    },
    "fornitore": {
        "dir": "fornitori",
        "id": re.compile(r"^FRN-\d{3,}$"),
        "per_anno": False,
        "fmt": lambda anno, n: f"FRN-{n:03d}",
    },
    "computo": {
        "dir": "computi",
        "id": re.compile(r"^CMP-\d{3,}$"),
        "per_anno": False,
        "fmt": lambda anno, n: f"CMP-{n:03d}",
    },
    "fattura": {
        "dir": "fatture",
        "id": re.compile(r"^FT-\d{4}-\d{4,}$"),
        "per_anno": True,
        "fmt": lambda anno, n: f"FT-{anno}-{n:04d}",
        "riepilogo": [
            {"etichetta": "Ditta", "campo": "fornitore_id", "tipo": "fornitore"},
            {"etichetta": "Importo", "campo": "totale", "tipo": "euro"},
            {"etichetta": "Cantiere", "campo": "cantiere_id", "tipo": "cantiere"},
        ],
    },
    "ddt": {
        "dir": "ddt",
        "id": re.compile(r"^DDT-\d{4}-\d{4,}$"),
        "per_anno": True,
        "fmt": lambda anno, n: f"DDT-{anno}-{n:04d}",
        "riepilogo": [
            {"etichetta": "Ditta", "campo": "fornitore_id", "tipo": "fornitore"},
            {"etichetta": "Cantiere", "campo": "cantiere_id", "tipo": "cantiere"},
        ],
    },
    "sal": {
        "dir": "sal",
        "id": re.compile(r"^SAL-\d{4}-\d{4,}$"),
        "per_anno": True,
        "fmt": lambda anno, n: f"SAL-{anno}-{n:04d}",
        "riepilogo": [
            {"etichetta": "Avanzamento", "campo": "percentuale_avanzamento", "tipo": "percento"},
            {"etichetta": "Lavori fatti finora", "campo": "importo_progressivo", "tipo": "euro"},
            {"etichetta": "Importo del contratto", "campo": "importo_lavori", "tipo": "euro"},
            {"etichetta": "Cantiere", "campo": "cantiere_id", "tipo": "cantiere"},
        ],
    },
    "rapportino": {
        "dir": "rapportini",
        "id": re.compile(r"^RAP-\d{4}-\d{4,}$"),
        "per_anno": True,
        "fmt": lambda anno, n: f"RAP-{anno}-{n:04d}",
        "riepilogo": [
            {"etichetta": "Giorno", "campo": "data", "tipo": "data"},
            {"etichetta": "Persone in cantiere", "campo": "righe", "tipo": "conteggio"},
            {"etichetta": "Cantiere", "campo": "cantiere_id", "tipo": "cantiere"},
        ],
    },
    "documento": {
        "dir": "documenti",
        "id": re.compile(r"^DOC-\d{4}-\d{4,}$"),
        "per_anno": True,
        "fmt": lambda anno, n: f"DOC-{anno}-{n:04d}",
    },
}


# Entità prodotte dai workflow d'ingresso (estratte da un documento, poi validate).
# Le anagrafiche (cantiere, fornitore, computo) non passano da qui.
TIPI_INGRESSO = ("fattura", "ddt", "sal", "rapportino")


def tipo_da_id(entity_id: str | None) -> str | None:
    """Il tipo entità dedotto dal formato dell'id (es. ``FT-…`` → ``fattura``)."""
    if not entity_id:
        return None
    for tipo, spec in ENTITY_TYPES.items():
        if spec["id"].fullmatch(entity_id):
            return tipo
    return None


class DalError(Exception):
    """Errore generico del DAL."""


class UnknownTypeError(DalError):
    """Tipo entità non presente nel registry."""


class InvalidIdError(DalError):
    """Id non conforme al formato del tipo (protegge anche i path)."""


class NotFoundError(DalError):
    """Entità inesistente."""


class AlreadyExistsError(DalError):
    """Creazione di un id già presente."""


class SchemaValidationError(DalError):
    """I ``dati`` non rispettano lo schema JSON del tipo."""

    def __init__(self, tipo: str, entity_id: str, errors: list[str]) -> None:
        self.errors = errors
        dettaglio = "; ".join(errors)
        super().__init__(f"{tipo} {entity_id}: dati non conformi allo schema: {dettaglio}")


class DAL:
    """CRUD degli envelope entità: validazione schema, lock, git auto-commit."""

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir).resolve()
        if not (self.data_dir / ".git").is_dir():
            raise DalError(f"{self.data_dir} non è un repo dati: eseguire `make seed`")
        self.repo = Repo(self.data_dir)
        self._write_lock = threading.Lock()

    # ------------------------------------------------------------ letture

    def read(self, tipo: str, entity_id: str) -> Envelope:
        path = self._path(tipo, entity_id)
        if not path.is_file():
            raise NotFoundError(f"{tipo} {entity_id} non trovato")
        return Envelope.model_validate_json(path.read_text(encoding="utf-8"))

    def list_all(self, tipo: str) -> list[Envelope]:
        spec = self._spec(tipo)
        base = self.data_dir / "entities" / spec["dir"]
        pattern = "*/*.json" if spec["per_anno"] else "*.json"
        return [
            Envelope.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(base.glob(pattern))
        ]

    def prossimo_id(self, tipo: str, anno: int | None = None) -> str:
        """Primo id libero del tipo (per anno, se il tipo è partizionato).

        L'allocazione non riserva nulla: chi crea deve gestire
        ``AlreadyExistsError`` e riprovare (vedi tool ``salva_bozza``).
        """
        spec = self._spec(tipo)
        base = self.data_dir / "entities" / spec["dir"]
        if spec["per_anno"]:
            if anno is None:
                raise DalError(f"anno obbligatorio per il tipo {tipo}")
            base = base / str(anno)
        progressivi = [0]
        for percorso in base.glob("*.json"):
            coda = percorso.stem.rsplit("-", 1)[-1]
            if coda.isdigit():
                progressivi.append(int(coda))
        return spec["fmt"](anno, max(progressivi) + 1)

    # ---------------------------------------------------------- scritture

    def create(self, envelope: Envelope, run_id: str | None = None) -> Envelope:
        path = self._path(envelope.tipo, envelope.id)
        with self._write_lock:
            if path.exists():
                raise AlreadyExistsError(f"{envelope.tipo} {envelope.id} esiste già")
            now = now_iso()
            envelope.meta.created = now
            envelope.meta.updated = now
            self._validate_dati(envelope)
            tag = run_id or envelope.meta.run_id or "manual"
            self._write_and_commit(envelope, path, azione="crea", tag=tag)
        return envelope

    def update(self, envelope: Envelope, run_id: str | None = None) -> Envelope:
        path = self._path(envelope.tipo, envelope.id)
        with self._write_lock:
            if not path.is_file():
                raise NotFoundError(f"{envelope.tipo} {envelope.id} non trovato")
            existing = Envelope.model_validate_json(path.read_text(encoding="utf-8"))
            envelope.meta.created = existing.meta.created  # immutabile
            envelope.meta.updated = now_iso()
            self._validate_dati(envelope)
            tag = run_id or envelope.meta.run_id or "manual"
            self._write_and_commit(envelope, path, azione="aggiorna", tag=tag)
        return envelope

    def set_validato(
        self, tipo: str, entity_id: str, validato_da: str, run_id: str | None = None
    ) -> Envelope:
        """Bozza → validato. Da esporre SOLO su endpoint admin (piano §3.1)."""
        path = self._path(tipo, entity_id)
        with self._write_lock:
            if not path.is_file():
                raise NotFoundError(f"{tipo} {entity_id} non trovato")
            envelope = Envelope.model_validate_json(path.read_text(encoding="utf-8"))
            envelope.stato = "validato"
            envelope.meta.validato_da = validato_da
            envelope.meta.updated = now_iso()
            # la validazione è un'azione a sé: non eredita il run che creò la bozza
            self._write_and_commit(envelope, path, azione="valida", tag=run_id or "manual")
        return envelope

    def crea_issue(
        self,
        origine: str,
        testo: str,
        run_id: str | None = None,
        doc: str | None = None,
        entity_id: str | None = None,
    ) -> Issue:
        """Apre una segnalazione in ``data/issues/`` (id progressivo ISS-nnnn)."""
        with self._write_lock:
            cartella = self.data_dir / "issues"
            issue = Issue(
                id=self._prossimo_id_progressivo(cartella, "ISS"),
                origine=origine,
                testo=testo,
                run_id=run_id,
                doc=doc,
                entity_id=entity_id,
            )
            self._committa_json(
                cartella / f"{issue.id}.json",
                issue.model_dump(mode="json"),
                f"issue {issue.id}: crea [{run_id or 'manual'}]",
            )
        return issue

    def list_issues(self) -> list[Issue]:
        """Tutte le segnalazioni in ``data/issues/`` (per la coda admin)."""
        cartella = self.data_dir / "issues"
        return [
            Issue.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(cartella.glob("ISS-*.json"))
        ]

    def chiudi_issue(self, issue_id: str, run_id: str | None = None) -> Issue:
        """Segna una segnalazione come chiusa (azione admin)."""
        with self._write_lock:
            percorso = self.data_dir / "issues" / f"{issue_id}.json"
            if not percorso.is_file():
                raise NotFoundError(f"issue {issue_id} non trovata")
            issue = Issue.model_validate_json(percorso.read_text(encoding="utf-8"))
            issue.stato = "chiusa"
            self._committa_json(
                percorso,
                issue.model_dump(mode="json"),
                f"issue {issue.id}: chiudi [{run_id or 'manual'}]",
            )
        return issue

    def leggi_issue(self, issue_id: str) -> Issue:
        percorso = self.data_dir / "issues" / f"{issue_id}.json"
        if not percorso.is_file():
            raise NotFoundError(f"issue {issue_id} non trovata")
        return Issue.model_validate_json(percorso.read_text(encoding="utf-8"))

    def salva_patch(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Registra una proposta di patch dell'Improver (id progressivo PATCH-nnnn)."""
        with self._write_lock:
            cartella = self.data_dir / "patches"
            cartella.mkdir(parents=True, exist_ok=True)
            patch = {**patch, "id": self._prossimo_id_progressivo(cartella, "PATCH")}
            pid = patch["id"]
            self._committa_json(
                cartella / f"{pid}.json", patch, f"patch {pid}: proposta [{pid}]"
            )
        return patch

    def aggiorna_patch(self, patch: dict[str, Any], azione: str) -> dict[str, Any]:
        with self._write_lock:
            percorso = self.data_dir / "patches" / f"{patch['id']}.json"
            if not percorso.is_file():
                raise NotFoundError(f"patch {patch['id']} non trovata")
            self._committa_json(
                percorso, patch, f"patch {patch['id']}: {azione} [{patch['id']}]"
            )
        return patch

    def leggi_patch(self, patch_id: str) -> dict[str, Any]:
        percorso = self.data_dir / "patches" / f"{patch_id}.json"
        if not percorso.is_file():
            raise NotFoundError(f"patch {patch_id} non trovata")
        return json.loads(percorso.read_text(encoding="utf-8"))

    def list_patches(self) -> list[dict[str, Any]]:
        cartella = self.data_dir / "patches"
        return [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(cartella.glob("PATCH-*.json"))
        ]

    def crea_golden(
        self,
        workflow: str,
        version: str,
        doc: str,
        entity_tipo: str,
        atteso: dict[str, Any],
        run_id: str | None = None,
        entity_id: str | None = None,
        validato_da: str | None = None,
    ) -> dict[str, Any]:
        """Aggiunge un caso al golden set (id progressivo GOLD-nnnn)."""
        with self._write_lock:
            cartella = self.data_dir / "golden"
            cartella.mkdir(parents=True, exist_ok=True)
            payload = {
                "id": self._prossimo_id_progressivo(cartella, "GOLD"),
                "workflow": workflow,
                "version": str(version),
                "doc": doc,
                "entity_tipo": entity_tipo,
                "atteso": atteso,
                "run_id": run_id,
                "entity_id": entity_id,
                "validato_da": validato_da,
                "creato": now_iso(),
            }
            self._committa_json(
                cartella / f"{payload['id']}.json",
                payload,
                f"golden {payload['id']}: crea [{run_id or 'manual'}]",
            )
        return payload

    def commit_paths(self, percorsi: list[Path | str], message: str) -> None:
        """Committa file già scritti dentro ``data/`` (trace, dataset, blob).

        I trace si accumulano durante il run: un solo commit a fine run tiene
        fede a "ogni mutazione = un commit" senza un commit per evento.
        """
        with self._write_lock:
            relativi = []
            for percorso in percorsi:
                risolto = Path(percorso).resolve()
                if risolto.is_file():
                    relativi.append(risolto.relative_to(self.data_dir).as_posix())
            if not relativi:
                return
            self.repo.index.add(relativi)
            self.repo.index.commit(message, author=GIT_AUTHOR, committer=GIT_AUTHOR)

    # ------------------------------------------------------------ interni

    @staticmethod
    def _prossimo_id_progressivo(cartella: Path, prefisso: str, cifre: int = 4) -> str:
        """Primo id libero ``PREFISSO-nnnn`` nella cartella (issues, golden, patch…)."""
        progressivi = [0]
        for percorso in cartella.glob(f"{prefisso}-*.json"):
            coda = percorso.stem.rsplit("-", 1)[-1]
            if coda.isdigit():
                progressivi.append(int(coda))
        return f"{prefisso}-{max(progressivi) + 1:0{cifre}d}"

    def _spec(self, tipo: str) -> dict[str, Any]:
        try:
            return ENTITY_TYPES[tipo]
        except KeyError as exc:
            raise UnknownTypeError(f"tipo entità sconosciuto: {tipo!r}") from exc

    def _path(self, tipo: str, entity_id: str) -> Path:
        spec = self._spec(tipo)
        if not spec["id"].fullmatch(entity_id):
            raise InvalidIdError(f"id non valido per {tipo}: {entity_id!r}")
        base = self.data_dir / "entities" / spec["dir"]
        if spec["per_anno"]:
            base = base / entity_id.split("-")[1]
        return base / f"{entity_id}.json"

    def _validate_dati(self, envelope: Envelope) -> None:
        schema_path = self.data_dir / "schemas" / f"{envelope.tipo}.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = [
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in validator.iter_errors(envelope.dati)
        ]
        if errors:
            raise SchemaValidationError(envelope.tipo, envelope.id, errors)

    def _write_and_commit(self, envelope: Envelope, path: Path, azione: str, tag: str) -> None:
        """Scrittura atomica + commit. Chiamare solo dentro ``_write_lock``."""
        message = f"{envelope.tipo} {envelope.id}: {azione} [{tag}]"
        self._committa_json(path, envelope.model_dump(mode="json"), message)

    def _committa_json(self, path: Path, payload: dict[str, Any], message: str) -> None:
        """Scrittura atomica di un JSON + commit. Chiamare solo dentro ``_write_lock``."""
        path.parent.mkdir(parents=True, exist_ok=True)
        testo = json.dumps(payload, ensure_ascii=False, indent=2)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(testo + "\n", encoding="utf-8")
        tmp.replace(path)
        self.repo.index.add([path.relative_to(self.data_dir).as_posix()])
        self.repo.index.commit(message, author=GIT_AUTHOR, committer=GIT_AUTHOR)
