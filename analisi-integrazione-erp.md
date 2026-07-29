# Analisi: integrazione di un ERP open source in Workflower

> Analisi ad ampio raggio (solo analisi, nessun codice applicativo). Scelte di indirizzo
> assunte: ciclo **solo passivo** (cost control), ERP come **sistema di record a valle**,
> priorità **open source puro / no lock-in**.

---

## 1. Contesto — perché questa analisi

Workflower è un sistema *LLM-driven* per il controllo costi dei cantieri, con un'identità
architetturale netta e non negoziabile (`CLAUDE.md`, `analisi-progettazione.md`):

- **Tutto è dato**: workflow, skill, tool, schemi entità sono file versionati in Git; il codice
  (`runtime.py`, `gateway.py`, `dal.py`) è solo la *cornice stabile*.
- **`/data` è la fonte di verità**, nessuno stato applicativo fuori da `/data`, ogni mutazione = commit git.
- **Nessun DB server**: DuckDB è solo motore di query read-only sopra i file JSON.
- **Estendere = dati, non codice**: nuova entità = schema + riga in `ENTITY_TYPES` + vista + manifest.

Workflower è già, di fatto, **mezza ERP di cantiere sul ciclo passivo**: anagrafiche
(`fornitore`, `cantiere`, `dipendente`, `mezzo`, `computo`), documenti estratti e validati
(`fattura`, `ddt`, `sal`, `rapportino`) con `ritenuta_acconto` di prima classe, e uno strato
analitico/contabile in viste DuckDB (`v_scostamento_voci`, `v_cantiere_scostamento`,
`v_mezzi_tco`, `v_rapportini_righe`). **Ciò che manca è la spina dorsale fiscale-contabile**:
partita doppia / piano dei conti (prima nota), pagamenti/tesoreria, registri IVA e adempimenti,
ciclo attivo. Reinventarli entity-as-data è possibile ma costoso e a rischio errori fiscali.

**La domanda dell'analisi**: quale ERP open source (prima ipotesi ERPNext) adottare e — soprattutto —
*con quale confine architetturale* per non tradire l'identità di Workflower.

---

## 2. Sintesi / Raccomandazione

**Adottare ERPNext come sistema di record contabile a valle, integrato tramite un adattatore
mono-direzionale (Workflower → ERPNext) con anti-corruption layer, attivato alla validazione
del documento, realizzato con il pattern entity-as-data già esistente. La cornice
`runtime.py`/`gateway.py`/`dal.py` non cambia; l'ERP non è mai embedded, non è mai lo store di
Workflower, non entra mai in-process — è un'integrazione outbound esattamente come le previste
integrazioni M365 di Fase 4.**

In una riga: **Workflower resta il *system of engagement* + cost intelligence; ERPNext diventa il
*system of record* fiscale**, alimentato solo da documenti già validati dall'umano.

Le tre scelte di indirizzo convergono tutte su questa soluzione:

| Scelta | Conseguenza sull'analisi |
|---|---|
| **Solo passivo** | Il punto debole di ERPNext (emissione SdI, community app) diventa quasi irrilevante: sul passivo si *riceve*, non si emette. |
| **Sistema di record a valle** | Conferma sync mono-direzionale + anti-corruption layer; Workflower resta il front LLM. |
| **Open puro / no lock-in** | Decide ERPNext vs Odoo: ERPNext è GPLv3 con contabilità completa inclusa; Odoo Community lascia P&L/bilancio in Enterprise (open-core → lock-in). |

---

## 3. Perché ERPNext e non Odoo

Confronto sui soli assi che contano per *questo* progetto e *queste* priorità.

| Criterio | ERPNext | Odoo Community | Vincitore per Workflower |
|---|---|---|---|
| **Licenza / apertura contabilità** | GPLv3, **tutta la contabilità inclusa** (GL, bilancio, P&L) | LGPLv3 ma **P&L/bilancio/riconciliazione bancaria solo Enterprise** (open-core) | **ERPNext** — coerente con "open puro / no lock-in" |
| **Modello dati** | Frappe **DocType metadata-driven**: ogni oggetto è metadato + REST auto-generata | ORM Python + moduli, RPC | **ERPNext** — risuona con "tutto è dato" / schema-as-data |
| **API d'integrazione** | REST pulita e prevedibile per ogni DocType (GET/POST/PUT/DELETE, JSON) | XML-RPC / JSON-RPC, più idiosincratico | **ERPNext** — anti-corruption layer più semplice |
| **Costo di proprietà** | Nessuna licenza per-utente | Community gratis ma le feature contabili chiave spingono all'Enterprise a pagamento | **ERPNext** — adatto a PMI edile |
| **Localizzazione IT / SdI** | App community (`mascor/erpnext_fattura_elettronica`), meno matura | `l10n_it_edi` / `l10n_it_edi_withholding` **nativi e maturi** | **Odoo** — ma poco rilevante sul solo passivo |
| **Stack / peso** | Python + MariaDB + Redis + bench | Python + PostgreSQL | Pari (entrambi pesanti, vedi §7) |

**Verdetto**: date le priorità dichiarate, **ERPNext**. Il solo vantaggio reale di Odoo (SdI nativo)
riguarda l'emissione attiva, esclusa dallo scope. La contabilità open-core di Odoo è invece un
*dealbreaker*: adottarlo come "backbone contabile gratuito" non darebbe gratis proprio la contabilità.

---

## 4. Il confine — chi possiede cosa

Regola d'oro dell'integrazione (golden record): **un solo sistema possiede ogni entità**.

| Dominio | Proprietario | Note |
|---|---|---|
| Ingest documenti, OCR, estrazione LLM, human-in-the-loop | **Workflower** | Cuore del progetto |
| Anagrafiche operative arricchite, `computo` (budget), scostamenti, TCO, costo manodopera, cronoprogramma | **Workflower** | La "cost intelligence" |
| UI Operatore/Admin, cost control per cantiere | **Workflower** | |
| Piano dei conti, partita doppia, prima nota | **ERPNext** | Ciò che manca oggi |
| Registrazione fiscale fattura fornitore, registri IVA | **ERPNext** | |
| Pagamenti, tesoreria, scadenziario fornitori | **ERPNext** | Oggi assente in Workflower |
| Reportistica fiscale / bilancio | **ERPNext** | |

**Dati mappati attraverso il confine** (con direzione):

| Workflower (`dati`) | → | ERPNext (DocType) | Direzione |
|---|---|---|---|
| `fornitore` (`ragione_sociale`, `partita_iva`, …) | → | **Supplier** | WF → ERP (upsert prima della fattura) |
| `cantiere` | → | **Project** e/o **Cost Center** | WF → ERP |
| `fattura` (testata) | → | **Purchase Invoice** | WF → ERP alla validazione |
| `fattura.righe[]` (`descrizione`, `importo`, `voce_computo_id`, `mezzo_id`) | → | **Purchase Invoice Item** (+ cost center = cantiere) | WF → ERP |
| `fattura.ritenuta_acconto` | → | **Purchase Taxes / Tax Withholding** | WF → ERP |
| `ddt` | → | **Purchase Receipt** (fase 2) | WF → ERP |
| Stato pagamento / n. protocollo fiscale | ← | Payment Entry / SdI status | ERP → WF (solo *read-back* su `meta`) |

Il ciclo attivo (`sal` → fattura a committente) resta **fuori scope**: eventuale fase futura.

---

## 5. Architettura d'integrazione

### 5.1 Pattern: Anti-Corruption Layer, mono-direzionale, entity-as-data

- **Mono-direzionale** WF → ERP per i documenti; ERP → WF solo *read-back* di stato (pagamento,
  esito fiscale) scritto su `meta` dell'envelope. Niente multi-master (evita loop/corruzione dati).
- **Anti-Corruption Layer** a tre strati: *Adapter* (HTTP/REST + auth), *Translator* (envelope Workflower
  → payload DocType ERPNext), *Facade* (operazioni pulite: `upsert_supplier`, `push_purchase_invoice`).
  Il modello ERPNext non "trapela" mai negli schemi di `/data`.

### 5.2 Realizzazione senza toccare la cornice

L'adattatore vive **come dato/tool**, non come modifica a runtime/gateway/dal:

- **Trigger**: alla transizione `bozza → validato` di un `TIPI_INGRESSO` (`set_validato` in `dal.py`).
  L'invio all'ERP è un *effetto a valle della validazione*, non parte dell'estrazione.
- **Codice adattatore**: due opzioni, entrambe coerenti con le regole —
  1. **Tool nativo d'integrazione** in `backend/app/core/tools/` (come `ocr_pdf`, `ricerca`): è
     parte della cornice ma *isolato*, invocato da un workflow di sincronizzazione; oppure
  2. **Python tool consolidato** in `data/tools/<nome>/` (pattern Toolsmith F3), versionato,
     approvato dall'umano, **eseguito solo in sandbox** — nota: la sandbox blocca la rete, quindi
     per chiamate HTTP verso l'ERP l'opzione (1) è la più adatta; la (2) resta valida per la sola
     *traduzione* (mapping puro envelope→payload, testabile e deterministico).

  Scelta consigliata: **traduzione come tool deterministico testabile + invio come tool nativo I/O**.
- **Config/segreti**: `ERP_BASE_URL`, `ERP_API_KEY`, `ERP_API_SECRET` via env (stesso pattern dei
  tier LLM `LLM_T*_MODEL` nel `gateway.py`): mai model/endpoint hard-coded.
- **Idempotenza & audit**: un ledger `data/dataset/erp_sync.jsonl` (stesso pattern di `pytools.jsonl`)
  mappa `id envelope ↔ docname ERPNext`; il `docname` restituito viene scritto su `meta` (es.
  `meta.erp_ref`) → link d'audit committato in git. Reinvio = upsert idempotente sulla chiave.
- **Fallimento**: se l'ERP è irraggiungibile, coerente col contratto "runtime non solleva mai" →
  issue automatica ("ci pensa l'ufficio") e retry, senza bloccare la validazione.

### 5.3 Flusso end-to-end

```
Documento → workflow ingest (invariato) → bozza → revisione umana → VALIDATO
                                                                       │
                                              [nuovo] workflow "sync-erp"
                                                       │
                        Translator (envelope → DocType)  ──►  Adapter REST ──►  ERPNext
                                                       │                         (Supplier,
                        meta.erp_ref + erp_sync.jsonl ◄── docname / esito        Purchase Invoice)
                                                       │
                        read-back stato pagamento (schedulato) ◄────────────────
```

---

## 6. Coerenza con le regole di Workflower (verifica)

| Regola | Rispettata? | Come |
|---|---|---|
| `/data` unica fonte di verità, nessuno stato fuori da `/data` | ✅ | Lo stato di WF resta in `/data`; ERPNext è un *sistema esterno separato*, non lo store di WF. Il backref è dato in `meta`. |
| Ogni mutazione = commit git | ✅ | `meta.erp_ref` e `erp_sync.jsonl` passano dal DAL → commit. |
| Nessun DB server (in Workflower) | ✅ | Il MariaDB è di ERPNext, servizio a sé; WF non guadagna un DB. La regola vincola lo store di WF, non i sistemi integrati. |
| Modelli LLM mai hard-coded (tier via env) | ✅ (analogia) | Endpoint/segreti ERP via env, stesso principio. |
| Aggiungere un'entità = dati | ✅ | Eventuali nuove entità (es. `pagamento` per il read-back) = schema + riga `ENTITY_TYPES` + vista. |
| `runtime.py`/`gateway.py`/`dal.py` non cambiano | ✅ | L'integrazione è workflow + tool + config, non cornice. |
| Codice generato eseguito solo in sandbox | ✅ | La traduzione può essere tool sandboxed; l'I/O di rete è tool nativo dedicato, non codice generato. |

---

## 7. Rischi & mitigazioni

1. **Peso operativo**: ERPNext richiede MariaDB + Redis + bench. È un servizio in più da gestire
   (backup, upgrade, sicurezza). *Mitigazione*: deploy separato (docker), trattato come dipendenza
   esterna; nessun accoppiamento in-process; l'indisponibilità dell'ERP non blocca WF (§5.2).
2. **Localizzazione SdI immatura su ERPNext**: sul solo passivo l'impatto è basso, ma verificare
   **prima** lo stato di manutenzione di `mascor/erpnext_fattura_elettronica` e la gestione nativa
   della *tax withholding* per la ritenuta. *Mitigazione*: se in futuro serve l'attivo/SdI, valutare
   un intermediario SdI dedicato (es. provider "canale SdI") indipendente dall'ERP.
3. **Tentazione del bidirezionale**: mantenere il read-back in sola lettura di pochi campi di stato.
   Mai far scrivere all'ERP dentro `/data` come master. *Mitigazione*: golden record per entità (§4).
4. **Drift del mapping** (voce_computo → cost center, ritenuta → withholding): il mapping è la parte
   fragile. *Mitigazione*: traduzione come **tool deterministico con test** (mina i casi dai trace
   validati, come già fa il Toolsmith per la ritenuta); lo scenario "ritenuta d'acconto" (M5) resta
   la regressione da non rompere mai.
5. **Doppia verità sui costi**: WF calcola scostamenti/TCO, ERPNext ha la sua contabilità analitica.
   *Mitigazione*: confine netto (§4) — WF possiede il *cost control gestionale*, ERPNext il *fiscale*;
   non si duplicano i report, si dividono i domini.

---

## 8. Alternative valutate e scartate

- **Odoo Community al centro**: scartato — contabilità open-core (P&L/bilancio in Enterprise)
  contro la priorità "open puro"; RPC meno affine a "tutto è dato". Resta il *piano B* solo se in
  futuro l'emissione SdI nativa diventasse prioritaria.
- **ERP al centro, WF come modulo di ingest**: scartato — snaturerebbe l'identità LLM-driven del progetto.
- **Nessun ERP, tutto entity-as-data + intermediario SdI**: architetturalmente purissimo e valido,
  ma richiede di implementare partita doppia/registri IVA/pagamenti a mano (rischio fiscale, costo).
  Non scelto ora, ma è la naturale evoluzione se l'ERP esterno risultasse troppo pesante:
  vale come *exit strategy* documentata.

---

## 9. Fasatura consigliata (per un'eventuale implementazione futura — fuori scope di questa analisi)

- **Fase 0 — Spike/PoC (go/no-go)**: alzare ERPNext in docker; mappare a mano via REST un `fornitore`
  → Supplier e una `fattura` con `ritenuta_acconto` → Purchase Invoice + withholding. Validare che la
  ritenuta e l'imputazione al cantiere (cost center) tornino. Verificare stato dell'app SdI community.
- **Fase 1 — Adattatore outbound minimo**: `fornitore` + `fattura` alla validazione, mono-direzionale,
  con `erp_sync.jsonl` + `meta.erp_ref`; traduzione come tool testato.
- **Fase 2 — Estensione**: `ddt` → Purchase Receipt; `cantiere` → Project/Cost Center; read-back
  stato pagamento su `meta`.
- **Fase 3 (eventuale)**: ciclo attivo (`sal` → fattura committente) + SdI, solo se richiesto.

---

## 10. Riferimenti

### File del repo citati
- `CLAUDE.md`, `analisi-progettazione.md` (§1, §3) — principi e cornice
- `backend/app/core/dal.py` (`ENTITY_TYPES`, `set_validato`, ledger pattern) — punto di trigger e audit
- `backend/app/core/gateway.py` — pattern env per config/segreti
- `backend/app/seed_assets/schemas/fattura.schema.json` — struttura mappata su Purchase Invoice
- `backend/app/seed_assets/config/views.sql` — strato analitico/cost-control che resta a WF
- `backend/app/core/tools/` — dove collocare il tool nativo d'integrazione I/O

### Fonti esterne principali
- ERPNext GPLv3, contabilità completa inclusa vs Odoo open-core (P&L/bilancio Enterprise-only) —
  confronti ERPNext/Odoo 2026, documentazione licenze Odoo Community/Enterprise
- Frappe Framework: REST auto-generata per ogni DocType (modello metadata-driven) — docs.frappe.io
- Odoo `l10n_it_edi` / `l10n_it_edi_withholding` nativi (rilevanti per il ciclo attivo/SdI) — docs Odoo Italy
- App community `mascor/erpnext_fattura_elettronica` per SdI su ERPNext — GitHub
- Pattern Anti-Corruption Layer e sync mono-direzionale (golden record per entità) — Azure Architecture Center / DDD
