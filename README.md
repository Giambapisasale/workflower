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

**Agente dati conversazionale.** Operatore e ufficio fanno domande in italiano
(«Quali fatture hanno una ritenuta d'acconto?»); l'agente sceglie solo fra tool
di lettura con parametri validati, risponde in modo chiaro e conserva gli ultimi
scambi della conversazione. L'operatore riceve esclusivamente dati dei propri
cantieri, filtrati dal server; l'ufficio può vedere tool usati e trace. SQL,
viste e macro restano dettagli interni e non vengono mai inviati al modello.

**Ciclo di auto-miglioramento.** Quando qualcosa non torna, l'operatore segnala in
un tocco. L'**Improver** analizza trace e feedback, propone una **patch** al
workflow (diff della skill/manifest), la **riprova sul golden set** (i run già
validati, come test di regressione) e — solo dopo l'ok umano — pubblica una nuova
versione, rielaborando il documento d'origine. L'ufficio può anche **dettare una
regola in linguaggio naturale** (es. «individua il fornitore dalla partita IVA»)
da **Revisione** o **Workflows**: diventa una proposta di patch, con la stessa rete
di sicurezza del replay, da approvare.

**Un inserimento sbagliato si scarta, e si ripristina.** Una fattura letta male, un
doppione, un documento caricato per errore: da **Revisione** si *scarta* indicando il
**motivo**. Non è una cancellazione — l'entità esce da costi, revisione e report
spostandosi in `data/scartati/`, dove resta come dato versionato e da cui si
**ripristina** (`Dati → Scartati`). Lo scarto toglie anche il caso golden nato da quel
documento (altrimenti l'Improver misurerebbe ogni nuova versione contro un dato che
l'ufficio ha ripudiato), chiude la segnalazione aperta e aggiorna il fascicolo
dell'operatore, che smette di dire «tutto a posto». Se il documento è **già arrivato in
contabilità**, lo scarto è **bloccato** finché non lo si sistema in ERPNext: Workflower
legge il `docstatus` a valle e dice cosa fare — eliminare la bozza o annullare il
documento confermato — senza mai scrivere annullamenti nell'ERP.

**Anagrafica mancante → creala dal documento.** Se un documento cita un fornitore
o un cantiere non ancora a sistema, l'estrazione lascia il riferimento vuoto e in
**revisione** compare la proposta di **creare l'anagrafica mancante** — precompilata
coi dati letti dal documento (ragione sociale, partita IVA…) — oppure di collegarne
una esistente. È generico: vale per ogni campo-riferimento e ogni tipo di documento.

**Evoluzione controllata delle capacità.** Le operazioni ripetute non restano a
carico dell'LLM per sempre: l'ufficio può proporre un nuovo strumento dati e/o una
skill dichiarativa. Ogni proposta ha intenti, ruoli, perimetro, esempi, test mirato
e replay sui golden agent-native; viene pubblicata solo dopo approvazione umana. Le
implementazioni deterministiche storiche restano interne al servizio. Il Toolsmith
continua a generare funzioni Python sandboxate per i workflow documentali.

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
(SOTA, per estrazione e Improver), `LLM_T2_MODEL` (medio, per l'agente dati e
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
  feedback sui campi, *valida* (entra nel golden set), *collega al computo*,
  **crea l'anagrafica mancante dal documento**, il **trace** del run,
  **istruzioni per migliorare il workflow** e **scarta** (vedi sotto).
- **Segnalazioni** — le note degli operatori; da qui parte l'Improver.
- **Agente dati** — chat sui dati con memoria limitata, tool letti e trace.
- **Evoluzione agente** — copertura del catalogo, lacune e proposte di nuovi
  tool o skill, pubblicabili solo dopo replay golden e approvazione.
- **Workflows** — versioni, manifest, statistiche dei run, patch dell'Improver
  con il replay sul golden set, *approva/rifiuta*, **migliora con un'istruzione**
  e i **casi golden** (la rete di regressione, ispezionabile e correggibile).
- **Run** — tutte le esecuzioni con esito, costo e durata, filtrabili per
  workflow ed esito, e il **trace** completo di ognuna.
- **Skills & Tools** — strumenti dei workflow documentali e accesso al percorso
  governato per estendere l'agente dati; il **Toolsmith** mantiene i suoi candidati
  Python sandboxati.
- **Dataset** — costi, tool call e **idoneità T3** del modello locale, inclusa la
  valutazione agent-native su strumenti, argomenti e risultati normalizzati.
- **Contabilità** — le sincronizzazioni verso l'ERP: quanti documenti sono
  arrivati a valle, quelli rimasti indietro con *Riprova*, il registro dei
  tentativi con il motivo dei fallimenti (vedi `docs/erp-integrazione.md`).
- **Log** — la diagnostica: eventi di tutte le fasi, errori in evidenza, livello
  configurabile a runtime (vedi sotto).
- **Diagnosi** — l'analisi automatica degli errori con proposta di risoluzione
  (vedi sotto).

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

**4 · Agente dati.**
In **Agente dati**: «Quali fatture hanno una ritenuta d'acconto?» → risposta
conversazionale fondata sui tool dati approvati. In **Evoluzione agente**, una
lacuna può diventare una proposta di tool o skill: viene verificata sui golden
storici e pubblicata solo con approvazione dell'ufficio.

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
| `make reseed` | **Azzera** `./data` e lo ricrea dal seed (perde i dati e la loro storia) |
| `make data-sync` | Allinea workflow e schemi di `./data` a quelli dell'applicazione (`ARGS=--applica` per scrivere) |
| `make demo-reset` | Rifà `./data` dal seed **conservando** golden, dataset e azienda (`ARGS=--applica`) |
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
classificatore, logbook, diagnostico e lettura del proprio codice), API (documenti,
revisione, entità, cruscotto, registro, report, Toolsmith, harness T3, log,
diagnosi) ed **end-to-end** (ciclo Improver, consolidamento dei tool, escalation
T3→T1). C'è inoltre un **pacchetto di
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
una riga nel registry dei tipi + una skill di workflow. Per l'agente dati una nuova
capacità è una proposta DSL versionata e approvata; il compilatore server-side la
lega a fonti interne affidabili. Un nuovo modello è una variabile d'ambiente.

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

### Diagnosi automatica degli errori

L'ultimo tassello: quando compaiono errori, un **trigger** avvia il **Diagnostico**,
che ne analizza la causa e **propone una risoluzione**. Per capire *dove* sta il
problema, il sistema **legge il proprio codice sorgente**: ogni errore porta con
sé il **traceback**, da cui si risale ai file e alle righe esatte del package
`app` (letti in sola lettura, confinati all'albero dell'applicazione). Poi
classifica:

- **`dato`** — la correzione sta in un *dato modificabile* (una **skill**, un
  **tool**, uno **schema**, un **manifest**, una **config**): propone la modifica,
  e per le skill di estrazione rimanda all'**Improver** (che riprova sul golden
  set prima di pubblicare).
- **`architettura`** — la correzione richiede di toccare il **codice-cornice**
  (`backend/app/**.py`): **sola analisi** con la modifica raccomandata, mai
  applicata in automatico.

Niente si applica da solo: ogni diagnosi è una **proposta** ispezionabile in
`data/diagnoses/` (analisi, causa radice, proposta, codice letto, traceback,
occorrenze), in attesa di una decisione umana. Le firme d'errore già viste non
ripartono: se ne aggiorna solo il conteggio. Il trigger automatico è **opt-in**
(`DIAGNOSTICA_AUTO=1`, perché ogni analisi è una chiamata LLM); l'analisi si può
comunque lanciare a mano.

Non solo errori: un **warning ripetuto** entra in diagnosi come *famiglia*, dalla
quinta occorrenza della stessa firma in poi. Serve a intercettare i guasti
sistematici che vivono sotto la soglia dell'errore — un passo best-effort che
fallisce **sempre** (un allegato che non arriva mai a destinazione) non è rumore,
anche se ogni singola riga è solo un `WARNING`.

- **Interfaccia** — Admin → **Diagnosi**: badge di categoria, proposta in
  evidenza, azione suggerita (con scorciatoia all'Improver), file coinvolti,
  codice letto e traceback espandibili; *Segna risolta* / *Archivia*.
- **API** (solo admin) — `GET /api/diagnoses`, `GET /api/diagnoses/{id}`,
  `POST /api/diagnoses/analyze`, `POST /api/diagnoses/{id}/resolve`,
  `POST /api/diagnoses/{id}/archive`.

## Parser documenti su GPU (Docling) — opzionale

Di serie il modello legge i documenti **come immagini** (`ocr_pdf`: pagine → PNG →
LLM multimodale). Con un sidecar [Docling](https://github.com/docling-project/docling)
acceso guadagna un secondo strumento, `leggi_documento`, che restituisce il
documento come **testo con le tabelle ricostruite**:

```bash
make docling-up      # container con la GPU (profilo compose "docling")
make docling-check   # risponde? converte? sta usando davvero la GPU?
```

e in `.env`: `DOCLING_URL=http://127.0.0.1:5001` (in compose: `http://docling:5001`).

| | `leggi_documento` | `ocr_pdf` |
|---|---|---|
| **Per cosa** | PDF nati al computer, Word `.docx`, Excel `.xlsx` | foto dal cantiere, scansioni storte |
| **Cosa dà** | Markdown con tabelle e ordine di lettura | pagine come immagini PNG |
| **Costo** | 16–34x meno token | ~2.300 token per pagina |

I due **convivono**: è la skill (dato) a dire quale usare, e su una foto il
modello vision resta la strada migliore. Senza `DOCLING_URL` il tool non viene
nemmeno registrato e il sistema si comporta esattamente come prima — Word ed
Excel tornano a essere rifiutati in caricamento, perché nessun altro sa aprirli.

Misure, limiti e il caso DGX Spark (`sm_121`) in
[`analisi-docling.md`](analisi-docling.md); messa in opera in
[`docs/deploy.md`](docs/deploy.md).

## Aggiornare un'installazione esistente

Aggiornare il codice **non** aggiorna il repo dati. Il seed crea `data/` una volta
sola — `make seed` rifiuta una cartella non vuota — quindi manifest, skill e schemi
già scritti restano quelli del giorno dell'installazione. È una conseguenza voluta
di "`/data` è la fonte di verità": quei file sono dato, e là dentro scrive anche
l'Improver quando l'ufficio approva una proposta di miglioramento.

La conseguenza pratica è che **una funzione nuova può restare invisibile**: se una
versione aggiunge un tool, il modello non lo userà mai finché il manifest nel repo
dati non lo dichiara; se aggiunge un campo, non verrà mai estratto finché lo schema
è quello vecchio. Non dà errore — dà risultati peggiori, in silenzio.

Dopo ogni aggiornamento che tocca `backend/app/seed_assets/`:

```bash
make data-sync                 # elenca e mostra il diff, non scrive niente
```

```bash
make data-sync ARGS=--applica  # copia e committa nel repo dati
```

In produzione il repo dati sta in un volume, quindi lo stesso modulo si invoca
dentro il container (non serve `make`, non serve il venv):

```bash
git pull && docker compose build app && docker compose up -d app
```

```bash
docker compose exec app python -m app.sync_dati
```

```bash
docker compose exec app python -m app.sync_dati --applica
```

Non serve riavviare: manifest e schemi si rileggono da disco a ogni run.

Il comando è **conservativo** per costruzione:

- di suo non scrive niente, mostra solo cosa cambierebbe;
- **non cancella mai**: i workflow e gli schemi che esistono solo nel repo dati
  (scritti a mano) non vengono nemmeno segnalati;
- **non sovrascrive ciò che l'Improver ha migliorato**: se un file ha nel repo dati
  un commit che non viene dal seed né da un allineamento precedente, viene marcato
  `!` e saltato. Per includerlo serve `--forza`, e si perde quella miglioria;
- differenze di solo fine-riga (repo dati creato su Windows, immagine costruita su
  Linux) non contano come modifiche.

Ed è reversibile, perché è un commit come gli altri:

```bash
docker compose exec app sh -c 'cd /data/repo && git revert HEAD'
```

Se un'estrazione non riconosce niente, il posto dove guardare è il **trace del run**
(visibile dalla UI dell'ufficio, o in `data/traces/AAAA/MM/run-*.jsonl`): elenca gli
strumenti chiamati e come sono andati, ed è lì che si vede se il modello ha provato
lo strumento sbagliato perché il manifest era indietro.

## Deploy (versione di prova)

Workflower gira come **singolo container** (il backend FastAPI serve anche il
frontend buildato), avviato con `docker compose` sul `Dockerfile` del repo su una
macchina che controlliamo noi — il server aziendale o una VPS. Vincolo chiave: lo
stato è un **repo git su disco**, quindi serve un **volume persistente** (niente
serverless, niente filesystem effimero). L'infrastruttura di riferimento è
**on-premise con GPU NVIDIA** (DGX Spark `arm64`, RTX 4090, RTX 3080 di sviluppo):
l'app non usa la GPU, la usano i servizi affiancati (parser documenti, tier T3).
Guida passo-passo, variabili d'ambiente e note operative (un solo worker, backup
via `git push`, cambio dei PIN demo, costi LLM) in
[`docs/deploy.md`](docs/deploy.md).

## Approfondimenti

- [`analisi-progettazione.md`](analisi-progettazione.md) — architettura, principi e
  decisioni chiave (ADR).
- [`guida_utente/`](guida_utente/README.md) — **come si usa e come si mostra**:
  guida passo passo per caso d'uso, dodici documenti d'esempio con l'esito
  misurato di ciascuno, copione di demo da trenta minuti e le risposte alle
  obiezioni ricorrenti.
- [`docs/test-book.md`](docs/test-book.md) — il **test-book manuale**: 173 casi di
  prova su tutti i casi d'uso, con ambiente, baseline attesa, matrice di copertura,
  limiti noti e foglio esiti.
- [`docs/deploy.md`](docs/deploy.md) — mettere in piedi una versione di prova
  (compose su server aziendale o VPS, infrastruttura GPU on-premise).
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
