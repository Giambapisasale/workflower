"""Agente dati conversazionale, read-only e tool-first.

Il modello non riceve SQL, viste o macro: vede esclusivamente gli schemi dei
tool dichiarati nel workflow ``interroga``. Le query restano un dettaglio
interno e validato del registry, eseguito dal server con i filtri di ruolo.
"""

import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturoScaduto
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from time import monotonic
from typing import Any

import duckdb
import yaml
from jsonschema import Draft202012Validator

from app.core.dal import DAL
from app.core.gateway import Gateway, GatewayError, RispostaLLM, estrai_json
from app.core.tracer import Tracer
from app.core.views import connect

logger = logging.getLogger("workflower.agente_dati")

MAX_GIRI_AGENTE = 8
MAX_TOOL_CALL_TOTALI = 8
MAX_RIGHE_TOOL = 100
MAX_BYTE_RISULTATO_TOOL = 32_000
TIMEOUT_TOOL_SECONDI = 10
TIMEOUT_RUN_SECONDI = 45
LIMITE_PREDEFINITO = 20
LIMITE_MINIMO = 6
LIMITE_MASSIMO = 30
_NOME_SICURO = re.compile(r"^[a-z][a-z0-9_-]{1,60}$")
_COLONNA_SICURA = re.compile(r"^[a-z][a-z0-9_]{0,60}$")
_INDIZIO_IMPLEMENTAZIONE = re.compile(
    r"\b(sql|select|from|where|join|insert|update|delete|drop|create|alter|v_[a-z0-9_]+|t_[a-z0-9_]+)\b",
    re.IGNORECASE,
)
_ID_PROPOSTA = re.compile(r"^AGENT-\d{4}$")


# Catalogo privato: i nomi qui sotto sono semantici per la DSL. Le istruzioni,
# API e trace non ricevono mai le implementazioni DuckDB. Le viste/macro restano
# un dettaglio interno dell'applicazione e non un linguaggio per il modello.
_FONTI: dict[str, dict[str, Any]] = {
    "cantieri": {
        "etichetta": "cantieri",
        "bindings": ["cerca", "cerca", "cerca"],
        "query": """SELECT id AS cantiere_id, nome, comune, provincia, stato, budget, capocantiere
FROM v_cantieri
WHERE (? IS NULL OR nome ILIKE '%' || ? || '%' OR comune ILIKE '%' || ? || '%')""",
        "scope_bindings": ["__scope__", "cerca", "cerca", "cerca"],
        "scope_query": """SELECT id AS cantiere_id, nome, comune, provincia, stato, budget, capocantiere
FROM v_cantieri
WHERE id = ANY(?) AND (? IS NULL OR nome ILIKE '%' || ? || '%' OR comune ILIKE '%' || ? || '%')""",
    },
    "scheda_cantiere": {
        "etichetta": "scheda cantiere",
        "bindings": ["cerca", "cerca"],
        "query": """SELECT c.id AS cantiere_id, c.nome, c.budget,
 COALESCE(f.totale_fatture, 0) AS fatture, COALESCE(o.ore, 0) AS ore,
 COALESCE(o.manodopera, 0) AS manodopera
FROM v_cantieri c
LEFT JOIN (SELECT cantiere_id, SUM(totale) AS totale_fatture FROM v_fatture GROUP BY cantiere_id) f ON f.cantiere_id = c.id
LEFT JOIN (SELECT cantiere_id, SUM(ore) AS ore, SUM(costo) AS manodopera FROM v_rapportini_righe GROUP BY cantiere_id) o ON o.cantiere_id = c.id
WHERE (? IS NULL OR c.nome ILIKE '%' || ? || '%')""",
        "scope_bindings": ["__scope__", "cerca", "cerca"],
        "scope_query": """WITH cantieri_scope AS (
 SELECT id, nome, budget FROM v_cantieri WHERE id = ANY(?)
), fatture_scope AS (
 SELECT f.cantiere_id, SUM(f.totale) AS totale_fatture FROM v_fatture f
 JOIN cantieri_scope c ON c.id = f.cantiere_id GROUP BY f.cantiere_id
), ore_scope AS (
 SELECT r.cantiere_id, SUM(r.ore) AS ore, SUM(r.costo) AS manodopera FROM v_rapportini_righe r
 JOIN cantieri_scope c ON c.id = r.cantiere_id GROUP BY r.cantiere_id
)
SELECT c.id AS cantiere_id, c.nome, c.budget, COALESCE(f.totale_fatture, 0) AS fatture,
 COALESCE(o.ore, 0) AS ore, COALESCE(o.manodopera, 0) AS manodopera
FROM cantieri_scope c LEFT JOIN fatture_scope f ON f.cantiere_id = c.id
 LEFT JOIN ore_scope o ON o.cantiere_id = c.id
WHERE (? IS NULL OR c.nome ILIKE '%' || ? || '%')""",
    },
    "fornitori": {
        "etichetta": "fornitori",
        "bindings": ["cerca", "cerca", "cerca", "cerca"],
        "query": """SELECT id, ragione_sociale, categoria, comune, partita_iva, telefono
FROM v_fornitori
WHERE (? IS NULL OR ragione_sociale ILIKE '%' || ? || '%' OR categoria ILIKE '%' || ? || '%' OR partita_iva ILIKE '%' || ? || '%')""",
    },
    "fatture": {
        "etichetta": "fatture",
        "bindings": ["cerca", "cerca", "cerca"],
        "query": """SELECT f.id, f.cantiere_id, f.numero, f.data, f.fornitore_id, f.totale, f.iva,
 f.ritenuta_acconto, f.scadenza_pagamento, f.stato
FROM v_fatture f
WHERE (? IS NULL OR f.numero ILIKE '%' || ? || '%' OR f.fornitore_id ILIKE '%' || ? || '%')
ORDER BY f.data DESC""",
        "scope_bindings": ["__scope__", "cerca", "cerca", "cerca"],
        "scope_query": """SELECT f.id, f.cantiere_id, f.numero, f.data, f.fornitore_id, f.totale, f.iva,
 f.ritenuta_acconto, f.scadenza_pagamento, f.stato
FROM v_fatture f WHERE f.cantiere_id = ANY(?)
 AND (? IS NULL OR f.numero ILIKE '%' || ? || '%' OR f.fornitore_id ILIKE '%' || ? || '%')
ORDER BY f.data DESC""",
    },
    "righe_fattura": {
        "etichetta": "righe fattura",
        "bindings": ["cerca", "cerca"],
        "query": """SELECT fattura_id, cantiere_id, data, descrizione, quantita, unita_misura, importo, voce_computo_id, tipo_costo
FROM v_fatture_righe WHERE (? IS NULL OR descrizione ILIKE '%' || ? || '%') ORDER BY data DESC""",
        "scope_bindings": ["__scope__", "cerca", "cerca"],
        "scope_query": """SELECT fattura_id, cantiere_id, data, descrizione, quantita, unita_misura, importo, voce_computo_id, tipo_costo
FROM v_fatture_righe WHERE cantiere_id = ANY(?)
 AND (? IS NULL OR descrizione ILIKE '%' || ? || '%') ORDER BY data DESC""",
    },
    "costi_cantiere": {
        "etichetta": "costi cantiere",
        "bindings": ["cerca"],
        "query": """SELECT cantiere_id, cantiere AS nome, materiali_e_servizi, mezzi, manodopera, costo_totale
FROM t_costi_cantiere(COALESCE(?, ''))""",
        "scope_bindings": ["__scope__", "cerca", "cerca"],
        "scope_query": """SELECT cantiere_id, cantiere AS nome, materiali_e_servizi, mezzi, manodopera, costo_totale
FROM v_cantiere_costi WHERE cantiere_id = ANY(?)
 AND (? IS NULL OR cantiere ILIKE '%' || ? || '%')""",
    },
    "scostamenti": {
        "etichetta": "scostamenti",
        "bindings": ["cerca", "cerca", "cerca"],
        "query": """SELECT cantiere_id, codice, descrizione, categoria, previsto, consuntivo, delta
FROM v_scostamento_voci
WHERE (? IS NULL OR descrizione ILIKE '%' || ? || '%' OR categoria ILIKE '%' || ? || '%') ORDER BY delta DESC""",
        "scope_bindings": ["__scope__", "cerca", "cerca", "cerca"],
        "scope_query": """SELECT cantiere_id, codice, descrizione, categoria, previsto, consuntivo, delta
FROM v_scostamento_voci WHERE cantiere_id = ANY(?)
 AND (? IS NULL OR descrizione ILIKE '%' || ? || '%' OR categoria ILIKE '%' || ? || '%') ORDER BY delta DESC""",
    },
    "ore_manodopera": {
        "etichetta": "ore e manodopera",
        "bindings": ["cerca", "cerca", "cerca"],
        "query": """SELECT cantiere_id, lavoratore, mansione, SUM(ore) AS ore, SUM(costo) AS costo
FROM v_rapportini_righe
WHERE (? IS NULL OR lavoratore ILIKE '%' || ? || '%' OR mansione ILIKE '%' || ? || '%')
GROUP BY cantiere_id, lavoratore, mansione ORDER BY ore DESC""",
        "scope_bindings": ["__scope__", "cerca", "cerca", "cerca"],
        "scope_query": """SELECT cantiere_id, lavoratore, mansione, SUM(ore) AS ore, SUM(costo) AS costo
FROM v_rapportini_righe WHERE cantiere_id = ANY(?)
 AND (? IS NULL OR lavoratore ILIKE '%' || ? || '%' OR mansione ILIKE '%' || ? || '%')
GROUP BY cantiere_id, lavoratore, mansione ORDER BY ore DESC""",
    },
    "dipendenti_allocazioni": {
        "etichetta": "dipendenti e allocazioni",
        "bindings": ["cerca", "cerca", "cerca"],
        "query": """SELECT d.id, d.nome, d.cognome, d.tipo, d.tariffa_oraria, a.cantiere_id, a.da, a.a
FROM v_dipendenti d LEFT JOIN v_allocazioni a ON a.dipendente_id = d.id
WHERE (? IS NULL OR d.nome ILIKE '%' || ? || '%' OR d.cognome ILIKE '%' || ? || '%')""",
    },
    "ddt": {
        "etichetta": "documenti di trasporto",
        "bindings": ["cerca", "cerca", "cerca"],
        "query": """SELECT id, cantiere_id, numero, data, fornitore_id, causale, riferimento_ordine, n_righe, stato
FROM v_ddt WHERE (? IS NULL OR numero ILIKE '%' || ? || '%' OR causale ILIKE '%' || ? || '%') ORDER BY data DESC""",
        "scope_bindings": ["__scope__", "cerca", "cerca", "cerca"],
        "scope_query": """SELECT id, cantiere_id, numero, data, fornitore_id, causale, riferimento_ordine, n_righe, stato
FROM v_ddt WHERE cantiere_id = ANY(?)
 AND (? IS NULL OR numero ILIKE '%' || ? || '%' OR causale ILIKE '%' || ? || '%') ORDER BY data DESC""",
    },
    "sal_avanzamento": {
        "etichetta": "avanzamento lavori",
        "bindings": [],
        "query": """SELECT s.cantiere_id, s.numero, s.data, s.importo_lavori, s.importo_progressivo,
s.percentuale_avanzamento, c.pianificato_pct, c.reale_pct, c.delta_pct
FROM v_sal s LEFT JOIN v_cronoprogramma c ON c.cantiere_id = s.cantiere_id ORDER BY s.data DESC""",
        "scope_bindings": ["__scope__"],
        "scope_query": """SELECT s.cantiere_id, s.numero, s.data, s.importo_lavori, s.importo_progressivo,
s.percentuale_avanzamento, c.pianificato_pct, c.reale_pct, c.delta_pct
FROM v_sal s LEFT JOIN v_cronoprogramma c ON c.cantiere_id = s.cantiere_id
WHERE s.cantiere_id = ANY(?) ORDER BY s.data DESC""",
    },
    "mezzi_tco": {
        "etichetta": "costi mezzi",
        "bindings": ["cerca", "cerca"],
        "query": """SELECT mezzo_id, descrizione, proprieta, costo_orario_pieno, costo_fatture,
costo_manutenzioni, costo_documentale FROM v_mezzi_tco
WHERE (? IS NULL OR descrizione ILIKE '%' || ? || '%') ORDER BY costo_documentale DESC""",
    },
    "pagamenti_scadenze": {
        "etichetta": "pagamenti e scadenze",
        "bindings": [],
        "query": """SELECT p.fattura_id, f.cantiere_id, p.stato_pagamento, p.importo_pagato,
p.data, p.scadenza, p.residuo FROM v_pagamenti p LEFT JOIN v_fatture f ON f.id = p.fattura_id
ORDER BY p.scadenza ASC NULLS LAST""",
    },
    "materiali_lavorazioni": {
        "etichetta": "materiali e lavorazioni",
        "bindings": ["cerca", "cerca", "cerca", "cerca", "cerca", "cerca", "cerca", "cerca"],
        "query": """SELECT 'materiale' AS tipo, id, codice, descrizione, categoria, unita_misura, prezzo_unitario
FROM v_materiali WHERE (? IS NULL OR codice ILIKE '%' || ? || '%' OR descrizione ILIKE '%' || ? || '%' OR categoria ILIKE '%' || ? || '%')
UNION ALL SELECT 'lavorazione' AS tipo, id, codice, descrizione, categoria, unita_misura, NULL AS prezzo_unitario
FROM v_lavorazioni WHERE (? IS NULL OR codice ILIKE '%' || ? || '%' OR descrizione ILIKE '%' || ? || '%' OR categoria ILIKE '%' || ? || '%')""",
    },
    "pozzetti_scadenze": {
        "etichetta": "pozzetti e scadenze",
        "bindings": [],
        "query": """SELECT 'pozzetto' AS tipo, cantiere_id, id, codice AS descrizione, stato_manufatto AS stato, data_installazione AS data FROM v_pozzetti
UNION ALL SELECT 'scadenza' AS tipo, cantiere_id, id, descrizione, stato_adempimento AS stato, data_scadenza AS data FROM v_scadenze""",
        "scope_bindings": ["__scope__", "__scope__"],
        "scope_query": """SELECT 'pozzetto' AS tipo, cantiere_id, id, codice AS descrizione, stato_manufatto AS stato, data_installazione AS data
FROM v_pozzetti WHERE cantiere_id = ANY(?)
UNION ALL SELECT 'scadenza' AS tipo, cantiere_id, id, descrizione, stato_adempimento AS stato, data_scadenza AS data
FROM v_scadenze WHERE cantiere_id = ANY(?)""",
    },
}

RISPOSTA_FALLBACK = "Non riesco a rispondere adesso. Riprova tra poco."
RISPOSTA_NON_COPERTA = (
    "Non ho ancora lo strumento giusto per controllare questa cosa. "
    "Puoi dirlo all'ufficio così lo aggiungiamo."
)


class AgenteDatiError(Exception):
    """Errore gestibile dell'agente dati."""


class ToolDatiError(AgenteDatiError):
    """Tool non disponibile, non autorizzato o con argomenti non validi."""


class CatalogoDatiError(AgenteDatiError):
    """L'installazione è incompleta: manca (o è illeggibile) il catalogo dell'agente.

    Distinto dagli altri errori perché non dipende da cosa ha chiesto l'utente:
    nessuna domanda, riformulata comunque, può funzionare finché il repo dati non
    viene allineato. Serve separato perché il messaggio utile — *quale* file e
    *quale* comando lo ripara — va all'amministratore e al log, mai all'operatore,
    che dal canto suo non può farci nulla e non deve leggere un comando di shell.
    """


def _semplice(valore: Any) -> Any:
    if isinstance(valore, datetime | date):
        return valore.isoformat()
    if isinstance(valore, Decimal):
        return float(valore)
    return valore


def _messaggio_assistant(risposta: RispostaLLM) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": risposta.text or "",
        "tool_calls": [
            {
                "id": chiamata.id,
                "type": "function",
                "function": {
                    "name": chiamata.name,
                    "arguments": json.dumps(chiamata.arguments, ensure_ascii=False),
                },
            }
            for chiamata in risposta.tool_calls
        ],
    }


def _testo_tool(risultato: Any) -> str:
    testo = json.dumps(risultato, ensure_ascii=False, default=str)
    if len(testo.encode("utf-8")) <= MAX_BYTE_RISULTATO_TOOL:
        return testo
    # Il risultato è già limitato per righe; se contiene campi eccezionalmente
    # lunghi resta meglio dichiararlo al modello che troncarlo a metà JSON.
    return json.dumps(
        {
            "errore": "risultato troppo grande per la conversazione",
            "nota": "chiedi un filtro più preciso",
        },
        ensure_ascii=False,
    )


def _risposta_pubblica(testo: str) -> str:
    """Impedisce che dettagli di implementazione escano dalla chat."""
    if _INDIZIO_IMPLEMENTAZIONE.search(testo):
        return RISPOSTA_NON_COPERTA
    return testo


def _leggi_json(percorso: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not percorso.is_file():
        return dict(default)
    try:
        contenuto = json.loads(percorso.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(default)
    return contenuto if isinstance(contenuto, dict) else dict(default)


def _scrivi_json(percorso: Path, contenuto: dict[str, Any]) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    tmp = percorso.with_name(percorso.name + ".tmp")
    tmp.write_text(json.dumps(contenuto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(percorso)


def _percorso_conversazione(data_dir: Path, username: str) -> Path:
    if not _NOME_SICURO.fullmatch(username):
        raise AgenteDatiError("utente non valido per la conversazione")
    return data_dir / "conversations" / f"{username}.json"


def configurazione(data_dir: Path | str) -> dict[str, int]:
    dati = _leggi_json(Path(data_dir) / "config" / "agente-dati.json", {})
    valore = dati.get("max_messages", LIMITE_PREDEFINITO)
    try:
        valore = int(valore)
    except (TypeError, ValueError):
        valore = LIMITE_PREDEFINITO
    valore = max(LIMITE_MINIMO, min(LIMITE_MASSIMO, valore))
    return {"max_messages": valore}


def aggiorna_configurazione(dal: DAL, max_messages: int, deciso_da: str) -> dict[str, int]:
    if not LIMITE_MINIMO <= max_messages <= LIMITE_MASSIMO:
        raise AgenteDatiError(
            f"il limite deve essere compreso tra {LIMITE_MINIMO} e {LIMITE_MASSIMO}"
        )
    base = Path(dal.data_dir)
    percorso = base / "config" / "agente-dati.json"
    # La modifica del limite e il taglio delle memorie sono un solo fatto: al
    # ritorno dell'API nessuna conversazione può più superare il nuovo limite.
    aggiornamenti: dict[Path, str] = {
        percorso: json.dumps({"max_messages": max_messages}, ensure_ascii=False, indent=2) + "\n"
    }
    for chat in (base / "conversations").glob("*.json"):
        contenuto = _leggi_json(chat, {"username": chat.stem, "messages": []})
        messaggi = _scambi_completi(contenuto.get("messages"), max_messages)
        if messaggi != contenuto.get("messages"):
            aggiornamenti[chat] = json.dumps(
                {"username": contenuto.get("username", chat.stem), "messages": messaggi},
                ensure_ascii=False,
                indent=2,
            ) + "\n"
    dal.commit_updates(
        aggiornamenti,
        message=f"agente dati: limite conversazione {max_messages} [{deciso_da}]",
    )
    return {"max_messages": max_messages}


def impronta_catalogo(
    data_dir: Path | str, sostituzioni: dict[Path, str] | None = None
) -> str:
    """Impronta riproducibile di registry, manifest e skill effettivamente caricati."""
    base = Path(data_dir) / "workflows" / "interroga"
    sostituzioni = sostituzioni or {}

    def contenuto(percorso: Path) -> bytes:
        # `sostituzioni` va letto prima del file: con `dict.get(k, default)` il
        # default si valuta comunque, quindi una sostituzione per un file che
        # non esiste ancora (una skill proposta e non ancora scritta) andava in
        # errore proprio nel caso per cui era stata pensata.
        if percorso in sostituzioni:
            return sostituzioni[percorso].encode("utf-8")
        try:
            return percorso.read_text(encoding="utf-8").encode("utf-8")
        except OSError:
            # Un pezzo di catalogo che manca è un guaio vero, ma non è qui che
            # si segnala: questa funzione deve solo produrre un'impronta stabile.
            # A dirlo — con un messaggio utile — è chi il catalogo lo carica
            # davvero (RegistryToolDati). Un'impronta che esplode trasformava un
            # repo dati non allineato in un 500 senza spiegazione.
            return b""

    parti = [contenuto(base / "manifest.yaml"), contenuto(base / "tools.yaml")]
    parti.extend(contenuto(p) for p in sorted((base / "skills").glob("*.md")))
    for percorso, testo in sostituzioni.items():
        if percorso.parent == base / "skills" and not percorso.is_file():
            parti.append(testo.encode("utf-8"))
    return sha256(b"\0".join(parti)).hexdigest()[:16]


def _scambi_completi(valore: Any, limite: int) -> list[dict[str, Any]]:
    """Normalizza la memoria a soli scambi utente→assistente completi.

    `limite` è il numero massimo di messaggi, non di scambi: quando è dispari
    preferiamo una coppia in meno a un contesto spezzato.
    """
    if not isinstance(valore, list):
        return []
    coppie: list[tuple[dict[str, Any], dict[str, Any]]] = []
    utente: dict[str, Any] | None = None
    for messaggio in valore:
        if not isinstance(messaggio, dict) or not isinstance(messaggio.get("content"), str):
            continue
        ruolo = messaggio.get("role")
        if ruolo == "user":
            utente = {"role": "user", "content": messaggio["content"]}
        elif ruolo == "assistant" and utente is not None:
            risposta = {"role": "assistant", "content": messaggio["content"]}
            if isinstance(messaggio.get("run_id"), str):
                risposta["run_id"] = messaggio["run_id"]
            coppie.append((utente, risposta))
            utente = None
    da_tenere = max(0, limite // 2)
    return [messaggio for coppia in coppie[-da_tenere:] for messaggio in coppia]


class RegistryToolDati:
    """Registry YAML dei tool dell'agente, separato dai tool di estrazione."""

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "workflows" / "interroga" / "tools.yaml"
        self._tools = self._carica()

    def _carica(self) -> dict[str, dict[str, Any]]:
        try:
            documento = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except FileNotFoundError as exc:
            # Caso tipico: repo dati creato da un'immagine precedente e mai
            # allineato. Il percorso da solo non basta a capire cosa fare.
            raise CatalogoDatiError(
                f"il catalogo dei tool dell'agente non c'è nel repo dati ({self.path}): "
                "il repo è rimasto a una versione precedente dell'applicazione. "
                "Allinearlo con `python -m app.sync_dati --applica`."
            ) from exc
        except OSError as exc:
            raise CatalogoDatiError(f"registry tool non leggibile: {exc}") from exc
        voci = documento.get("tools") if isinstance(documento, dict) else None
        if not isinstance(voci, list):
            raise CatalogoDatiError(
                f"registry tool non valido ({self.path}): manca l'elenco 'tools'"
            )
        risultato: dict[str, dict[str, Any]] = {}
        for voce in voci:
            self.valida_spec(voce)
            nome = str(voce["name"])
            if nome in risultato:
                raise AgenteDatiError(f"tool duplicato: {nome}")
            risultato[nome] = voce
        return risultato

    @staticmethod
    def valida_spec(voce: Any) -> None:
        if not isinstance(voce, dict):
            raise AgenteDatiError("tool non valido")
        nome = voce.get("name")
        if not isinstance(nome, str) or not _NOME_SICURO.fullmatch(nome):
            raise AgenteDatiError(f"nome tool non valido: {nome!r}")
        if not isinstance(voce.get("description"), str) or not voce["description"].strip():
            raise AgenteDatiError(f"descrizione mancante per {nome}")
        schema = voce.get("parameters")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise AgenteDatiError(f"schema parametri non valido per {nome}")
        implementazione = voce.get("implementation")
        if not isinstance(implementazione, dict):
            raise AgenteDatiError(f"implementazione dichiarativa mancante per {nome}")
        fonte = implementazione.get("source")
        if not isinstance(fonte, str) or fonte not in _FONTI:
            raise AgenteDatiError(f"fonte dichiarativa non valida per {nome}")
        for campo in ("filters", "aggregations", "ordering"):
            if campo not in implementazione:
                raise AgenteDatiError(f"{campo} mancante per {nome}")
        if voce.get("scope") not in {"cantiere", "globale"}:
            raise AgenteDatiError(f"scope non valido per {nome}")
        if not isinstance(voce.get("roles"), list) or not set(voce["roles"]) <= {"op", "admin"}:
            raise AgenteDatiError(f"ruoli non validi per {nome}")
        if voce.get("scope") == "cantiere":
            colonna_scope = voce.get("scope_column", "cantiere_id")
            if not isinstance(colonna_scope, str) or not _COLONNA_SICURA.fullmatch(colonna_scope):
                raise AgenteDatiError(f"colonna scope non valida per {nome}")
        # I binding vivono nel catalogo privato della fonte, non nella DSL e non
        # possono quindi essere scelti/iniettati dal modello.

    def elenco(self, ruolo: str, cantieri: list[str]) -> list[dict[str, Any]]:
        return [
            {k: v for k, v in tool.items() if k != "implementation"}
            for tool in self._tools.values()
            if self._autorizzato(tool, ruolo, cantieri)
        ]

    def elenco_admin(self) -> list[dict[str, Any]]:
        """DSL ispezionabile dall'ufficio, senza il compilatore DuckDB privato."""
        return [json.loads(json.dumps(tool)) for tool in self._tools.values()]

    def schemi(self, ruolo: str, cantieri: list[str]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in self._tools.values()
            if self._autorizzato(tool, ruolo, cantieri)
        ]

    def fonti_usate(self, nomi: list[str]) -> list[dict[str, str]]:
        """Evidenza leggibile per l'ufficio, senza dettagli implementativi."""
        viste: list[dict[str, str]] = []
        for nome in dict.fromkeys(nomi):
            tool = self._tools.get(nome)
            if tool is None:
                continue
            fonte = _FONTI[tool["implementation"]["source"]]
            viste.append({"tool": nome, "source": str(fonte["etichetta"])})
        return viste

    @staticmethod
    def _autorizzato(tool: dict[str, Any], ruolo: str, cantieri: list[str]) -> bool:
        if ruolo not in tool["roles"]:
            return False
        return not (tool["scope"] == "cantiere" and ruolo == "op" and not cantieri)

    def esegui(
        self, nome: str, argomenti: dict[str, Any], ruolo: str, cantieri: list[str]
    ) -> dict[str, Any]:
        tool = self._tools.get(nome)
        if tool is None:
            raise ToolDatiError("strumento non disponibile")
        return self.esegui_spec(tool, argomenti, ruolo, cantieri)

    def esegui_spec(
        self, tool: dict[str, Any], argomenti: dict[str, Any], ruolo: str, cantieri: list[str]
    ) -> dict[str, Any]:
        """Esegue una specifica già validata, anche durante il collaudo di una proposta."""
        self.valida_spec(tool)
        if not self._autorizzato(tool, ruolo, cantieri):
            raise ToolDatiError("strumento non disponibile per questo accesso")
        validatore = Draft202012Validator(tool["parameters"])
        errori = [errore.message for errore in validatore.iter_errors(argomenti)]
        if errori:
            raise ToolDatiError("argomenti non validi: " + "; ".join(errori[:3]))

        implementazione = tool["implementation"]
        risolto = self._risolvi_anagrafica(implementazione, argomenti, ruolo, cantieri)
        if risolto is not None:
            return risolto
        fonte = _FONTI[str(implementazione["source"])]
        binding = fonte["bindings"]
        sql = str(fonte["query"])
        if tool["scope"] == "cantiere" and ruolo == "op":
            # Il compilatore sceglie una variante il cui perimetro e' nella
            # lettura di fonte, prima di join e aggregazioni. Non esiste una
            # strada in cui il modello possa togliere o spostare il filtro.
            sql = str(fonte.get("scope_query", ""))
            binding = fonte.get("scope_bindings", [])
            if not sql:
                raise ToolDatiError("fonte non utilizzabile nel perimetro operatore")
        valori = [cantieri if nome == "__scope__" else argomenti.get(nome) for nome in binding]
        sql = f"SELECT * FROM ({sql}) AS risultato LIMIT ?"
        valori.append(MAX_RIGHE_TOOL)

        conn = None
        try:
            # ``connect`` prepara il catalogo delle viste/macro autorizzate in
            # una connessione read-only rispetto al repo dati.
            conn = connect(self.data_dir)
            with ThreadPoolExecutor(max_workers=1) as pool:
                futuro = pool.submit(conn.execute, sql, valori)
                try:
                    cursore = futuro.result(timeout=TIMEOUT_TOOL_SECONDI)
                except FuturoScaduto:
                    conn.interrupt()
                    raise ToolDatiError(
                        f"strumento interrotto dopo {TIMEOUT_TOOL_SECONDI} secondi"
                    ) from None
            colonne = [c[0] for c in cursore.description]
            righe = [
                {colonna: _semplice(valore) for colonna, valore in zip(colonne, riga, strict=True)}
                for riga in cursore.fetchall()
            ]
        except duckdb.Error as exc:
            # All'utente va una frase innocua — il testo di DuckDB nomina viste e
            # colonne, e non è roba sua. Ma senza questa riga il perché non lo
            # sapeva *nessuno*: il trace registra solo «non disponibile», e un
            # catalogo rotto (una macro che nomina una vista che non c'è: fa
            # fallire ogni query, non una) diventava invisibile. Il costo di
            # sbagliare qui non è una query persa, è non sapere di averla persa.
            logger.error("tool %s non eseguibile sul catalogo: %s", tool.get("name"), exc)
            raise ToolDatiError("strumento momentaneamente non disponibile") from exc
        finally:
            if conn is not None:
                conn.close()
        return {"risultati": righe, "troncato": len(righe) >= MAX_RIGHE_TOOL}

    def _risolvi_anagrafica(
        self,
        implementazione: dict[str, Any],
        argomenti: dict[str, Any],
        ruolo: str,
        cantieri: list[str],
    ) -> dict[str, Any] | None:
        """Adapter sulle primitive fuzzy esistenti per le ricerche anagrafiche.

        Evita di duplicare la logica di similarità usata dai workflow documentali.
        Il filtro operatore è applicato ai candidati prima che il risultato esca
        dal server; questi strumenti non aggregano dati.
        """
        cerca = argomenti.get("cerca")
        fonte = implementazione.get("source")
        if not isinstance(cerca, str) or not cerca.strip():
            return None
        from app.core.tools import ricerca

        if fonte == "cantieri":
            candidati = ricerca.cerca_cantiere(DAL(self.data_dir), cerca)["risultati"]
            if ruolo == "op":
                candidati = [c for c in candidati if c.get("id") in cantieri]
            righe = [
                {
                    "cantiere_id": c["id"],
                    "nome": c.get("nome"),
                    "comune": c.get("comune"),
                    "committente": c.get("committente"),
                }
                for c in candidati
            ]
            return {"risultati": righe[:MAX_RIGHE_TOOL], "troncato": False}
        if fonte == "fornitori":
            candidati = ricerca.cerca_fornitore(DAL(self.data_dir), cerca)["risultati"]
            righe = [
                {
                    "id": c["id"],
                    "ragione_sociale": c.get("ragione_sociale"),
                    "partita_iva": c.get("partita_iva"),
                    "comune": c.get("comune"),
                }
                for c in candidati
            ]
            return {"risultati": righe[:MAX_RIGHE_TOOL], "troncato": False}
        return None


class AgenteDati:
    """Ciclo conversazionale dell'agente, con una sola capacità: leggere dati."""

    def __init__(self, dal: DAL, gateway: Gateway) -> None:
        self.dal = dal
        self.data_dir = Path(dal.data_dir)
        self.gateway = gateway
        self.wf_dir = self.data_dir / "workflows" / "interroga"

    def conversazione(self, username: str) -> dict[str, Any]:
        percorso = _percorso_conversazione(self.data_dir, username)
        contenuto = _leggi_json(percorso, {"username": username, "messages": []})
        limite = configurazione(self.data_dir)["max_messages"]
        messaggi = _scambi_completi(contenuto.get("messages"), limite)
        return {"messages": messaggi, "max_messages": limite}

    def reset(self, username: str) -> dict[str, Any]:
        percorso = _percorso_conversazione(self.data_dir, username)
        self.dal.commit_updates(
            {percorso: json.dumps({"username": username, "messages": []}, ensure_ascii=False, indent=2) + "\n"},
            message=f"agente dati: conversazione azzerata [{username}]",
        )
        return {"messages": [], "max_messages": configurazione(self.data_dir)["max_messages"]}

    def rispondi(
        self, *, username: str, ruolo: str, cantieri: list[str], contenuto: str
    ) -> dict[str, Any]:
        domanda = contenuto.strip()
        if not domanda or len(domanda) > 2_000:
            raise AgenteDatiError("scrivi una domanda tra 1 e 2000 caratteri")
        manifest = self._manifest()
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        tracer = Tracer(
            self.data_dir,
            run_id,
            manifest.get("name", "interroga"),
            str(manifest.get("version", "?")),
        )
        tracer.run_start(domanda, catalog_hash=impronta_catalogo(self.data_dir))
        registry = RegistryToolDati(self.data_dir)
        storico = self.conversazione(username)["messages"]
        tools = registry.schemi(ruolo, cantieri)
        messaggi: list[dict[str, Any]] = [
            {"role": "system", "content": self._istruzioni(manifest, ruolo, cantieri)},
            *[
                {"role": m["role"], "content": m["content"]}
                for m in storico
                if isinstance(m, dict) and m.get("role") in {"user", "assistant"}
                and isinstance(m.get("content"), str)
            ],
            {"role": "user", "content": domanda},
        ]
        usati: list[str] = []
        risposta_finale = RISPOSTA_FALLBACK
        esito = "ok"
        errore: str | None = None
        inizio = monotonic()
        chiamate_totali = 0
        try:
            for _ in range(MAX_GIRI_AGENTE):
                if monotonic() - inizio > TIMEOUT_RUN_SECONDI:
                    esito, errore = "errore", "tempo massimo del run raggiunto"
                    risposta_finale = RISPOSTA_FALLBACK
                    break
                risposta = self.gateway.complete(
                    tier=manifest.get("tier", "T2"),
                    messages=messaggi,
                    tools=tools or None,
                    tracer=tracer,
                    step="agente_dati",
                )
                if not risposta.tool_calls:
                    risposta_finale = _risposta_pubblica(
                        (risposta.text or "").strip() or RISPOSTA_NON_COPERTA
                    )
                    break
                messaggi.append(_messaggio_assistant(risposta))
                for chiamata in risposta.tool_calls:
                    chiamate_totali += 1
                    if chiamate_totali > MAX_TOOL_CALL_TOTALI:
                        esito, errore = "errore", "limite chiamate tool raggiunto"
                        risposta_finale = RISPOSTA_NON_COPERTA
                        break
                    usati.append(chiamata.name)
                    ok = True
                    try:
                        risultato = registry.esegui(
                            chiamata.name,
                            chiamata.arguments,
                            ruolo,
                            cantieri,
                        )
                    except ToolDatiError as exc:
                        ok, risultato = False, {"errore": str(exc)}
                    tracer.tool_call(
                        step="agente_dati",
                        name=chiamata.name,
                        args=chiamata.arguments,
                        result=risultato,
                        ok=ok,
                        messages=messaggi,
                        tools=tools,
                    )
                    messaggi.append(
                        {
                            "role": "tool",
                            "tool_call_id": chiamata.id,
                            "content": _testo_tool(risultato),
                        }
                    )
                if errore:
                    break
            else:
                risposta_finale = RISPOSTA_NON_COPERTA
                esito, errore = "errore", "limite giri tool raggiunto"
        except GatewayError as exc:
            logger.warning("agente dati non disponibile: %s", exc)
            esito, errore = "errore", str(exc)
        except Exception as exc:  # il contratto verso operatore resta non tecnico
            logger.exception("agente dati fallito")
            esito, errore = "errore", str(exc)

        tracer.run_end(esito, tools=usati, errore=errore)
        percorsi = [tracer.trace_path, _percorso_conversazione(self.data_dir, username)]
        if tracer.dataset_path.is_file():
            percorsi.append(tracer.dataset_path)
        try:
            # Rileggiamo sotto il lock del DAL: due invii simultanei dello
            # stesso utente non possono perdere uno scambio fra read e append.
            with self.dal._write_lock:
                percorso_chat = _percorso_conversazione(self.data_dir, username)
                corrente = self.conversazione(username)["messages"]
                conversazione = self._salva_conversazione(
                    username, corrente, domanda, risposta_finale, run_id
                )
                self.dal.commit_updates(
                    {
                        percorso_chat: json.dumps(
                            {"username": username, "messages": conversazione["messages"]},
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n"
                    },
                    include=[p for p in percorsi if Path(p).resolve() != percorso_chat.resolve()],
                    message=f"trace {run_id}: agente dati [{username}]",
                )
        except Exception as exc:
            logger.warning("commit agente dati fallito: %s", exc)
            conversazione = self._salva_conversazione(
                username, storico, domanda, risposta_finale, run_id
            )
        return {
            "answer": risposta_finale,
            "run_id": run_id,
            "messages": conversazione["messages"],
            "max_messages": conversazione["max_messages"],
            "used_tools": usati if ruolo == "admin" else [],
            "sources": registry.fonti_usate(usati) if ruolo == "admin" else [],
        }

    def _salva_conversazione(
        self, username: str, storico: list[dict[str, Any]], domanda: str, risposta: str, run_id: str
    ) -> dict[str, Any]:
        limite = configurazione(self.data_dir)["max_messages"]
        messaggi = _scambi_completi([
            *storico,
            {"role": "user", "content": domanda},
            {"role": "assistant", "content": risposta, "run_id": run_id},
        ], limite)
        return {"messages": messaggi, "max_messages": limite}

    def _manifest(self) -> dict[str, Any]:
        try:
            valore = yaml.safe_load((self.wf_dir / "manifest.yaml").read_text(encoding="utf-8"))
        except OSError as exc:
            raise AgenteDatiError(f"workflow agente non disponibile: {exc}") from exc
        return valore if isinstance(valore, dict) else {}

    def _istruzioni(self, manifest: dict[str, Any], ruolo: str, cantieri: list[str]) -> str:
        skills = manifest.get("skills") or {}
        file_agente = self.wf_dir / str(skills.get("agente", "skills/agente-dati.md"))
        file_stile = self.wf_dir / str(
            skills.get("risposta_operatore", "skills/risposta-operatore.md")
        )
        parti = [file_agente.read_text(encoding="utf-8"), file_stile.read_text(encoding="utf-8")]
        # Le skill aggiunte dall'Evolutore sono capacità approvate, separate dal
        # prompt principale per ridurre i conflitti e renderle ispezionabili.
        parti.extend(
            p.read_text(encoding="utf-8")
            for p in sorted((self.wf_dir / "skills").glob("agent-*.md"))
        )
        if ruolo == "op":
            parti.append(
                "La persona può vedere solo questi cantieri: " + ", ".join(cantieri or ["nessuno"])
            )
        else:
            parti.append("Stai rispondendo all'ufficio. Mantieni comunque la risposta chiara.")
        return "\n\n".join(parti)


class EvolutoreAgente:
    """Proposte deliberate di nuovi tool/skill, sempre con approvazione umana."""

    def __init__(self, dal: DAL, gateway: Gateway) -> None:
        self.dal = dal
        self.data_dir = Path(dal.data_dir)
        self.gateway = gateway
        self.base = self.data_dir / "agent_proposals"

    def elenco(self) -> list[dict[str, Any]]:
        proposte = []
        for percorso in sorted(self.base.glob("AGENT-*.json"), reverse=True):
            proposte.append(_leggi_json(percorso, {}))
        return [p for p in proposte if p]

    def proponi(self, feedback: str, creato_da: str) -> dict[str, Any]:
        if not feedback.strip():
            raise AgenteDatiError("descrivi cosa manca o cosa vorresti migliorare")
        wf = self.data_dir / "workflows" / "interroga"
        skill = (wf / "skills" / "evolvi-agente.md").read_text(encoding="utf-8")
        registry = RegistryToolDati(self.data_dir)
        contesto = "\n".join(
            f"- {tool['name']}: {tool['description']}"
            for tool in registry.elenco("admin", [])
        )
        fonti = "\n".join(f"- {nome}: {dati['etichetta']}" for nome, dati in _FONTI.items())
        segnali = self._segnali_osservati()
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        tracer = Tracer(self.data_dir, run_id, "evolvi-agente", "1.0")
        tracer.run_start(feedback, catalog_hash=impronta_catalogo(self.data_dir))
        try:
            risposta = self.gateway.complete(
                tier="T1",
                messages=[
                    {"role": "system", "content": skill},
                    {
                        "role": "user",
                        "content": (
                            f"Feedback: {feedback}\n\nTool già disponibili:\n{contesto}"
                            f"\n\nFonti semantiche approvate:\n{fonti}"
                            f"\n\nLacune e segnali recenti:\n{segnali}"
                        ),
                    },
                ],
                tracer=tracer,
                step="proposta_agente",
            )
        except Exception:
            tracer.run_end("errore")
            self.dal.commit_paths([tracer.trace_path], f"trace {run_id}: evoluzione agente")
            raise
        generata = estrai_json(risposta.text or "")
        if not isinstance(generata, dict) or not (generata.get("tool") or generata.get("skill")):
            raise AgenteDatiError("la proposta non contiene né un tool né una skill")
        tool = generata.get("tool")
        compilazione = self._verifica_tool(tool) if tool else {"ok": True, "righe": 0}
        if generata.get("skill"):
            verifica_skill = self._verifica_skill(generata["skill"])
            if not verifica_skill["ok"]:
                compilazione = verifica_skill
        replay = self._replay_golden()
        self.base.mkdir(parents=True, exist_ok=True)
        with self.dal._write_lock:
            numeri = [
                int(percorso.stem.split("-")[-1])
                for percorso in self.base.glob("AGENT-*.json")
                if percorso.stem.split("-")[-1].isdigit()
            ]
            proposta = {
            "id": f"AGENT-{max(numeri, default=0) + 1:04d}",
            "stato": "proposta",
            "feedback": feedback,
            "analisi": str(generata.get("analisi", "")),
            "motivazione": str(generata.get("motivazione", "")),
            "intenti": generata.get("intenti", []),
            "parametri": generata.get("parametri", []),
            "esempi": generata.get("esempi", []),
            "risultato_atteso": str(generata.get("risultato_atteso", "")),
            "tool": tool,
            "skill": generata.get("skill"),
            "compilazione": compilazione,
            "replay": replay,
            "creato_da": creato_da,
            "run_id": run_id,
            "catalog_hash": impronta_catalogo(self.data_dir),
            }
            percorso = self.base / f"{proposta['id']}.json"
            tracer.run_end("ok", proposal_id=proposta["id"])
            self.dal.commit_updates(
                {percorso: json.dumps(proposta, ensure_ascii=False, indent=2) + "\n"},
                include=[tracer.trace_path],
                message=f"agente dati: proposta {proposta['id']} [{creato_da}]",
            )
        return proposta

    def _segnali_osservati(self) -> str:
        """Input dell'evolutore da trace tool-first e golden correnti, mai da archivio storico."""
        from app.core.golden_agente import casi

        esempi: list[str] = []
        for percorso in sorted((self.data_dir / "traces").glob("*/*/*.jsonl"), reverse=True):
            avvio: dict[str, Any] | None = None
            fine: dict[str, Any] | None = None
            try:
                eventi = [json.loads(riga) for riga in percorso.read_text(encoding="utf-8").splitlines() if riga]
            except (OSError, json.JSONDecodeError):
                continue
            for evento in eventi:
                if evento.get("evento") == "run_start" and evento.get("workflow") == "interroga":
                    avvio = evento
                elif evento.get("evento") == "run_end":
                    fine = evento
            if avvio and avvio.get("catalog_hash") and fine and fine.get("outcome") == "errore":
                domanda = avvio.get("input")
                if isinstance(domanda, str):
                    esempi.append(f"- richiesta non soddisfatta: {domanda[:240]}")
            if len(esempi) >= 8:
                break
        golden = casi(self.data_dir)
        coperti = sum(len(caso.get("tool_calls", [])) for caso in golden)
        parti = [f"- golden agent-native disponibili: {len(golden)} ({coperti} chiamate attese)", *esempi]
        return "\n".join(parti)

    def approva(self, proposal_id: str, deciso_da: str) -> dict[str, Any]:
        """Approva con lettura, collaudo e pubblicazione serializzati dal DAL."""
        if not _ID_PROPOSTA.fullmatch(proposal_id):
            raise AgenteDatiError("identificativo proposta non valido")
        with self.dal._write_lock:
            return self._approva_bloccata(proposal_id, deciso_da)

    def _approva_bloccata(self, proposal_id: str, deciso_da: str) -> dict[str, Any]:
        if not _ID_PROPOSTA.fullmatch(proposal_id):
            raise AgenteDatiError("identificativo proposta non valido")
        percorso = self.base / f"{proposal_id}.json"
        proposta = _leggi_json(percorso, {})
        if not proposta or proposta.get("stato") != "proposta":
            raise AgenteDatiError("proposta non disponibile")
        # Il giudizio precedente e' solo informativo: prima della pubblicazione
        # collaudiamo di nuovo sul catalogo e sui golden correnti.
        compilazione = self._verifica_tool(proposta.get("tool")) if proposta.get("tool") else {"ok": True, "righe": 0}
        if proposta.get("skill"):
            compilazione = self._verifica_skill(proposta["skill"])
        replay = self._replay_golden()
        if not compilazione.get("ok"):
            raise AgenteDatiError("il test mirato del tool non è verde: proposta non pubblicabile")
        if not int(replay.get("totale", 0)) or int(replay.get("falliti", 0)):
            raise AgenteDatiError(
                "il replay golden non è verde o non ha casi: proposta non pubblicabile"
            )
        aggiornati = [percorso]
        if proposta.get("tool"):
            registry_path = self.data_dir / "workflows" / "interroga" / "tools.yaml"
            documento = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {"tools": []}
            tools = documento.setdefault("tools", [])
            if any(t.get("name") == proposta["tool"]["name"] for t in tools if isinstance(t, dict)):
                raise AgenteDatiError("esiste già un tool con questo nome")
            tools.append(proposta["tool"])
            testo_registry = yaml.safe_dump(
                documento,
                allow_unicode=True,
                sort_keys=False,
            )
            aggiornati.append(registry_path)
        if proposta.get("skill"):
            skill = proposta["skill"]
            verifica_skill = self._verifica_skill(skill)
            if not verifica_skill["ok"]:
                raise AgenteDatiError("skill proposta non valida")
            nome = skill.get("name") if isinstance(skill, dict) else None
            testo = skill.get("content") if isinstance(skill, dict) else None
            if (
                not isinstance(nome, str)
                or not _NOME_SICURO.fullmatch(nome)
                or not isinstance(testo, str)
            ):
                raise AgenteDatiError("skill proposta non valida")
            skill_path = (
                self.data_dir
                / "workflows"
                / "interroga"
                / "skills"
                / f"agent-{nome}.md"
            )
            aggiornati.append(skill_path)
        manifest_path = self.data_dir / "workflows" / "interroga" / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        versione = str(manifest.get("version", "2.0"))
        try:
            maggiore, minore = (int(v) for v in versione.split(".", 1))
        except ValueError:
            maggiore, minore = 2, 0
        manifest["version"] = f"{maggiore}.{minore + 1}"
        proposta.update(
            {
                "stato": "approvata",
                "deciso_da": deciso_da,
                "compilazione": compilazione,
                "replay": replay,
                "versione_pubblicata": manifest["version"],
            }
        )
        testo_manifest = yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
        aggiornamenti: dict[Path, str] = {
            percorso: json.dumps(proposta, ensure_ascii=False, indent=2) + "\n",
            manifest_path: testo_manifest,
        }
        if proposta.get("tool"):
            aggiornamenti[registry_path] = testo_registry
        if proposta.get("skill"):
            aggiornamenti[skill_path] = testo.strip() + "\n"
        proposta["catalog_hash_approvazione"] = impronta_catalogo(
            self.data_dir,
            {p: contenuto for p, contenuto in aggiornamenti.items() if p != percorso},
        )
        aggiornamenti[percorso] = json.dumps(proposta, ensure_ascii=False, indent=2) + "\n"
        self.dal.commit_updates(
            aggiornamenti,
            message=f"agente dati: approva {proposal_id} [{deciso_da}]",
        )
        return proposta

    def rifiuta(self, proposal_id: str, deciso_da: str) -> dict[str, Any]:
        if not _ID_PROPOSTA.fullmatch(proposal_id):
            raise AgenteDatiError("identificativo proposta non valido")
        with self.dal._write_lock:
            return self._rifiuta_bloccata(proposal_id, deciso_da)

    def _rifiuta_bloccata(self, proposal_id: str, deciso_da: str) -> dict[str, Any]:
        if not _ID_PROPOSTA.fullmatch(proposal_id):
            raise AgenteDatiError("identificativo proposta non valido")
        percorso = self.base / f"{proposal_id}.json"
        proposta = _leggi_json(percorso, {})
        if not proposta or proposta.get("stato") != "proposta":
            raise AgenteDatiError("proposta non disponibile")
        proposta.update({"stato": "rifiutata", "deciso_da": deciso_da})
        self.dal.commit_updates(
            {percorso: json.dumps(proposta, ensure_ascii=False, indent=2) + "\n"},
            message=f"agente dati: rifiuta {proposal_id} [{deciso_da}]",
        )
        return proposta

    def _replay_golden(self) -> dict[str, int]:
        """Rigioca tool, argomenti e risultati normalizzati dei golden agente."""
        from app.core.golden_agente import casi, impronta_risultato

        totale = falliti = 0
        registry = RegistryToolDati(self.data_dir)
        for caso in casi(self.data_dir):
            totale += 1
            try:
                for chiamata in caso.get("tool_calls", []):
                    risultato = registry.esegui(
                        chiamata["name"],
                        chiamata.get("arguments", {}),
                        caso.get("role", "admin"),
                        caso.get("cantieri", []),
                    )
                    if impronta_risultato(risultato) != chiamata.get("result_hash"):
                        raise AgenteDatiError("risultato golden diverso")
            except Exception:
                falliti += 1
        return {"totale": totale, "ok": totale - falliti, "falliti": falliti}

    def _verifica_tool(self, tool: Any) -> dict[str, Any]:
        """Compila ed esegue un caso mirato prima che l'ufficio possa approvarlo."""
        try:
            RegistryToolDati.valida_spec(tool)
            if not isinstance(tool, dict):  # rende esplicito il tipo a mypy/lettori
                raise AgenteDatiError("tool proposto non valido")
            test = tool.get("test")
            if not isinstance(test, dict):
                raise AgenteDatiError("manca il test mirato del tool")
            argomenti = test.get("arguments", {})
            ruolo = test.get("role", "admin")
            cantieri = test.get("cantieri", [])
            minimo = test.get("min_results", 1)
            if not isinstance(argomenti, dict) or ruolo not in {"op", "admin"}:
                raise AgenteDatiError("test mirato non valido")
            if not isinstance(cantieri, list) or not all(isinstance(c, str) for c in cantieri):
                raise AgenteDatiError("cantieri del test non validi")
            if not isinstance(minimo, int) or minimo < 0:
                raise AgenteDatiError("min_results del test non valido")
            risultato = RegistryToolDati(self.data_dir).esegui_spec(
                tool,
                argomenti,
                ruolo,
                cantieri,
            )
            righe = len(risultato["risultati"])
            if righe < minimo:
                raise AgenteDatiError(
                    f"test mirato: attese almeno {minimo} righe, trovate {righe}"
                )
            if tool.get("scope") == "cantiere" and "op" in tool.get("roles", []):
                prova_cantieri = cantieri or ["CNT-001"]
                protetto = RegistryToolDati(self.data_dir).esegui_spec(
                    tool, argomenti, "op", prova_cantieri
                )
                if any(
                    r.get(tool.get("scope_column", "cantiere_id")) not in prova_cantieri
                    for r in protetto["risultati"]
                ):
                    raise AgenteDatiError("il collaudo operatore ha superato il perimetro cantiere")
            return {"ok": True, "righe": righe, "minimo": minimo}
        except (AgenteDatiError, ToolDatiError, duckdb.Error) as exc:
            return {"ok": False, "errore": str(exc)}

    @staticmethod
    def _verifica_skill(skill: Any) -> dict[str, Any]:
        """Controlla che una skill approvabile non reintroduca dettagli tecnici."""
        if not isinstance(skill, dict):
            return {"ok": False, "errore": "skill proposta non valida"}
        nome = skill.get("name")
        testo = skill.get("content")
        if not isinstance(nome, str) or not _NOME_SICURO.fullmatch(nome):
            return {"ok": False, "errore": "nome skill non valido"}
        if not isinstance(testo, str) or not testo.strip():
            return {"ok": False, "errore": "testo skill mancante"}
        if _INDIZIO_IMPLEMENTAZIONE.search(testo):
            return {"ok": False, "errore": "dettagli implementativi non ammessi nella skill"}
        return {"ok": True, "righe": 0}
