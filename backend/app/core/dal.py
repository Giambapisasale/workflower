"""Data Access Layer: ogni scrittura su ``data/`` passa da qui (piano §3.1).

Coda single-writer: un unico lock serializza scrittura file + commit git,
perché ogni mutazione produce un commit sullo stesso repo dati e l'indice
git non tollera scritture concorrenti. La granularità per cantiere diventa
utile solo quando i commit saranno raggruppabili; a questa scala non serve.
"""

import json
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from git import Actor, Repo
from jsonschema import Draft202012Validator, FormatChecker

from app.core.views import connect
from app.models.envelope import Envelope, Meta, now_iso
from app.models.issue import Issue

GIT_AUTHOR = Actor("Workflower", "bot@workflower.local")


class CatalogoNonValido(Exception):
    """Un'operazione sul catalogo lo lascerebbe non compilabile: annullata."""

# Tentativi di allocazione di un id progressivo: `prossimo_id` non prenota,
# quindi fra allocazione e create un run concorrente può prendere lo stesso id.
TENTATIVI_ID = 5

# Registry dei tipi entità: cartella, formato id, partizione per anno e le
# righe del riepilogo che l'operatore vede (etichetta + campo + tipo).
# Nuova entità = una riga qui + schema in data/schemas/<tipo>.schema.json:
# così il riepilogo si mostra da sé, senza toccare l'API né la UI.
# Tipi di riga: "testo"/"euro"/"percento"/"data" (la UI li formatta),
# "fornitore"/"cantiere" (rimando risolto nel nome) e "conteggio" (n. righe).
ENTITY_TYPES: dict[str, dict[str, Any]] = {
    "cantiere": {
        "dir": "cantieri",
        "etichetta": "Cantiere",
        "id": re.compile(r"^CNT-\d{3,}$"),
        "per_anno": False,
        "fmt": lambda anno, n: f"CNT-{n:03d}",
    },
    "fornitore": {
        "dir": "fornitori",
        "etichetta": "Fornitore",
        "id": re.compile(r"^FRN-\d{3,}$"),
        "per_anno": False,
        "fmt": lambda anno, n: f"FRN-{n:03d}",
    },
    "computo": {
        "dir": "computi",
        "etichetta": "Computo",
        "id": re.compile(r"^CMP-\d{3,}$"),
        "per_anno": False,
        "fmt": lambda anno, n: f"CMP-{n:03d}",
    },
    "fattura": {
        "dir": "fatture",
        "etichetta": "Fattura",
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
        "etichetta": "DDT",
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
        "etichetta": "SAL",
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
        "etichetta": "Rapportino",
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
        "etichetta": "Documento",
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


# Regione gestita in ``config/views.sql`` per le viste consolidate da
# ``/api/dataset/consolida``: rigenerata dal registro ``dataset/
# consolidamenti.jsonl`` a ogni consolidazione. Fuori da questi marker il
# catalogo resta scritto a mano (il loader di views.py ignora i commenti ``--``).
_VISTE_INIZIO = "-- === VISTE CONSOLIDATE — generate da /api/dataset/consolida ==="
_VISTE_FINE = "-- === FINE VISTE CONSOLIDATE ==="

# Regione gemella in ``config/macros.sql`` per i tool parametrici (macro
# tabellari) consolidati da ``/api/dataset/consolida-tool``, rigenerata dal
# registro ``dataset/tools.jsonl``. Vive in un file a parte perché le macro
# vanno caricate DOPO le viste (le referenziano): l'ordine dei file lo garantisce.
_TOOL_INIZIO = "-- === TOOL PARAMETRICI (MACRO) — generati da /api/dataset/consolida-tool ==="
_TOOL_FINE = "-- === FINE TOOL PARAMETRICI ==="
_INTESTAZIONE_MACRO = (
    "-- Tool parametrici (macro tabellari DuckDB) sul repo dati, in sola lettura.\n"
    "-- Generati da /api/dataset/consolida-tool: sono DATO, non codice.\n"
    "-- Caricati dopo le viste (le referenziano). Convenzione: niente ';' nei literal.\n"
)


def _regione_viste(consolidamenti: list[dict[str, Any]]) -> str:
    """La regione SQL delle viste consolidate, generata dal registro."""
    righe = [_VISTE_INIZIO, "-- rigenerata automaticamente: non modificare a mano"]
    for c in consolidamenti:
        righe.append(f"-- vista consolidata {c['vista']} (creata {c.get('creato', '')})")
        righe.append(f"CREATE OR REPLACE VIEW {c['vista']} AS")
        righe.append(f"{c['corpo']};")
        righe.append("")
    righe.append(_VISTE_FINE)
    return "\n".join(righe)


def _regione_tool(consolidamenti: list[dict[str, Any]]) -> str:
    """La regione SQL dei tool parametrici (macro), generata dal registro."""
    righe = [_TOOL_INIZIO, "-- rigenerata automaticamente: non modificare a mano"]
    for c in consolidamenti:
        firma = ", ".join(c.get("parametri", []))
        righe.append(f"-- tool consolidato {c['macro']} (creato {c.get('creato', '')})")
        righe.append(f"CREATE OR REPLACE MACRO {c['macro']}({firma}) AS TABLE (")
        righe.append(f"{c['corpo']}")
        righe.append(");")
        righe.append("")
    righe.append(_TOOL_FINE)
    return "\n".join(righe)


def _righe_ndjson(voci: list[dict[str, Any]]) -> str:
    """Serializza le voci di un registro come NDJSON (una riga JSON per voce)."""
    return "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in voci)


def _inserisci_regione(base: str, regione: str, inizio: str, fine: str) -> str:
    """Sostituisce (o accoda, la prima volta) una regione delimitata da marker."""
    if inizio in base and fine in base:
        testa = base[: base.index(inizio)].rstrip("\n")
        coda = base[base.index(fine) + len(fine) :].lstrip("\n")
        parti = [p for p in (testa, regione, coda) if p.strip()]
        return "\n".join(parti).rstrip("\n") + "\n"
    return base.rstrip("\n") + "\n\n" + regione + "\n"


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

    def crea_progressivo(
        self,
        tipo: str,
        dati: dict[str, Any],
        *,
        stato: str = "bozza",
        meta: Meta | None = None,
        tag: str | None = None,
    ) -> Envelope:
        """Crea un'entità allocando l'id progressivo del tipo, con retry.

        Sorgente unica dell'allocazione id: la usano sia i workflow (via
        ``tools/salva_bozza``) sia la creazione manuale admin. ``tag`` finisce
        nel messaggio di commit (es. ``manual:giovanna``) senza toccare il meta.
        """
        anno = self._anno_progressivo(tipo, dati)
        ultimo: Exception | None = None
        for _ in range(TENTATIVI_ID):
            entity_id = self.prossimo_id(tipo, anno)
            envelope = Envelope(
                id=entity_id,
                tipo=tipo,
                stato=stato,  # type: ignore[arg-type]
                dati=dati,
                meta=meta or Meta(),
            )
            try:
                return self.create(envelope, run_id=tag)
            except AlreadyExistsError as exc:
                # id preso da un run concorrente fra prossimo_id e create: riprova
                ultimo = exc
        raise DalError(f"nessun id libero per {tipo} dopo {TENTATIVI_ID} tentativi: {ultimo}")

    def _anno_progressivo(self, tipo: str, dati: dict[str, Any]) -> int | None:
        """L'anno di partizione per i tipi ``per_anno`` (dalla data, o l'anno corrente)."""
        if not self._spec(tipo).get("per_anno"):
            return None
        data = str(dati.get("data") or "")
        if len(data) >= 4 and data[:4].isdigit():
            return int(data[:4])
        return datetime.now(UTC).year

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

    def delete(self, tipo: str, entity_id: str, tag: str = "manual") -> None:
        """Elimina un'entità (git rm + commit). Da esporre SOLO a endpoint admin.

        Primitiva pura: non conosce i riferimenti fra entità e non fa mai
        cascade. Chi elimina deve prima accertarsi che nessuno la referenzi
        (la guardia vive nell'API). Recuperabile comunque dalla storia git.
        """
        path = self._path(tipo, entity_id)
        with self._write_lock:
            if not path.is_file():
                raise NotFoundError(f"{tipo} {entity_id} non trovato")
            rel = path.relative_to(self.data_dir).as_posix()
            self.repo.index.remove([rel], working_tree=True)
            self.repo.index.commit(
                f"{tipo} {entity_id}: elimina [{tag}]",
                author=GIT_AUTHOR,
                committer=GIT_AUTHOR,
            )

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

    def consolida_vista(
        self,
        *,
        nome: str,
        vista: str,
        corpo: str,
        fingerprint: str,
        esempio: str,
        creato_da: str,
    ) -> dict[str, Any]:
        """Registra una vista consolidata e la rende parte del catalogo.

        Aggiorna il registro ``dataset/consolidamenti.jsonl`` (fonte di verità) e
        rigenera da esso la regione gestita in ``config/views.sql``, poi committa:
        un'unica mutazione atomica sotto il lock. Idempotente sul nome vista (una
        nuova consolidazione con lo stesso nome rimpiazza la precedente). La
        validità della vista è garantita a monte da ``consolida.prepara``.
        """
        with self._write_lock:
            ledger = self.data_dir / "dataset" / "consolidamenti.jsonl"
            voci = [v for v in self._righe_jsonl(ledger) if v.get("vista") != vista]
            voce = {
                "creato": now_iso(),
                "nome": nome,
                "vista": vista,
                "fingerprint": fingerprint,
                "corpo": corpo,
                "esempio": esempio,
                "creato_da": creato_da,
            }
            voci.append(voce)
            self._scrivi_atomico(
                ledger, "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in voci)
            )

            views_sql = self.data_dir / "config" / "views.sql"
            aggiornato = _inserisci_regione(
                views_sql.read_text(encoding="utf-8"),
                _regione_viste(voci),
                _VISTE_INIZIO,
                _VISTE_FINE,
            )
            self._scrivi_atomico(views_sql, aggiornato)

            self.repo.index.add(
                [
                    ledger.relative_to(self.data_dir).as_posix(),
                    views_sql.relative_to(self.data_dir).as_posix(),
                ]
            )
            self.repo.index.commit(
                f"consolida: vista {vista} [{creato_da}]",
                author=GIT_AUTHOR,
                committer=GIT_AUTHOR,
            )
        return voce

    def consolida_tool(
        self,
        *,
        nome: str,
        macro: str,
        corpo: str,
        parametri: list[str],
        fingerprint: str,
        esempio: str,
        creato_da: str,
    ) -> dict[str, Any]:
        """Registra un tool parametrico e lo rende parte del catalogo (macro).

        Gemello di :meth:`consolida_vista`, branca "query parametrica" del §3.6:
        aggiorna il registro ``dataset/tools.jsonl`` (fonte di verità) e rigenera
        da esso la regione gestita in ``config/macros.sql``, poi committa in
        un'unica mutazione atomica sotto il lock. Idempotente sul nome della macro.
        La validità è garantita a monte da ``consolida.prepara_tool``.
        """
        with self._write_lock:
            ledger = self.data_dir / "dataset" / "tools.jsonl"
            voci = [v for v in self._righe_jsonl(ledger) if v.get("macro") != macro]
            voce = {
                "creato": now_iso(),
                "nome": nome,
                "macro": macro,
                "parametri": parametri,
                "fingerprint": fingerprint,
                "corpo": corpo,
                "esempio": esempio,
                "creato_da": creato_da,
            }
            voci.append(voce)
            self._scrivi_atomico(
                ledger, "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in voci)
            )

            macros_sql = self.data_dir / "config" / "macros.sql"
            base = (
                macros_sql.read_text(encoding="utf-8")
                if macros_sql.is_file()
                else _INTESTAZIONE_MACRO
            )
            aggiornato = _inserisci_regione(
                base, _regione_tool(voci), _TOOL_INIZIO, _TOOL_FINE
            )
            self._scrivi_atomico(macros_sql, aggiornato)

            self.repo.index.add(
                [
                    ledger.relative_to(self.data_dir).as_posix(),
                    macros_sql.relative_to(self.data_dir).as_posix(),
                ]
            )
            self.repo.index.commit(
                f"consolida: tool {macro} [{creato_da}]",
                author=GIT_AUTHOR,
                committer=GIT_AUTHOR,
            )
        return voce

    def elimina_tool(self, *, macro: str, eliminato_da: str) -> bool:
        """Rimuove un tool parametrico dal catalogo. Ritorna False se non esisteva.

        Toglie la voce dal registro ``dataset/tools.jsonl`` e rigenera la regione
        in ``config/macros.sql``; con il candidato di nuovo libero, la query può
        essere ri-consolidata (è così che si "modifica" un tool). Reversibile via
        git come ogni mutazione.
        """
        with self._write_lock:
            ledger = self.data_dir / "dataset" / "tools.jsonl"
            voci = self._righe_jsonl(ledger)
            restanti = [v for v in voci if v.get("macro") != macro]
            if len(restanti) == len(voci):
                return False
            macros_sql = self.data_dir / "config" / "macros.sql"
            base = (
                macros_sql.read_text(encoding="utf-8")
                if macros_sql.is_file()
                else _INTESTAZIONE_MACRO
            )
            self._commit_catalogo(
                [
                    (ledger, _righe_ndjson(restanti)),
                    (macros_sql, _inserisci_regione(
                        base, _regione_tool(restanti), _TOOL_INIZIO, _TOOL_FINE
                    )),
                ],
                f"consolida: rimuove tool {macro} [{eliminato_da}]",
            )
        return True

    def elimina_vista(self, *, vista: str, eliminato_da: str) -> bool:
        """Rimuove una vista consolidata dal catalogo. Ritorna False se non esisteva.

        Come :meth:`elimina_tool` ma sul registro ``consolidamenti.jsonl`` e su
        ``config/views.sql``. La verifica del catalogo impedisce di rimuovere una
        vista da cui un'altra vista (o un tool) dipende: in quel caso solleva.
        """
        with self._write_lock:
            ledger = self.data_dir / "dataset" / "consolidamenti.jsonl"
            voci = self._righe_jsonl(ledger)
            restanti = [v for v in voci if v.get("vista") != vista]
            if len(restanti) == len(voci):
                return False
            views_sql = self.data_dir / "config" / "views.sql"
            self._commit_catalogo(
                [
                    (ledger, _righe_ndjson(restanti)),
                    (views_sql, _inserisci_regione(
                        views_sql.read_text(encoding="utf-8"),
                        _regione_viste(restanti),
                        _VISTE_INIZIO,
                        _VISTE_FINE,
                    )),
                ],
                f"consolida: rimuove vista {vista} [{eliminato_da}]",
            )
        return True

    def _commit_catalogo(self, aggiornamenti: list[tuple[Path, str]], messaggio: str) -> None:
        """Scrive file di catalogo (ledger + .sql), verifica ``connect()``, poi committa.

        Se la modifica lascia il catalogo non compilabile (es. si rimuove una vista
        da cui un'altra dipende) ripristina i file e solleva :class:`CatalogoNonValido`,
        senza lasciare query/cruscotto inservibili. Solo dentro ``_write_lock``.
        """
        originali = [
            (percorso, percorso.read_text(encoding="utf-8") if percorso.is_file() else None)
            for percorso, _ in aggiornamenti
        ]
        for percorso, nuovo in aggiornamenti:
            self._scrivi_atomico(percorso, nuovo)
        try:
            connect(self.data_dir).close()
        except Exception as exc:
            for percorso, originale in originali:
                if originale is None:
                    percorso.unlink(missing_ok=True)
                else:
                    self._scrivi_atomico(percorso, originale)
            raise CatalogoNonValido(str(exc)) from exc
        self.repo.index.add(
            [percorso.relative_to(self.data_dir).as_posix() for percorso, _ in aggiornamenti]
        )
        self.repo.index.commit(messaggio, author=GIT_AUTHOR, committer=GIT_AUTHOR)

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
        self._scrivi_atomico(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        self.repo.index.add([path.relative_to(self.data_dir).as_posix()])
        self.repo.index.commit(message, author=GIT_AUTHOR, committer=GIT_AUTHOR)

    @staticmethod
    def _scrivi_atomico(percorso: Path, testo: str) -> None:
        """Scrive ``testo`` in modo atomico (tmp + replace). Solo dentro il lock."""
        percorso.parent.mkdir(parents=True, exist_ok=True)
        tmp = percorso.with_name(percorso.name + ".tmp")
        tmp.write_text(testo, encoding="utf-8")
        tmp.replace(percorso)

    @staticmethod
    def _righe_jsonl(percorso: Path) -> list[dict[str, Any]]:
        """Le righe di un file JSONL come dict (righe vuote/corrotte ignorate)."""
        if not percorso.is_file():
            return []
        voci: list[dict[str, Any]] = []
        for riga in percorso.read_text(encoding="utf-8").splitlines():
            if riga.strip():
                try:
                    voci.append(json.loads(riga))
                except json.JSONDecodeError:
                    continue
        return voci
