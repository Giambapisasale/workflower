# Workflower — Piano di implementazione: Integrazione ERP (ERPNext) (M22–M29)

> **Contesto**: le Fasi F1 (M0–M6), F2 (M7–M13) e F3 (M14–M21) sono completate e verdi. L'analisi
> `analisi-integrazione-erp.md` ha stabilito la soluzione: **ERPNext come sistema di record contabile
> a valle del ciclo passivo**, alimentato dai documenti già validati dall'umano, con sincronizzazione
> **mono-direzionale WF→ERP** tramite anti-corruption layer, più **read-back in sola lettura** dello
> stato di pagamento. Questo piano la traduce in milestone eseguibili.
>
> **Scelte di indirizzo** (confermate): ciclo **solo passivo**; ERP come **sistema di record a valle**
> (Workflower resta il front LLM); priorità **open source puro / no lock-in** (→ ERPNext, GPLv3);
> trigger sync **automatico alla validazione + re-sync manuale**; ampiezza **track passivo completo**.
>
> Valgono tutte le regole di `CLAUDE.md`: `/data` è la fonte di verità (ogni mutazione = commit),
> scritture solo via `dal.py`, DuckDB read-only, modelli LLM mai hard-coded (tier da env), prompt/skill
> in italiano dentro `data/workflows/**`, UI Operatore senza termini tecnici, **pytest verde a ogni
> milestone**, e — non negoziabile — lo scenario "ritenuta d'acconto" (M5) non si rompe mai. Ogni
> milestone termina con un commit dedicato.
>
> **Numerazione**: F1=M0–M6, F2=M7–M13, F3=M14–M21 → questo track parte da **M22**. È una fase a sé
> ("Integrazione ERP"), da non confondere con la F4 concettuale (M365/SSO/LoRA), non ancora pianificata.

---

## 0. Obiettivo del track

Rendere **ERPNext il system-of-record contabile a valle** per il ciclo passivo: ogni documento
(`fattura`, `ddt`) che l'umano valida in Workflower viene riflesso in ERPNext come record contabile
(Purchase Invoice / Purchase Receipt), con lo stato di pagamento riletto da ERPNext e mostrato nel
cost-control. Tutto questo **senza toccare la cornice** `runtime.py`/`gateway.py`/`dal.py` (salvo i
punti-dato previsti: una riga in `ENTITY_TYPES`, due campi nel `Meta`), e **senza** che l'ERP diventi
lo store di Workflower o entri in-process.

**MVP di produzione = M22–M25** (stand-up + sync fornitore/fattura verde). M26–M29 = estensioni.

## 1. Principio guida (invariante del track)

> L'ERP è un **sistema esterno**: Workflower non guadagna un DB, non importa codice ERPNext
> in-process, e **non espone mai la scrittura ERP al modello** (ADR-4 — il modello non scrive). La
> sincronizzazione è un **effetto della validazione umana**, best-effort, idempotente e tracciato: un
> suo fallimento diventa una issue ("ci pensa l'ufficio") e mai un blocco della validazione. Il
> **mapping è dato testabile** (funzioni pure); il flusso dati è **mono-direzionale** WF→ERP, con solo
> un read-back in lettura per lo stato di pagamento. `runtime.py`/`gateway.py` restano invariati.

## 2. Milestone

### M22 — Ambiente ERPNext + PoC di mappatura (go/no-go)
**Perché**: prima di scrivere codice in Workflower bisogna *provare che il mapping regge* — in
particolare la `fattura` con **ritenuta d'acconto** → Purchase Invoice + *Tax Withholding*, e
l'imputazione del costo al `cantiere`. È la Fase 0 dell'analisi (§9): un cancello go/no-go.

- Ambiente ERPNext di sviluppo come **deploy separato** (docker: MariaDB + Redis + bench), trattato
  da subito come dipendenza esterna.
- Runbook manuale via REST che crea a mano un **Supplier** e una **Purchase Invoice** (con withholding)
  a partire da una `fattura` del seed, incluso il caso della ritenuta in calce.
- Verifica dello stato/manutenzione dell'app SdI community (`mascor/erpnext_fattura_elettronica`) e
  della gestione nativa *Tax Withholding* per la ritenuta.
- **AC**: il PoC dimostra `fornitore→Supplier` e `fattura(ritenuta)→Purchase Invoice + cost center`;
  è documentato in `docs/erp-poc.md`; la decisione go/no-go è registrata. **Zero codice applicativo**
  in Workflower in questa milestone.

### M23 — Config ERP + client HTTP iniettabile (cornice minima)
**Perché**: dare a Workflower un modo *isolato e testabile* di parlare con l'ERP, senza accoppiamento
e senza segreti hard-coded (stesso principio dei tier LLM da env).

- Nuovo modulo `core/erp.py`: `ErpConfig` letta da env `ERP_BASE_URL`/`ERP_API_KEY`/`ERP_API_SECRET`,
  con `erp_attivo()` analogo a `gateway.t3_attivo()` → se non configurato, la sync è **no-op silenziosa**.
- `ErpClient` su **httpx** con **transport iniettabile** (pattern `Gateway(completer=...)`): default
  reale, nei test un finto. Timeout corti; errori HTTP/trasporto tradotti in un'eccezione dedicata.
- Costruzione una-tantum e iniezione via `deps.py`/`app.state` come il `Gateway`.
- `httpx>=0.28` promosso da dipendenza `dev` a **runtime** in `backend/pyproject.toml`.
- **AC**: il client è costruibile da env; un test con transport finto (nessun ERP reale) è verde;
  in assenza di config la sync è no-op. La suite resta verde.

### M24 — Anti-corruption layer: Translator (envelope→DocType) come dato testabile
**Perché**: isolare il **mapping** — la parte fragile — in funzioni pure, così il modello ERPNext non
"trapela" negli schemi di `/data` e ogni regola di conversione è verificabile con test tabellari.

- Funzioni pure, deterministiche e senza I/O in `core/erp.py`: `fornitore→Supplier`,
  `fattura→Purchase Invoice + items + taxes`, con `ritenuta_acconto → Tax Withholding`,
  `cantiere→Cost Center/Project`; le righe portano `voce_computo_id`/`mezzo_id`/`tipo_costo`.
- **AC**: test tabellari sui payload prodotti, incluso il **caso ritenuta** (→ withholding) e il
  vincolo `totale ≈ imponibile + iva`; la traduzione è pura (nessun I/O). La regressione ritenuta
  (`test_improver_e2e.py::test_scenario_ritenuta`) resta intatta. Suite verde.

### M25 — Sync fornitore + fattura alla validazione (mono-direzionale, idempotente)
**Perché**: chiudere il ciclo minimo — un documento validato **compare in ERPNext** come record
contabile — riusando il precedente degli effetti post-validazione già presenti nella revisione.

- Facade `sincronizza(dal, envelope, erp)` (upsert Supplier → upsert Purchase Invoice), agganciata in
  `api/review.py::valida()` subito dopo `dal.set_validato(...)`, **best-effort** accanto a
  `registra_derivazione(...)` e `_forse_golden(...)`.
- Idempotenza + audit via ledger append-only `data/dataset/erp_sync.jsonl` (nuova `dataset.registra_sync_erp`,
  stile `registra_query` + `dal.commit_paths`); chiave idempotente (fornitore+numero+anno / `envelope_id`).
- Backref sull'envelope: nuovi campi espliciti `Meta.erp_id` / `Meta.erp_synced`
  (`Meta` è `extra="forbid"` → è l'**unico tocco al model layer**), persistiti via `dal.update`.
- Su errore: `dal.crea_issue("auto", "Sync ERP fallita per FT-…: <err>", entity_id=…, run_id=…)` +
  riga `esito="errore"` nel ledger; **la validazione resta valida**.
- **AC**: e2e con **ERP finto** — dopo `POST /review/{id}/validate` compaiono commit su `meta`
  (`erp_id`/`erp_synced`) + riga nel ledger; una seconda validazione è **idempotente** (nessun doppione);
  su errore simulato nasce l'issue e la validazione regge. Suite verde.

### M26 — Estensione documenti: DDT→Purchase Receipt; cantiere→Cost Center/Project
**Perché**: estendere il ciclo passivo oltre la fattura, con l'anagrafica cantiere allineata *prima*
dei documenti così i costi cadono sul centro di costo giusto.

- Translator + sync per `ddt`→Purchase Receipt; upsert `cantiere`→Cost Center/Project come passo
  preliminare della sincronizzazione dei documenti.
- **AC**: un `ddt` validato genera una Purchase Receipt tracciata nel ledger; i costi sono imputati al
  cost center corretto. Suite verde.

### M27 — Read-back stato pagamento (entità `pagamento`, puro dato)
**Perché**: completare il quadro cost-control con lo stato di pagamento **senza** aprire un canale di
scrittura ERP→WF su `/data` come master (solo lettura). Riprova l'invariante "aggiungere un'entità = dati".

- Nuova entità `pagamento` come **puro dato**: schema in `seed_assets/schemas/pagamento.schema.json`,
  **una riga** in `ENTITY_TYPES` (registry-dato), vista `v_pagamenti` in `views.sql`; **nessun workflow**.
- Endpoint/job admin che interroga ERPNext (Payment Entry) per le fatture presenti nel ledger e
  crea/aggiorna il `pagamento` via `dal.crea_progressivo`/`dal.update`. Flusso ERP→WF di **sola lettura**.
- **AC**: dato lo stato "pagato" su ERP, Workflower crea/aggiorna il `pagamento`, visibile in
  registro/cruscotto; **zero modifiche** a `runtime.py`/`gateway.py`/`dal.py` salvo la riga
  `ENTITY_TYPES`. Suite verde.

### M28 — Osservabilità, resilienza e re-sync manuale
**Perché**: rendere l'integrazione *operabile* — recuperare i fallimenti e non farsi bloccare da un
ERP momentaneamente irraggiungibile.

- Endpoint admin: stato sincronizzazioni (legge il ledger) + **re-sync manuale** delle fatture rimaste
  indietro; registro "sincronizzazioni ERP" nel pannello admin.
- Timeout/circuit-breaker sul client; il fallimento resta best-effort (issue + riga ledger).
- **AC**: le fatture non sincronizzate sono elencabili e ri-inviabili; un ERP irraggiungibile non
  blocca né Workflower né la validazione; ogni tentativo è tracciato. Suite verde.

### M29 — Deploy affiancato + docs + hardening sicurezza
**Perché**: portare Workflower ed ERPNext in esecuzione affiancata in modo riproducibile e sicuro.

- Servizio/compose ERPNext documentato in `docs/deploy.md`; segreti via env con `deploy.env.example`
  esteso (`ERP_*`); nota che Workflower resta **single-worker** (DAL single-writer); checklist di
  backup (ERPNext ha il proprio DB, separato dal repo git di `/data`).
- **AC**: `docker compose` porta su Workflower + ERPNext affiancati; `deploy.md` aggiornato; nessun
  segreto committato. Suite verde.

## 3. Rischi e mitigazioni

| Rischio | Mitigazione |
|---|---|
| Peso operativo di ERPNext (MariaDB+Redis+bench) | Deploy separato; sync best-effort; ERP down non blocca WF (M28/M29) |
| Localizzazione SdI immatura su ERPNext | Sul passivo non si emette; verifica app community in M22; SdI/attivo fuori scope |
| Deriva verso il bidirezionale | Read-back di sola lettura (M27); golden record: una sola entità per proprietario |
| Drift del mapping (voce_computo→cost center, ritenuta→withholding) | Translator = dato con test tabellari (M24); regressione ritenuta preservata |
| Doppia verità sui costi (viste WF vs contabilità ERP) | Confine netto: WF cost-control gestionale, ERP fiscale; niente duplicazione dei report |
| `Meta` `extra="forbid"` blocca chiavi ad-hoc | Campi espliciti `erp_id`/`erp_synced` nel model (unico tocco al layer) — M25 |
| Doppioni su ri-validazione | Ledger `erp_sync.jsonl` + upsert idempotente per chiave (M25) |
| Nessuna CI nel repo | "pytest verde a ogni milestone" resta manuale (`make test`); opzionale aggiungere GitHub Actions |

## 4. Non-goal del track (restano fuori)

Restano fuori il ciclo attivo (`sal`→fattura al committente) e l'emissione elettronica verso SdI; la
scrittura ERP→WF su `/data` come master (multi-master); l'import in-process di codice ERPNext; la
sostituzione delle viste cost-control di Workflower con la contabilità dell'ERP; e ogni modifica a
`runtime.py`/`gateway.py`, che restano invariati.

## 5. File toccati / creati (rappresentativi)

**Nuovi**
- `backend/app/core/erp.py` — `ErpConfig` + `ErpClient` (httpx, transport iniettabile) + Translator (funzioni pure) + Facade `sincronizza`
- `backend/app/seed_assets/schemas/pagamento.schema.json`
- `docs/erp-poc.md` — runbook del PoC (M22)
- Test: `backend/tests/test_erp_translate.py`, `backend/tests/test_erp_sync_e2e.py`, `backend/tests/fake_erp.py`

**Modificati (punti-dato previsti, non la cornice)**
- `backend/app/api/review.py` — aggancio della sync in `valida()` (best-effort)
- `backend/app/models/envelope.py` — `Meta`: campi `erp_id`, `erp_synced` (unico tocco al model)
- `backend/app/core/dal.py` — **una riga** in `ENTITY_TYPES` per `pagamento` (registry-dato)
- `backend/app/core/dataset.py` — `registra_sync_erp` (stile `registra_query` + `commit_paths`)
- `backend/app/seed_assets/config/views.sql` — `v_pagamenti`
- `backend/app/core/deps.py` — costruzione/iniezione di `ErpClient` (come `Gateway`)
- `backend/pyproject.toml` — `httpx>=0.28` da `dev` a runtime
- `docker-compose.yml`, `docs/deploy.md`, `deploy.env.example` — servizio ERPNext + env `ERP_*`

**Riuso esplicito di funzioni/pattern esistenti** (niente reinvenzione)
- `Gateway(completer=...)` (`core/gateway.py`) → modello per il transport iniettabile di `ErpClient`
- `dataset.registra_query` + `DAL.commit_paths` (`core/dataset.py`, `core/dal.py`) → ledger append-only
- `_forse_golden` / `registra_derivazione` (`api/review.py`) → precedente per effetto post-validazione best-effort
- `DAL.update` / `crea_progressivo` / `crea_issue` (`core/dal.py`) → persistenza, id progressivi, issue di fallimento
- ricetta entità-dato di `pozzetto` (schema + riga `ENTITY_TYPES` + vista `v_*`) → modello per `pagamento`
- `conftest.py` (fixture `client` / `dati_rw`) + `fake_llm.FakeCompleter` → modello per `fake_erp` nei test

## 6. Verifica end-to-end

- **`make test` verde a ogni milestone**; in particolare `test_improver_e2e.py::test_scenario_ritenuta`
  e i guard in `test_runtime.py` / `test_views.py` / `test_toolsmith*` **restano intatti** (non negoziabile).
- **Test ERP con transport finto** (nessun ERPNext reale, pattern `conftest`/`fake_llm` → `fake_erp`):
  upload fixture → `POST /review/{id}/validate` → assert commit su `meta` (`erp_id`/`erp_synced`), riga
  in `erp_sync.jsonl`, **idempotenza** su seconda validazione, **issue** su errore simulato.
- **Translator**: test tabellari sui payload DocType (incluso il caso ritenuta → withholding).
- **PoC M22**: runbook manuale contro un ERPNext reale in docker (criterio go/no-go documentato).
- **Deploy M29**: `docker compose up` porta su Workflower + ERPNext; la sync end-to-end di una fattura
  validata è visibile come Purchase Invoice in ERPNext.
- **Nota**: nel repo non esiste CI — la verifica per-milestone è manuale via `make test` + commit dedicato.
