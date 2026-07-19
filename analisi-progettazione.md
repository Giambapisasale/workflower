# Workflower — Analisi di progettazione

**Sistema LLM-driven per gestione e controllo costi di cantieri edili**
Versione 0.2 — 19/07/2026 — AITHO / Giambattista

---

## 1. Visione

La richiesta del cliente (cruscotto costi, report mensili da fatture/DDT/SAL/ore/materiali, app interna per mezzi/lavorazioni/scadenze/documenti, aggiornamento automatico registri, confronto computi/preventivi, integrazione M365) viene affrontata **rovesciando l'approccio tradizionale**: il software non implementa le funzionalità — le funzionalità sono **workflow dichiarativi eseguiti da agenti LLM**. Il codice "tradizionale" costruisce solo la cornice stabile: storage, logging, UI, sicurezza, runtime.

Principi:

1. **Tutto è dato**: workflow, skill, tool e schemi delle entità sono file versionati in Git, modificabili dagli agenti stessi (con approvazione umana).
2. **Human-in-the-loop**: ogni estrazione produce una *bozza* con confidence; ogni modifica a un workflow richiede approvazione.
3. **Auto-miglioramento**: log tecnici + feedback utente alimentano un agente Improver che corregge i workflow.
4. **Costi sotto controllo**: le operazioni ricorrenti vengono consolidate in codice deterministico e i tool call loggati alimentano il fine-tuning di modelli piccoli.

## 2. Glossario

| Concetto | Definizione |
|---|---|
| **Entità** | Record JSON con schema (Fattura, DDT, SAL, Cantiere…), salvato come file, collegato ad altre entità per ID |
| **Workflow** | Manifest dichiarativo: trigger + sequenza di step (prompt + tools + skills) + schema di output + regole di validazione. Un workflow = un agente |
| **Skill** | Istruzioni (Markdown) + eventuali script che un agente carica per un compito specifico |
| **Tool** | Funzione deterministica invocabile (Python / vista SQL), nata dal consolidamento di operazioni ricorrenti |
| **Trace** | Log completo di una esecuzione: input, prompt, tool call (input/output), risultato, esito |
| **Golden set** | Insieme di run passati validati dall'utente, usato come test di regressione per le nuove versioni dei workflow |

## 3. Architettura

```
┌────────────────────────────────────────────────────────────┐
│  UI Web (cruscotto, carica, revisione, interroga, admin)   │
└──────────────────────────┬─────────────────────────────────┘
┌──────────────────────────▼─────────────────────────────────┐
│  ORCHESTRATORE (workflow runtime)                          │
│  · carica manifest workflow · esegue step · valida output  │
│  · coda scritture single-writer · trace di ogni run        │
└───────┬──────────────────┬──────────────────────┬──────────┘
┌───────▼────────┐ ┌───────▼──────────┐ ┌─────────▼──────────┐
│ GATEWAY LLM    │ │ STORAGE          │ │ INTEGRAZIONI       │
│ (LiteLLM)      │ │ · file JSON (SoT)│ │ · MS Graph:        │
│ · SOTA (T1)    │ │ · DuckDB (query) │ │   SharePoint/      │
│ · medio (T2)   │ │ · blob originali │ │   OneDrive/Planner │
│ · fine-tuned   │ │ · Git (audit)    │ │ · Outlook ingest   │
│   locale (T3)  │ │                  │ │ · export Excel     │
└───────┬────────┘ └──────────────────┘ └────────────────────┘
┌───────▼────────────────────────────────────────────────────┐
│ OBSERVABILITY: trace store · cost tracking · dataset       │
│ builder (JSONL tool call → fine-tuning FunctionGemma)      │
└────────────────────────────────────────────────────────────┘
```

### 3.1 Gateway model-agnostic

Requisito confermato: nessun lock-in su un provider. **LiteLLM** (proxy/gateway open source) espone un'API unica OpenAI-compatible verso 100+ provider, con cost tracking, logging nativo di input/output, fallback e load balancing. Routing a tre tier:

- **T1 — SOTA** (Claude, GPT, Gemini top): estrazione documenti, riparazione errori, proposte di miglioramento dei workflow.
- **T2 — medio**: classificazione documenti, text-to-SQL, riassunti.
- **T3 — piccolo/locale fine-tuned**: tool call consolidate (vedi §3.7). Escalation automatica a T1 su bassa confidence o errore.

Lo switch di modello è trasparente per i workflow: il manifest dichiara il *tier*, non il modello.

### 3.2 Storage: file JSON + DuckDB (nessun DB server)

Vincolo: entità come file JSON interrogabili e collegabili, evitando un database NoSQL. La soluzione:

**Il file system è la fonte di verità.** Un file per record, organizzato per tipo/anno:

```
/data
  /entities
    /cantieri/CNT-001.json
    /fatture/2026/FT-2026-0341.json
    /ddt/2026/DDT-2026-1102.json
    /sal/CNT-001/SAL-03.json
  /blobs/fatture/2026/FT-2026-0341.pdf     ← originale immutabile
  /schemas/fattura.schema.json             ← JSON Schema per entità
```

**DuckDB è il motore di query, non un database.** È una libreria embedded (nessun server, nessun processo da amministrare) che legge i file JSON direttamente con `read_json`, inferisce lo schema e offre SQL completo con operatori JSON — con prestazioni analitiche molto superiori a SQLite su aggregazioni (il caso d'uso: cruscotti costi, confronti computo/preventivo). Nessun ETL: si definisce un **catalogo di viste** per entità (`v_fatture`, `v_sal`, `v_ore`…) e il Query Agent genera SQL contro viste stabili, mai contro i file grezzi. Se domani un file cambia posizione, si aggiorna la vista, non i workflow.

**Concorrenza e audit**: le scritture passano tutte dall'orchestratore in coda single-writer con lock per cantiere; ogni mutazione produce un commit Git automatico → audit trail completo, diff leggibili, rollback gratuito.

**Redis Stack come evoluzione opzionale** (valutato e rimandato): RedisJSON + RediSearch darebbero indicizzazione secondaria, full-text e bassa latenza su accessi concorrenti. Non serve nel perimetro attuale (decine di utenti, migliaia di documenti/anno). Poiché tutte le letture passano da un Data Access Layer, introdurlo in futuro come *indice/cache* — con i file che restano la verità — non impatta i workflow.

### 3.3 Modello delle entità

Registry di JSON Schema versionati. Entità principali: `Cantiere`, `Fornitore`, `Fattura`, `DDT`, `SAL`, `RapportinoOre`, `Materiale`, `Mezzo`, `Lavorazione`, `Scadenza`, `Documento`, `VoceComputo`, `VocePreventivo`, `Pozzetto`, `Cronoprogramma`.

Ogni record usa un **envelope standard**; le relazioni sono riferimenti per ID:

```json
{
  "id": "FT-2026-0341",
  "tipo": "fattura",
  "schema_version": "1.2",
  "stato": "bozza | validato",
  "dati": {
    "fornitore_id": "FRN-018",
    "cantiere_id": "CNT-001",
    "numero": "341/2026", "data": "2026-07-02",
    "imponibile": 10163.93, "iva": 2236.07, "totale": 12400.00,
    "righe": [ { "descrizione": "...", "voce_computo_id": "VC-114", "importo": 0 } ]
  },
  "meta": {
    "origine": "blobs/fatture/2026/FT-2026-0341.pdf",
    "workflow_run_id": "run-8f21", "workflow_version": "carica-fattura@1.3",
    "confidence": { "totale": 0.99, "righe": 0.87 },
    "created": "2026-07-18T09:12:00Z"
  }
}
```

### 3.4 Workflow = agenti dichiarativi

Un workflow è un manifest YAML versionato. Esempio (semplificato):

```yaml
name: carica-fattura
version: 1.3
trigger: [upload:pdf, upload:image, email:fatture@…, watch:sharepoint/Fatture]
tier: T1
steps:
  - id: estrai
    skill: skills/estrazione-fattura.md      # prompt + esempi + regole IVA/ritenute
    tools: [ocr_pdf, cerca_fornitore, cerca_cantiere]
    output_schema: schemas/fattura.schema.json
  - id: collega
    skill: skills/collega-entita.md          # match fornitore, cantiere, voci computo
  - id: valida
    rules: [totale == imponibile + iva, data <= oggi, fornitore_id esiste]
    on_fail: escalate:T1-retry | flag:revisione-umana
  - id: salva
    action: save_draft                        # sempre bozza, mai validato in automatico
confidence_threshold: 0.90                    # sotto soglia → revisione umana obbligatoria
```

Il runtime esegue gli step, valida contro lo schema, salva la bozza e registra il trace completo. **I manifest sono dati**: l'agente Improver può proporne una nuova versione.

### 3.5 Ciclo di auto-miglioramento

```
run → trace ─┬─ ok ────────────────────→ (candidato golden set dopo validazione)
             ├─ errore tecnico (log) ──┐
             └─ errore semantico ──────┤   (feedback utente puntuale dalla UI:
                                       ▼    "manca la ritenuta d'acconto")
                              AGENTE IMPROVER
                    analizza trace + feedback → propone PATCH:
                    diff sul prompt della skill / nuova regola di
                    validazione / esempio few-shot dal caso corretto
                                       ▼
                    REGRESSIONE: replay su golden set (N run validati)
                                       ▼
                    APPROVAZIONE UMANA → nuova versione (semver, Git)
                                       └─ rollback sempre possibile
```

Questo pattern (skill library + self-refinement guidato da valutazione, con verifiche di regressione prima della promozione) è oggi la direzione consolidata della ricerca sugli agenti auto-miglioranti (SkillAxe, SkillSmith, SkillOps — vedi Fonti). Il punto critico che la letteratura conferma: **mai promuovere una modifica senza replay su casi validati** — altrimenti si corregge un errore introducendone tre.

### 3.6 Consolidamento skill → tool ("hardening")

Ogni operazione generata dagli agenti (query SQL, calcoli, trasformazioni) viene fingerprintata. Un tracker conta le generazioni *simili*; oltre soglia diventano **candidati al consolidamento**, che l'ufficio promuove (human-in-the-loop) in una di **tre forme, tutte dato-non-codice**:

- **Vista `v_*`** (aggregati/elenchi): una vista SQL in `config/views.sql`. *Consegnata (F2).*
- **Tool parametrico `t_*`** (query con un valore variabile, es. il cantiere): una **macro tabellare DuckDB** in `config/macros.sql`, non Python. *Consegnata (F2).*
- **Tool Python** (calcoli e trasformazioni che l'SQL non esprime, es. il calcolo della ritenuta d'acconto): una funzione deterministica in `data/tools/`. *Fase 3.* Il **Toolsmith** (1) scrive la funzione equivalente, (2) genera i test **dai trace storici** (coppie input/output già validate), (3) la esegue **in sandbox** contro i test, (4) su approvazione umana la registra e propone — via Improver — una patch di skill perché la invochi, con l'LLM come fallback.

**Invariante — il codice generato è dato, non runtime.** Un tool Python vive in `data/tools/` (sorgente + schema + test + ledger), versionato e committato come le viste; il runtime non lo importa mai in-process, lo **esegue solo in sandbox isolata** (subprocess, niente rete/filesystem/ambiente, import in whitelist, limiti di CPU/memoria/tempo). La cornice stabile — runtime, gateway, dal — non cambia: cresce solo il dato.

Ciclo di vita: `esplorativa → candidata → consolidata → deprecata`. Benefici: costo token ≈ 0 sulle operazioni ricorrenti, latenza costante, determinismo, testabilità. La pagina Skills & Tools mostra contatori, candidati e artefatti consolidati; rimuovere un consolidato libera di nuovo il candidato (reversibile via git).

### 3.7 Logging tool call e distillazione (FunctionGemma)

Ogni chiamata LLM e ogni function call è loggata in JSONL standard:

```json
{"run_id":"run-8f21","step":"estrai","tools":[…schema tools…],
 "messages":[…contesto…],"tool_call":{"name":"cerca_fornitore","args":{…}},
 "result":{…},"outcome":"success","validated_by_user":true}
```

Il **dataset builder** filtra le tool call dei run validati → training set per fine-tuning di **FunctionGemma** (Gemma 3 270M specializzata in function calling, fine-tuning LoRA documentato da Google) o Gemma 3 1B. La distillazione da tracce di modelli frontier verso studenti piccoli è una pratica ormai standard con guadagni documentati. Il router (§3.1) sposta progressivamente i workflow consolidati sul tier T3 locale: **il costo marginale per documento tende a zero** man mano che il sistema matura. *Stato*: il dataset builder è consegnato (F2); la **valutazione offline** del modello candidato, l'**escalation T3→T1** e il wiring dell'endpoint locale sono la **Fase 3** — il training LoRA reale resta un runbook operativo fuori dal repo, attivabile a modello pronto.

### 3.8 Integrazioni Microsoft 365

Via Microsoft Graph API: **SharePoint/OneDrive** (watcher sulle cartelle esistenti del cliente: i file che già oggi salvano diventano trigger di workflow), **Planner** (scadenze e attività generate dai workflow), **Outlook** (ingest fatture da casella dedicata; notifiche), **Excel** (i report mensili standard si generano come .xlsx da viste DuckDB — il cliente continua a vivere in Excel senza doverlo abbandonare).

### 3.9 Ruoli e modalità operative

Due modalità nette, stessa piattaforma:

| | **Operatore** (capocantiere, operaio, impiegato) | **Admin** (ufficio tecnico / gestore piattaforma) |
|---|---|---|
| Scopo | *usare* le funzionalità | *governare ed evolvere* il sistema |
| Vede | Carica, I miei documenti, Chiedi, (Cruscotto se autorizzato) | tutto: revisione, workflows, skills & tools, log, dataset, approvazioni |
| Feedback | "Qualcosa non torna" in linguaggio naturale → coda segnalazioni | feedback puntuale per campo + approvazione patch Improver |
| Meccanica interna | **totalmente invisibile**: mai termini come workflow, skill, JSON, confidence | trasparenza completa su trace, versioni, diff |
| Validazione dati | non valida: carica e conferma "è tutto giusto?" con linguaggio semplice | valida le bozze, gestisce i casi sotto soglia |

**Principio "a prova di cantiere"** per la modalità Operatore:

- **Mobile-first**: il dispositivo primario è il telefono in cantiere. Foto → fatto.
- **3 azioni massimo** in home, bottoni giganti con icona + parola: *Carica* (fotografa o scegli file), *I miei documenti* (stato: 🟡 in lavorazione / 🟢 a posto / 🔴 serve aiuto), *Chiedi* (domanda a voce o testo → risposta semplice, niente SQL a video).
- **Zero form**: l'operatore non compila campi — carica il documento, l'LLM estrae, e il sistema al massimo fa **una domanda alla volta** in italiano semplice ("Questo DDT è del cantiere di Via Roma?" [Sì] [No, è un altro]).
- **Zero errori bloccanti**: qualsiasi cosa carichi, il sistema la accetta; se non la capisce, la mette in coda per l'ufficio e all'operatore dice solo "ci pensiamo noi ✓".
- **Conferme rassicuranti**, testo grande, alto contrasto, funziona coi guanti (target touch ≥ 48px), vocabolario da cantiere non da software.

Il feedback dell'operatore alimenta comunque il ciclo §3.5: la segnalazione in linguaggio naturale finisce nella coda Admin; è l'Admin che la trasforma (con l'aiuto dell'Improver) in patch e la approva. **L'operatore non approva mai modifiche ai workflow.**

**Autorizzazione**: RBAC minimale (`operatore` | `admin`), pronto per SSO Microsoft Entra ID (il cliente è già su M365) con mapping gruppo→ruolo. Permessi granulari per cantiere (un capocantiere vede solo i suoi cantieri).

## 4. UX — pagine dell'applicazione

**Modalità Operatore** (default): `Home` (3 bottoni giganti) · `Carica` (foto/file → "ricevuto, ci pensiamo noi") · `I miei documenti` (elenco a semaforo, tap per dettaglio semplificato) · `Chiedi` (domanda libera → risposta in italiano, mai SQL/JSON a video).

**Modalità Admin**: `Cruscotto` (costi per cantiere, scostamenti vs preventivo, alert) · `Revisione` (originale a fianco del JSON interpretato, confidence per campo, feedback puntuale) · `Segnalazioni` (coda dei "qualcosa non torna" degli operatori, con trace collegato) · `Interroga` (linguaggio naturale → SQL su viste → tabella; salvabile come report o tool) · `Workflows` (versioni, success rate, patch da approvare) · `Skills & Tools` (registry, contatori, candidati al consolidamento) · `Log & Dataset` (trace, esempi, export fine-tuning, costo token).

Il mockup (`mockup.html`) ha lo **switch Operatore/Admin**: in modalità Operatore percorre carica-con-foto → conferma semplice → segnalazione "qualcosa non torna"; in modalità Admin percorre il giro completo: revisione → feedback puntuale → patch Improver con regressione → approvazione → ri-esecuzione → cruscotto.

## 5. Rischi e mitigazioni

| Rischio | Mitigazione |
|---|---|
| Allucinazioni in estrazione | JSON Schema validation + regole aritmetiche (§3.4) + confidence per campo + stato `bozza` finché non validato da umano |
| Drift dei workflow auto-modificati | Versioning Git + golden set di regressione + approvazione umana obbligatoria |
| Concorrenza su file | Coda single-writer nell'orchestratore + lock per cantiere |
| Costi token | Routing a tier + consolidamento in tool + distillazione su modello locale |
| Esecuzione di codice generato dall'LLM (Toolsmith §3.6) | Sandbox obbligatoria: subprocess isolato, no rete/FS/ambiente, import in whitelist, limiti CPU/memoria/tempo; il codice è dato, mai importato in-process; test dai trace validati; approvazione umana; fallback all'LLM se il tool sbaglia |
| Lock-in provider | Gateway LiteLLM, manifest dichiarano tier non modelli |
| Privacy dati cantiere | Provider con no-training garantito per T1/T2; T3 gira in locale; originali mai inviati a terzi se non necessario |
| Scalabilità query | DuckDB regge ordini di grandezza oltre il perimetro; exit strategy: Redis Stack come indice (§3.2) senza toccare i workflow |
| Adozione da parte di utenti poco digitali | Modalità Operatore (§3.9): mobile-first, 3 azioni, zero form, zero errori bloccanti; test sul campo con veri operai in F1 |

## 6. Roadmap

> **Stato (agg. 19/07/2026)**: F1 e F2 **completate** e verdi ai test (M0–M13). L'ordine di
> esecuzione delle fasi successive è stato **rovesciato** rispetto alla numerazione
> originale: si completa prima l'**autonomia locale** (l'ex-F4 più la metà interna dell'ex-F3),
> poi le **integrazioni esterne** — per avere una piattaforma completa *al netto dei servizi
> esterni*.

- **F1 — PoC** ✅: entità core (Cantiere, Fornitore, Fattura), workflow carica-fattura completo di ciclo di feedback, cruscotto minimale, viste DuckDB, **due modalità UI (Operatore mobile-first + Admin)** con RBAC minimale.
- **F2** ✅: DDT, SAL, rapportini ore, computo; classificazione e instradamento documenti; collegamento voci e scostamenti; cruscotto + registro per cantiere; report mensili Excel; Interroga (text-to-SQL); CRUD manuale schema-driven; **consolidamento in due forme dato-non-codice** (viste `v_*`, tool parametrici `t_*`).
- **F3 — Autonomia locale** (in corso, `piano-implementazione-fase3.md`, M14–M21): **Toolsmith Python** in sandbox — la terza forma di consolidamento — e attivazione del ciclo; **dataset builder → valutazione → tier T3** con escalation T3→T1; completamento delle **entità e registri interni** (materiali, mezzi, lavorazioni, scadenze, pozzetti, cronoprogramma).
- **F4 — Integrazioni esterne**: M365/Graph (watcher SharePoint, Planner, ingest Outlook), SSO Entra ID, packaging/deploy e hardening di prodotto.

KPI: % estrazioni senza correzione umana; tempo di produzione report mensile; costo token per documento (atteso in calo strutturale con la Fase 3: consolidamento + tier T3).

## 7. Decisioni chiave (ADR)

1. **Storage**: file JSON = fonte di verità + DuckDB embedded per query. No DB server, no NoSQL. Redis Stack solo come futuro indice opzionale.
2. **Gateway**: LiteLLM, routing a tier, modelli intercambiabili.
3. **Workflow-as-data**: manifest YAML + skill Markdown versionati in Git; gli agenti li modificano, gli umani approvano.
4. **Bozza-first**: nessun dato entra come `validato` senza conferma umana o storicità di affidabilità del workflow.
5. **Log-everything**: ogni tool call è un potenziale esempio di training.
6. **Due modalità nette**: Operatore (solo uso, meccanica LLM invisibile, mobile-first "a prova di cantiere") e Admin (governo ed evoluzione del sistema). L'operatore non approva mai patch ai workflow.
7. **Codice generato = dato, eseguito solo in sandbox**: i tool Python prodotti dal Toolsmith (§3.6) vivono in `data/tools/`, versionati e approvati come le viste; il runtime non li importa mai in-process, li esegue solo in sandbox isolata. Consolidare resta una mutazione di dati; la cornice (runtime/gateway/dal) non cambia.

## Fonti

- DuckDB su JSON: [duckdb.org/docs/data/json/overview](https://duckdb.org/docs/current/data/json/overview), [MotherDuck — Analyze JSON with SQL](https://motherduck.com/blog/analyze-json-data-using-sql/), [DuckDB vs SQLite](https://motherduck.com/learn/duckdb-vs-sqlite-databases/)
- Redis Stack JSON: [redis.io — Index/query JSON](https://redis.io/docs/latest/develop/data-types/json/indexing_json/), [use cases](https://redis.io/docs/latest/develop/data-types/json/use_cases/)
- Agenti auto-miglioranti e skill library: [SkillAxe](https://arxiv.org/pdf/2606.10546), [SkillSmith](https://arxiv.org/pdf/2606.01314), [SkillOps](https://arxiv.org/pdf/2605.13716), [MetaSkill-Evolve](https://arxiv.org/pdf/2607.05297)
- FunctionGemma fine-tuning: [Google AI — Fine-tuning with FunctionGemma](https://ai.google.dev/gemma/docs/functiongemma/finetuning-with-functiongemma), [Google Developers Blog](https://developers.googleblog.com/a-guide-to-fine-tuning-functiongemma/)
- Gateway: [LiteLLM](https://github.com/BerriAI/litellm)
