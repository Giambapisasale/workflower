# Workflower

**Sistema LLM-driven per la gestione e il controllo costi dei cantieri edili.**

Workflower rovescia l'approccio tradizionale: le funzionalità non sono codice, ma
**workflow dichiarativi eseguiti da agenti LLM**. Il codice costruisce solo la
cornice stabile — storage, runtime, gateway ai modelli, interfaccia, sicurezza,
osservabilità — mentre i workflow (prompt, skill, schemi, regole) sono **dati
versionati in Git**, che gli agenti stessi propongono di migliorare e che un
umano approva. Aggiungere una capacità, il più delle volte, significa aggiungere
*dati*, non scrivere codice.

Quattro principi lo tengono insieme:

1. **Tutto è dato** — workflow, skill, tool e schemi delle entità sono file
   versionati, modificabili (con approvazione umana).
2. **Human-in-the-loop** — ogni estrazione produce una *bozza* con confidence;
   nessun dato diventa `validato` e nessun workflow cambia senza un sì esplicito.
3. **Auto-miglioramento** — trace tecnici e feedback dell'operatore alimentano un
   agente **Improver** che corregge i workflow e li riprova sui casi già validati.
4. **Costo marginale che scende** — le operazioni ricorrenti si consolidano in
   codice deterministico (viste, tool, funzioni Python) e le chiamate loggate
   preparano il passaggio a un modello locale a basso costo.

---

## Cosa fa

**Acquisizione documenti.** L'operatore carica una foto o un PDF (fattura, DDT,
SAL, rapportino ore). Un **classificatore** riconosce il tipo e lo instrada al
workflow giusto; l'agente **estrae** i campi via LLM, li valida contro lo schema
dell'entità e produce una **bozza** con un punteggio di confidence per campo. Le
bozze a bassa confidence o che non superano le regole finiscono in **revisione**.

**Controllo costi.** Il **cruscotto** aggrega spesa per cantiere e per fornitore,
ritenute, IVA, imponibile, ore e costo manodopera, con l'avanzamento sul budget.
Ogni cantiere ha un **registro** consolidato (fascicolo di fatture, DDT, ore,
SAL, avanzamento) esportabile in **Excel** (fogli Riepilogo, Fatture, DDT, Ore,
SAL, Scostamento).

**Preventivo vs consuntivo.** Il **computo** (preventivo per voci) si confronta
con la spesa reale: la pagina **Scostamenti** mostra il delta per voce e per
cantiere. In revisione, *Collega al computo* abbina in modo deterministico le
righe di una fattura alle voci, e la spesa risale nello scostamento.

**Interrogazione in linguaggio naturale.** L'ufficio fa domande in italiano
(«Quali fatture hanno una ritenuta d'acconto?»); il sistema genera **SQL** con
guardrail severi (solo `SELECT` sulle viste, `LIMIT` forzato) e mostra la tabella.
Le query ricorrenti diventano candidate al consolidamento in una vista o in un tool.

**Ciclo di auto-miglioramento.** Quando qualcosa non torna, l'operatore segnala in
un tocco. L'**Improver** analizza trace e feedback, propone una **patch** al
workflow (diff della skill/manifest), la **riprova sul golden set** (i run già
validati, come test di regressione) e — solo dopo l'ok umano — pubblica una nuova
versione, rielaborando il documento d'origine.

**Consolidamento in codice deterministico.** Le operazioni ripetute non restano a
carico dell'LLM per sempre: possono diventare **viste SQL** (`v_*`), **tool
parametrici** (`t_*`) o **funzioni Python** generate dal **Toolsmith** a partire
dal delta fra bozza estratta e dato validato, con i **test generati dai trace
storici**. Il codice generato è *dato versionato, approvato dall'umano, eseguito
solo in sandbox isolata* e mai importato nel processo; il tool è un'ottimizzazione
con **fallback all'LLM** se sbaglia.

**Modelli intercambiabili e tier locale.** I workflow dichiarano un *tier*
(T1 SOTA, T2 medio, T3 locale), **mai un modello**: la mappa tier→modello vive
nell'ambiente. Un **harness offline** misura l'accuratezza di un modello locale
candidato sugli esempi validati prima di instradarci del traffico; quando è
attivo, uno step gira in locale a costo ~0 ed **escala a T1** su errore o bassa
confidence, con la percentuale di escalation tracciata.

**Anagrafiche e registri che si aggiornano da soli.** Entità di dominio come puro
dato (materiale, mezzo, lavorazione, scadenza) e **registri automatici** —
pozzetti (manufatti con stato) e cronoprogramma (pianificato vs consuntivo,
dall'ultimo SAL) — si aggiornano a ogni documento e confluiscono in cruscotto,
registro e report.

**Osservabilità.** Ogni esecuzione ha un **trace** completo (input, prompt, tool
call, esito, costo, latenza); un **logbook** trasversale raccoglie gli eventi di
tutte le fasi con gli **errori** in evidenza, con livello configurabile e una
sezione dedicata nell'interfaccia (vedi [Log e diagnostica](#log-e-diagnostica)).

Tutto passa da **due interfacce nette**: l'**Operatore** (mobile-first, la
meccanica LLM è invisibile: si carica, si conferma, si segnala) e l'**Admin**
(l'ufficio governa dati, costi, revisione ed evoluzione dei workflow).

---

## Prerequisiti

- **Python 3.12** (`py -3.12` su Windows)
- **Node 18+** (per il frontend)
- **git** (il repo dati è un repo git separato, creato dal seed)

## Avvio rapido

```bash
make setup            # venv backend + dipendenze + npm install
cp .env.example .env   # poi inserisci una chiave LLM (Anthropic/OpenAI/Gemini)
make demo             # crea il repo dati d'esempio + le fixture + stampa il giro guidato
make dev              # backend :8000, frontend :5173
```

Apri:
- **Operatore** (mobile-first): <http://localhost:5173/op>
- **Admin** (ufficio): <http://localhost:5173/admin>

I modelli LLM **non sono mai hard-coded**: si scelgono in `.env` — `LLM_T1_MODEL`
(SOTA, per estrazione e Improver), `LLM_T2_MODEL` (medio, per text-to-SQL e
giudizio) e l'opzionale `LLM_T3_MODEL` (locale fine-tuned). Qualunque modello
supportato da litellm.

### Utenti demo

| Utente | Codice | Ruolo | Cantiere |
|---|---|---|---|
| `salvo` | `1111` | operatore | Residenza Le Palme |
| `giuseppe` | `2222` | operatore | Scuola Manzoni |
| `marco` | `3333` | operatore | Capannone Etna Sud |
| `giovanna` | `9999` | **admin** | tutti |

## Le due interfacce

**Operatore** (`/op`) — nessun termine tecnico, nessun form, una cosa alla volta:

- **Carica** un documento (foto/PDF); il sistema lo legge e mostra un riepilogo
  leggibile.
- **Documenti**: lo stato di ciò che hai caricato, con un semaforo.
- **Conferma** quando è giusto, oppure **segnala** in un tocco se qualcosa non torna.
- **Chiedi**: domande in linguaggio naturale sui propri cantieri.

**Admin** (`/admin`) — l'ufficio, con la meccanica in chiaro:

- **Cruscotto** — costi per cantiere/fornitore, ritenute, ore, avanzamento budget.
- **Dati** — CRUD generico su tutte le entità, guidato dagli schemi.
- **Scostamenti** — computo ↔ consuntivo, per voce e per cantiere.
- **Revisione** — coda delle bozze da controllare; confronto con l'originale,
  feedback sui campi, *valida* (entra nel golden set), *collega al computo*.
- **Segnalazioni** — le note degli operatori; da qui parte l'Improver.
- **Interroga** — domanda in italiano → SQL generato → tabella.
- **Workflows** — versioni, manifest, statistiche dei run, patch dell'Improver
  con il replay sul golden set, *approva/rifiuta*.
- **Skills & Tools** — registry dei tool con contatori d'uso, candidati al
  consolidamento (viste, tool parametrici, funzioni Python) e idoneità T3.
- **Dataset** — costo per documento, tool call, export `toolcalls.jsonl` e
  `finetuning.jsonl`, query ricorrenti.
- **Log** — la diagnostica: eventi di tutte le fasi, errori in evidenza, livello
  configurabile a runtime (vedi sotto).

## Il giro della demo (≈ 10 minuti)

**1 · Estrazione e segnalazione (Operatore, `salvo` / `1111`).**
*Carica un documento* → `fixtures/fattura-studio-bianchi.pdf` (una parcella con
**ritenuta d'acconto in calce**). Il sistema legge e mostra il riepilogo: la
versione 1.0 del workflow **non conosce** la ritenuta, quindi manca. Tocca
*👎 Qualcosa non torna* → «manca la ritenuta d'acconto» → *Invia*.

**2 · Miglioramento del workflow (Admin, `giovanna` / `9999`).**
In **Segnalazioni** trovi la nota → *Migliora il workflow*. In **Workflows**
l'**Improver** ha proposto una **patch** (diff colorato) e l'ha provata sul
**golden set** (replay N/N). Senza regressioni → *Approva e applica*: il workflow
passa a **v1.1** e il documento d'origine viene rielaborato — ora la ritenuta
(800 €) c'è. In **Revisione** apri la bozza corretta, confrontala con l'originale
e *Salva come validato*: diventa una regressione futura.

**3 · Multi-entità e costi.**
Carica anche `fixtures/ddt-edil-sud.pdf`, `fixtures/sal-capannone-etna.pdf`,
`fixtures/rapportino-le-palme.pdf`: il **classificatore** li riconosce e li
instrada — nessun codice nuovo, solo un manifest per tipo. Nel **Cruscotto**
compaiono i KPI di DDT, SAL, ore e manodopera; il nome di un cantiere apre il
**registro** con **Scarica Excel**. In **Scostamenti** vedi il confronto
computo ↔ consuntivo; in revisione di una fattura, *Collega al computo* fa
risalire la spesa sulle voci.

**4 · Interrogazione.**
In **Interroga**: «Quali fatture hanno una ritenuta d'acconto?» → SQL generato +
tabella (guardrail: solo `SELECT` sulle viste, `LIMIT` forzato). Le query che si
ripetono diventano candidate al consolidamento in **Skills & Tools**.

**5 · Consolidamento e costo marginale ~0.**
In **Skills & Tools → Candidati Python**, il **Toolsmith** individua un calcolo
ricorrente dal *delta fra bozza e dato validato* (l'esempio guida è la **ritenuta
d'acconto**) e propone una **funzione Python** con i **test generati dai trace**.
La proposta è ispezionabile (codice, esito in **sandbox**, esempi): *Approva* → il
tool è registrato in `data/tools/<nome>/` ed eseguito **solo** in sandbox isolata,
e la skill viene patchata per chiamarlo, con l'LLM come **fallback**. In
**Dataset → Idoneità T3**, l'harness (`/api/dataset/eval-t3`) misura un modello
locale candidato contro T1 e indica i workflow "pronti".

## Comandi

| Comando | Cosa fa |
|---|---|
| `make setup` | Prima installazione (venv + dipendenze) |
| `make dev` | Backend (:8000) + frontend (:5173) |
| `make seed` | Crea il repo dati `./data` (git separato) |
| `make fixtures` | Genera i PDF sintetici in `./fixtures` (fatture + DDT/SAL/rapportino) |
| `make demo` | Seed + fixtures + istruzioni del giro |
| `make test` | Test backend (pytest) |
| `make lint` | Ruff (backend) + ESLint (frontend) |

## Test

I test **non richiedono una chiave LLM**: usano un trasporto finto e deterministico.

```bash
make test                                    # intera suite backend (pytest)
# oppure, per un singolo file / test:
cd backend && . .venv/bin/activate
pytest tests/test_improver_e2e.py            # lo scenario "ritenuta d'acconto"
pytest tests/test_simulazione_mese.py        # simulazione di un mese su 10 cantieri
pytest -k ritenuta                           # per parola chiave
```

La suite copre ogni livello: unità (DAL, gateway, runtime, regole, viste, sandbox,
classificatore, logbook), API (documenti, revisione, entità, cruscotto, registro,
report, Toolsmith, harness T3, log) ed **end-to-end** (ciclo Improver,
consolidamento dei tool, escalation T3→T1). C'è inoltre un **pacchetto di
simulazione** che ricostruisce un mese di attività reale — 10 cantieri, 100
dipendenti, rapportini/DDT/fatture/SAL/pozzetti/cronoprogrammi — e verifica che
cruscotto, registri, scostamenti, report Excel e permessi restino coerenti a quella
scala (`tests/simulazione.py` + `tests/test_simulazione_mese.py`).

## Architettura

- **Storage** — il file system è la **fonte di verità**: un JSON per entità in un
  repo git separato (`./data`), ogni mutazione è un commit (audit completo).
  **DuckDB** legge quei file per le query — nessun DB server, nessun ORM. Tutte le
  scritture passano dal `dal.py`, serializzate da un unico lock (single-writer).
- **Gateway** (litellm) — punto d'accesso unico ai modelli; i workflow dichiarano
  un *tier*, non un modello, e ogni chiamata riuscita finisce nel trace con token,
  costo e latenza.
- **Workflow-as-data** — manifest YAML + skill Markdown in `data/workflows/`, in
  italiano; l'Improver li modifica, gli umani approvano.
- **Runtime** — orchestratore generico: carica il manifest, esegue gli step
  (estrazione con giri agente↔tool, validazione a regole, salvataggio bozza),
  non solleva mai verso il chiamante (ogni fallimento → esito `errore` + issue
  automatica) e traccia tutto.
- **Bozza-first** — nessun dato diventa `validato` senza conferma umana; l'operatore
  non approva mai una patch.

**Estendere = aggiungere dati, non codice.** Una nuova entità è uno schema JSON +
una riga nel registry dei tipi + una vista + un manifest con la sua skill:
`runtime.py`, `gateway.py`, `dal.py` **non cambiano**. Un consolidamento è una
vista `v_*`, un tool `t_*` o una funzione Python in `data/tools/` — sempre dato
versionato e approvato. Un nuovo modello è una variabile d'ambiente.

## Log e diagnostica

Ogni fase del processo scrive su un **logbook** trasversale, con gli **errori** in
primo piano: avvio, chiamate API (ogni richiesta e ogni eccezione non gestita, con
traceback), scritture/commit del DAL, gateway LLM (retry ed esaurimento trasporto),
runtime (avvio/esito run, escalation di tier, validazioni, salvataggi, fallimenti),
tool, sandbox e Improver. È complementare al **trace** per-run (`data/traces/…`,
la ricostruzione dettagliata di una singola esecuzione): il logbook raccoglie tutto
in un unico flusso interrogabile.

- **Dove** — `data/logs/AAAA/MM/GG.jsonl`, dentro la fonte di verità ma
  *diagnostico*, non stato applicativo: è **gitignorato** nel repo dati, quindi non
  produce commit e non rende "sporco" il repo.
- **Livello configurabile** — default all'avvio da `LOG_LEVEL`
  (`DEBUG|INFO|WARNING|ERROR|CRITICAL`); l'ufficio lo cambia **a runtime** dalla
  pagina **Log**. La scelta è persistita in `data/logs/livello` e sopravvive al
  riavvio.
- **Interfaccia** — Admin → **Log**: conteggi per livello, selettore del livello
  attivo, filtri (livello minimo, fase, testo, periodo), traceback espandibili con
  il `run_id` che rimanda al trace, auto-aggiornamento e scarico del file del giorno.
- **API** (solo admin) — `GET /api/logs`, `GET /api/logs/stats`,
  `GET|PUT /api/logs/config`, `GET /api/logs/export`.

## Approfondimenti

- [`analisi-progettazione.md`](analisi-progettazione.md) — architettura, principi e
  decisioni chiave (ADR).
- [`piano-implementazione.md`](piano-implementazione.md),
  [`piano-implementazione-fase2.md`](piano-implementazione-fase2.md),
  [`piano-implementazione-fase3.md`](piano-implementazione-fase3.md) — contratti e
  milestone.
- [`docs/finetuning-runbook.md`](docs/finetuning-runbook.md) — il runbook operativo
  per addestrare il tier locale.
- `mockup.html` — il riferimento UX.

## Note

- **Senza chiave LLM** non giri il flusso reale, ma i **test** funzionano lo stesso
  (trasporto LLM finto e deterministico): `make test`.
- Lo scenario **ritenuta d'acconto** è la *definition of done* del prodotto ed è
  coperto da un test end-to-end che non deve mai rompersi
  (`backend/tests/test_improver_e2e.py`); lo stesso calcolo è anche l'esempio guida
  del Toolsmith (`test_toolsmith_m17.py`).
- Il **codice generato** gira solo in **sandbox isolata** (subprocess, import in
  whitelist, niente rete/FS/ambiente, limiti CPU/memoria/tempo): mai importato
  in-process. Le forme d'abuso sono coperte da `test_sandbox.py`.
- I dati d'esempio sono immaginari (cantieri, fornitori e fatture della zona di
  Catania) e servono solo alla demo.
