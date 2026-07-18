# Workflower — Piano di implementazione v1 (per Claude Code)

> **Istruzioni per l'agente**: questo piano genera la prima versione funzionante (PoC F1) del sistema descritto in `analisi-progettazione.md` (leggilo prima di iniziare; `mockup.html` è il riferimento UX). Esegui le milestone **in ordine**: ognuna termina con test verdi e un commit. Non saltare i criteri di accettazione. In caso di dubbio scegli la soluzione più semplice che rispetta le ADR (§7 dell'analisi).

## 0. Obiettivo della v1

Giro completo end-to-end del workflow **carica-fattura** con **due modalità UI** (Operatore mobile-first, Admin) e ciclo di auto-miglioramento minimo:

upload PDF/foto → estrazione LLM → bozza JSON validata contro schema → revisione Admin (o conferma semplice Operatore) → feedback/segnalazione → proposta patch dell'Improver → replay su golden set → approvazione → nuova versione del workflow → ri-esecuzione corretta → dato nel cruscotto.

## 1. Stack (vincolante)

| Livello | Scelta | Note |
|---|---|---|
| Backend | Python 3.12, FastAPI + uvicorn | API REST, no GraphQL |
| Validazione | pydantic v2 + jsonschema | envelope in pydantic, schemi entità in JSON Schema |
| LLM | **litellm** (SDK) | model-agnostic; tier T1/T2 da env, mai modelli hard-coded |
| Query | **duckdb** (pacchetto pip) | viste su file JSON, read-only per le query |
| PDF | pymupdf | render pagine → PNG → LLM multimodale |
| Versioning dati | GitPython | auto-commit su ogni mutazione in `/data` |
| Frontend | React 18 + Vite + TypeScript + Tailwind | due layout separati: `/op` (mobile-first) e `/admin` |
| Auth v1 | login locale (`data/config/users.json`, password hash) + JWT | interfaccia `AuthProvider` astratta, predisposta per Entra ID (non implementare Entra) |
| Test | pytest + httpx (backend); il frontend si testa manualmente in v1 | |
| Nessun database server, nessun Redis, nessun ORM | | ADR-1 |

## 2. Struttura repository

```
workflower/
├── CLAUDE.md                    # convenzioni per l'agente (vedi §8)
├── Makefile                     # dev, test, seed, demo
├── .env.example
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py              # FastAPI, mount /api
│   │   ├── api/                 # routers: auth, documents, review, issues, dashboard, ask, workflows, admin
│   │   ├── core/
│   │   │   ├── dal.py           # Data Access Layer: CRUD envelope su file, lock, git-commit
│   │   │   ├── views.py         # catalogo viste DuckDB (v_fatture, v_cantieri, …)
│   │   │   ├── gateway.py       # wrapper litellm: complete(tier, messages, tools, response_schema)
│   │   │   ├── runtime.py       # esecutore workflow: carica manifest YAML, esegue step, valida
│   │   │   ├── tracer.py        # trace JSONL per run + logging tool call (dataset)
│   │   │   ├── improver.py      # analisi trace+feedback → proposta patch → replay golden set
│   │   │   └── tools/           # tool nativi: ocr_pdf, cerca_fornitore, cerca_cantiere, salva_bozza
│   │   └── models/              # pydantic: Envelope, Run, Patch, Issue, User
│   └── tests/
├── frontend/
│   └── src/
│       ├── op/                  # modalità Operatore: Home, Carica, Documenti, Chiedi
│       ├── admin/               # Cruscotto, Revisione, Segnalazioni, Interroga, Workflows, Log
│       └── shared/              # api client, auth, componenti
└── data/                        # SoT — repo git SEPARATO, creato da `make seed`
    ├── entities/{cantieri,fornitori,fatture/2026}/
    ├── blobs/fatture/2026/
    ├── schemas/                 # cantiere|fornitore|fattura .schema.json
    ├── workflows/carica-fattura/
    │   ├── manifest.yaml        # versionato: name, version, steps, rules, threshold
    │   └── skills/estrazione-fattura.md
    ├── traces/2026/07/run-*.jsonl
    ├── golden/                  # run validati per replay di regressione
    ├── dataset/toolcalls.jsonl  # log function calling per futuro fine-tuning
    ├── issues/                  # segnalazioni operatori
    └── config/{users.json,views.sql}
```

## 3. Contratti fondamentali (non derogare)

### 3.1 Envelope entità (ogni file in `data/entities/**`)

```json
{
  "id": "FT-2026-0001",
  "tipo": "fattura",
  "schema_version": "1.0",
  "stato": "bozza|validato|errore",
  "dati": { "...conforme a schemas/<tipo>.schema.json..." },
  "meta": {
    "origine": "blobs/…", "workflow": "carica-fattura@1.0",
    "run_id": "run-…", "confidence": {"campo": 0.97},
    "created": "ISO8601", "updated": "ISO8601", "validato_da": null
  }
}
```

Regole DAL: scritture **solo** tramite `dal.py` (coda single-writer con lock per cantiere); ogni scrittura = git commit su `data/` con messaggio `"{tipo} {id}: {azione} [{run_id}]"`; `stato=validato` impostabile solo da endpoint admin.

### 3.2 Manifest workflow (`data/workflows/*/manifest.yaml`)

```yaml
name: carica-fattura
version: "1.0"            # semver; bump gestito da improver + approvazione
tier: T1
steps:
  - id: estrai
    skill: skills/estrazione-fattura.md
    tools: [ocr_pdf, cerca_fornitore, cerca_cantiere]
    output_schema: schemas/fattura.schema.json
  - id: valida
    rules:                 # espressioni valutate dal runtime (no eval libero: mini-parser o simpleeval)
      - "abs(dati.totale - (dati.imponibile + dati.iva)) < 0.01"
      - "dati.data <= today()"
    on_fail: retry_T1_once_then_flag
  - id: salva
    action: save_draft
confidence_threshold: 0.90
```

### 3.3 Trace (un JSONL per run in `data/traces/`)

Eventi: `run_start`, `llm_call` (tier, model, messages_digest, tokens, cost, latency), `tool_call` (name, args, result, ok — **duplicato anche in `dataset/toolcalls.jsonl`**), `validation`, `run_end` (outcome). Il trace è la materia prima di Improver e dataset: non risparmiare campi.

### 3.4 API REST (prefisso `/api`)

```
POST /auth/login                        → JWT {role: operatore|admin, cantieri:[...]}
POST /documents                          upload multipart (pdf/jpg/png) → {run_id, doc_id} — MAI errore bloccante:
                                         se il workflow fallisce → stato=errore + issue automatica "ci pensa l'ufficio"
GET  /documents?mine=1                   elenco per operatore (stato semaforo derivato)
GET  /documents/{id}                     dettaglio (admin: envelope completo; operatore: vista semplificata)
POST /documents/{id}/confirm             operatore: "è tutto giusto" → nota sul run (non valida!)
POST /documents/{id}/issue               operatore: "qualcosa non torna" {text} → data/issues/ + aggancio trace
POST /review/{id}/feedback               admin: feedback puntuale per campo {field, note}
POST /review/{id}/validate               admin: bozza → validato (+ copia run nel golden set)
GET  /issues                             admin: coda segnalazioni
GET  /dashboard/costs                    aggregati da viste DuckDB
POST /ask                                {question, mode: op|admin} → op: risposta in italiano semplice;
                                         admin: {sql, rows} — guardrail: SOLO SELECT su viste, LIMIT 1000, timeout 10s
GET  /workflows                          elenco manifest + versioni + stats run
POST /workflows/{name}/improve           avvia Improver su {run_id|issue_id} → Patch (diff skill/manifest + replay golden)
POST /patches/{id}/approve|reject        approve: applica diff, bump version, git commit; reject: archivia
GET  /runs/{id}/trace                    admin only
```

RBAC: middleware su ruolo + filtro cantieri; l'operatore non può chiamare endpoint admin (403).

## 4. Milestone

### M0 — Scaffolding
Repo, backend healthcheck, frontend vuoto con routing `/op` e `/admin`, Makefile (`dev`, `test`, `seed`), `.env.example` (`LLM_T1_MODEL`, `LLM_T2_MODEL`, chiavi provider, `DATA_DIR`, `JWT_SECRET`), CI-ready lint (ruff, eslint).
**AC**: `make dev` avvia tutto; `GET /api/health` → 200; entrambe le route frontend renderizzano.

### M1 — Storage layer
DAL completo (CRUD envelope, lock, git auto-commit), JSON Schema per `cantiere`, `fornitore`, `fattura`; `make seed` crea il repo `data/` con 3 cantieri, 8 fornitori, 5 fatture validate di esempio; `views.py` con `v_cantieri`, `v_fornitori`, `v_fatture` (+ `v_fatture_righe`) da `data/config/views.sql`.
**AC**: pytest: CRUD + validazione schema + commit git verificato; `SELECT * FROM v_fatture` restituisce il seed; scritture concorrenti serializzate (test con thread).

### M2 — Gateway + runtime + workflow carica-fattura
`gateway.py` (litellm, tier da env, structured output via JSON Schema, retry, log costi nel trace); `tracer.py`; tool nativi (`ocr_pdf` con pymupdf→PNG, `cerca_fornitore`/`cerca_cantiere` fuzzy su seed, `salva_bozza` via DAL); `runtime.py` esegue il manifest §3.2; skill `estrazione-fattura.md` in italiano (campi, regole IVA/ritenuta d'acconto, "se assente → null esplicito"); script `make fixtures` che genera 3 PDF fattura sintetici (reportlab) di cui uno **con ritenuta d'acconto in calce**.
**AC**: pytest e2e: upload fixture → bozza conforme allo schema, confidence per campo presente, trace completo, riga in `dataset/toolcalls.jsonl`; workflow che fallisce → `stato=errore` + issue automatica, mai eccezione all'utente.

### M3 — UI Operatore ("a prova di cantiere")
Home 3 bottoni giganti (Carica / I miei documenti / Chiedi); Carica: camera/file → "⏳ Sto leggendo…" → riepilogo in 3 righe → "È tutto giusto?" [👍/👎]; 👎 → textarea → `POST /issue` → "🤝 Grazie! Ci pensiamo noi"; Documenti a semaforo 🟢🟡🔴; Chiedi → `POST /ask mode=op` → solo risposta in italiano.
**Vincoli**: touch ≥ 48px, font ≥ 17px, zero termini tecnici (mai: workflow, JSON, confidence, bozza), zero form, una domanda alla volta, nessun errore bloccante. Riferimento: `mockup.html` modalità Operatore.
**AC**: flusso completo da viewport 390×844; nessuna stringa tecnica nella UI operatore (test grep su bundle: `workflow|json|confidence` assenti dalle stringhe utente).

### M4 — UI Admin
Cruscotto (KPI + costi per cantiere da `/dashboard/costs`); Revisione (originale a fianco dei campi estratti + confidence, vista JSON toggle, feedback per campo, "Salva come validato"); Segnalazioni (coda issues, link al trace e alla revisione); Interroga (domanda → SQL mostrato + tabella); Workflows (elenco, versioni, changelog).
**AC**: giro del mockup riprodotto con dati veri; guardrail `/ask` testati (INSERT/UPDATE/DROP rifiutati, LIMIT forzato).

### M5 — Ciclo Improver (cuore del sistema)
`improver.py`: input = run + feedback/issue → T1 genera **Patch** strutturata `{analisi, diff_skill (unified diff), diff_manifest?, motivazione}`; replay: riesegue il workflow patchato sui run del `golden/` (LLM-as-judge T2 confronta output vs output validato) → report N/N; UI Admin: pannello patch con diff colorato + esito replay + Approva/Rifiuta; approve → applica diff, bump minor version, git commit, il doc origine è rieseguibile con la nuova versione.
**AC**: test e2e "scenario ritenuta": fixture con ritenuta → v1.0 non la estrae → issue operatore → improve → patch che aggiunge la ritenuta alla skill → replay golden OK → approve → v1.1 → re-run estrae la ritenuta. Questo test è la **definition of done** della v1.

### M6 — Hardening + demo
RBAC per cantiere ovunque; pagina Log & Dataset (conteggi, costo per documento, export `toolcalls.jsonl`); contatore fingerprint delle query generate da `/ask` (solo conteggio duplicati simili — **niente Toolsmith automatico in v1**); README con quickstart; `make demo` (seed + fixtures + istruzioni giro demo).
**AC**: `make demo` porta un utente nuovo al giro completo in < 10 minuti; tutti i test verdi.

## 5. Non-goals v1 (non implementare)

Toolsmith/consolidamento automatico (solo contatori) · fine-tuning FunctionGemma (solo raccolta dataset) · integrazioni M365/Graph · Redis · DDT/SAL/ore (solo fattura; ma schemi e runtime devono essere generici: aggiungere un'entità = aggiungere schema + manifest, zero codice nuovo nel runtime) · notifiche push · multi-tenant · i18n.

## 6. Qualità e stile

Type hints ovunque; funzioni < 50 righe; niente singleton globali (dependency injection FastAPI); i prompt delle skill in italiano e **nei file di `data/`, mai hard-coded nel codice**; errori: mai stacktrace all'utente (operatore: "ci pensiamo noi"; admin: dettaglio tecnico); commit convenzionali (`feat:`, `fix:`, `test:`); ogni milestone → commit dedicato con test verdi.

## 7. Rischi implementativi noti

- **Structured output**: usare `response_format`/tool-use nativo via litellm dove il provider lo supporta, altrimenti JSON-mode + reparse con retry (max 2).
- **DuckDB su file in scrittura**: aprire connessioni read-only per query; le viste rileggono i file a ogni query (no cache) — a questa scala va bene.
- **Replay golden set**: costi contenuti — max 20 run nel golden, campionare se di più.
- **simpleeval per le rules**: whitelist funzioni (`abs`, `today`), nessun accesso a builtins.

## 8. Contenuto di CLAUDE.md (crearlo in M0)

```markdown
# Workflower
Sistema LLM-driven per controllo costi cantieri. Leggere: analisi-progettazione.md, piano-implementazione.md.
## Regole
- /data è la fonte di verità: mai stato applicativo fuori da /data. Ogni mutazione = git commit.
- Nessun DB server. DuckDB solo read-only per query. Scritture solo via dal.py.
- Modelli LLM mai hard-coded: tier T1/T2 da env via gateway.py.
- Prompt e skill vivono in data/workflows/*/skills/*.md, in italiano.
- UI Operatore: mai termini tecnici, zero form, una domanda alla volta.
- Test: pytest per ogni milestone; lo scenario "ritenuta d'acconto" (M5) non deve mai rompersi.
## Comandi
make dev | make test | make seed | make fixtures | make demo
```
