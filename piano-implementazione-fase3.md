# Workflower — Piano di implementazione Fase 3 (M14–M21)

> **Contesto**: le Fasi 1 (PoC, M0–M6) e 2 (M7–M13) sono complete e verdi ai test. La
> piattaforma copre il giro end-to-end multi-entità (fattura, DDT, SAL, rapportino,
> computo), classificazione e instradamento documenti, collegamento voci e scostamenti,
> cruscotto + registro per cantiere, report Excel, dataset builder, pagina Skills & Tools,
> CRUD manuale schema-driven, e il **consolidamento in due forme dato-non-codice**:
> viste `v_*` e tool parametrici `t_*` (macro tabellari DuckDB).
>
> Questa fase realizza ciò che l'analisi (`analisi-progettazione.md` §6) chiamava **F4**
> — *Toolsmith, distillazione, tier T3* — più la **metà interna dell'ex-F3** (registri e
> riepiloghi automatici: pozzetti, cronoprogramma). Le **integrazioni esterne M365/Graph**
> (SharePoint, Planner, Outlook, SSO Entra) slittano a una **Fase 4**, coerentemente con
> l'obiettivo dichiarato: *completare la piattaforma al netto dei servizi esterni*.
>
> Valgono tutte le regole di `CLAUDE.md`: `/data` è la fonte di verità (ogni mutazione =
> commit), scritture solo via `dal.py`, DuckDB read-only, modelli LLM mai hard-coded (tier
> da env), prompt/skill in italiano dentro `data/workflows/**`, UI Operatore senza termini
> tecnici, **pytest verde a ogni milestone**, e — non negoziabile — lo scenario "ritenuta
> d'acconto" (M5) non si rompe mai. Ogni milestone termina con un commit dedicato.

## 0. Obiettivo della Fase 3

Portare la piattaforma alla **maturità a costo marginale ~0** promessa dall'analisi (§1,
§3.6, §3.7): le operazioni ricorrenti smettono di consumare token perché vengono
**consolidate in codice deterministico**, e i workflow maturi migrano su un **modello locale
fine-tuned (tier T3)** con escalation automatica al modello SOTA (T1) quando serve. È il
passo che l'analisi chiama "hardening" delle skill: dalle due forme dato-non-codice già
consegnate (vista SQL, macro parametrica) alla **terza forma — il tool Python** — l'unica in
grado di catturare *calcoli e trasformazioni* che l'SQL non esprime.

Contestualmente si completa la copertura di dominio **interna**: le entità ancora non
implementate (materiali, mezzi, lavorazioni, scadenze) come **puro dato**, a riprova
dell'invariante, e i **registri automatici** (pozzetti, cronoprogramma) che si aggiornano da
soli a ogni documento. Nessuna dipendenza da servizi esterni: tutto è verificabile in locale
col trasporto LLM finto, come in Fase 2.

## 1. Principio guida (invariante di Fase 3)

> **Il codice generato è DATO, non runtime.** Un tool Python consolidato vive in
> `data/tools/<nome>/` (sorgente + schema + test + voce di ledger), versionato e committato
> come lo sono le viste `v_*` e le macro `t_*`. Il runtime **non lo importa mai in-process**:
> lo **esegue solo in una sandbox isolata** (subprocess, niente rete/filesystem/ambiente,
> import in whitelist, limiti di CPU/memoria/tempo). La cornice stabile — `runtime.py`,
> `gateway.py`, `dal.py`, `tracer.py` — non cambia: cresce solo il dato.
>
> Le **uniche estensioni strutturali** ammesse sono le *capacità nuove* (come lo furono a suo
> tempo il classificatore e il collega): la **sandbox** (M14), il **loader dinamico dei tool**
> dentro `Toolset` (M15), il **Toolsmith** (M16–M17), l'**harness di valutazione T3** (M18) e
> l'**escalation T3→T1** (M19). Ognuna è un modulo a sé, iniettabile e testabile. Un tool
> consolidato non ne aggiunge mai altre: consolidare resta una mutazione di dati + commit, con
> l'umano che approva (§3.6, human-in-the-loop).

## 2. Milestone

### M14 — Sandbox di esecuzione per codice generato
**Perché**: prima di *generare* codice bisogna poterlo *eseguire senza rischi*. È il §3.6
punto 3 ("la esegue in sandbox contro i test") e la precondizione di sicurezza dell'intera
fase: da qui in poi il sistema esegue codice scritto da un LLM.

- Modulo `core/sandbox.py` (capacità nuova): esegue una funzione pura
  `esegui(**kwargs) -> dict` in un **subprocess isolato**. Contratto I/O = JSON dentro, JSON
  fuori (gli stessi argomenti che l'LLM passerebbe al tool); **nessun** accesso a DAL,
  filesystem di `/data`, rete o variabili d'ambiente.
- Guardrail: **import in whitelist** (es. `math`, `datetime`, `decimal`, `re`; vietati `os`,
  `sys`, `subprocess`, `socket`, `open`, dunder pericolosi), **timeout** wall-clock, **limite
  di memoria/CPU**, output troncato. Su Linux: `resource` + rimozione della rete; su Windows
  (piattaforma di sviluppo): subprocess + timeout + Job Object per la memoria, dietro la
  **stessa interfaccia**.
- Un fallimento della sandbox (timeout, import vietato, eccezione) è un **errore di tool**
  (`ToolError`), non un crash: torna al chiamante come "il tool non è utilizzabile".
- **AC**: un tool-campione buono gira e ritorna il risultato atteso; ogni vettore d'abuso
  (rete, lettura/scrittura file, `os.system`, ciclo infinito, esplosione di memoria) è
  rifiutato o terminato entro i limiti; nessun percorso della sandbox scrive in `/data` o
  raggiunge la rete.

### M15 — Registry dei tool dinamico (dato) + ciclo di vita
**Perché**: oggi `Toolset._registro` è statico (tool nativi hard-coded). Per caricare i tool
consolidati **come dato** serve un loader che li scopra in `data/tools/`, senza toccare né
`runtime.py` (che già invoca `toolset.esegui`) né la firma dei tool nativi.

- `Toolset` esteso con un **loader**: legge il registro `data/dataset/pytools.jsonl` (fonte di
  verità) e, per ogni tool consolidato, ne espone lo schema function-calling e un handler che
  **passa dalla sandbox** (M14). I tool nativi restano invariati; i consolidati si aggiungono
  come dato.
- Ciclo di vita `esplorativa → candidata → consolidata → deprecata` nel ledger e nella pagina
  Skills & Tools (che già mostra `usi`/`ciclo`).
- Primitive DAL `consolida_pytool` / `elimina_pytool`, gemelle di `consolida_tool`: ledger +
  file sorgente in `data/tools/<nome>/`, commit atomico sotto lock, e **rete di sicurezza in
  stile `_commit_catalogo`** — carica il tool ed esegue i suoi test in sandbox *prima* di
  committare; se non passano, rollback + `CatalogoNonValido` (→ HTTP 409).
- **AC**: un tool Python posato a mano in `data/tools/` è caricato, compare nel registry con
  contatori e stato di ciclo, ed è invocabile da un workflow **attraverso la sandbox**; la sua
  rimozione libera il candidato senza rompere il runtime; svuotare i tool non spegne nulla.

### M16 — Toolsmith: candidato → generazione → test dai trace → proposta
**Perché**: è il §3.6 punti 1–2. Automatizza la scrittura del tool deterministico e — punto
critico — **ne genera i test dai trace storici già validati**, non da esempi inventati.

- **Sorgente dei candidati**: le *trasformazioni deterministiche ricorrenti* che l'SQL non
  cattura — tipicamente **calcoli/normalizzazioni post-estrazione**, emersi dal *delta fra la
  bozza estratta e il dato validato* dall'ufficio, più le regole di manifest che falliscono e
  vengono corrette allo stesso modo (l'Improver §M5 ne è il segnale). L'esempio canonico: il
  **calcolo della ritenuta d'acconto** — deterministico, oggi affidato al prompt.
  *Nota di progetto*: il trace attuale non registra le derivazioni intermedie; M16 aggiunge una
  piccola **instrumentazione** che marca nel dataset il delta estratto→validato come base
  minabile. Vive nel tracer/dataset, **non** in `runtime.py`.
- Modulo `core/toolsmith.py` (capacità nuova, iniettabile come `improver.py`): con T1
  (1) legge gli esempi I/O validati del candidato, (2) genera una **funzione Python pura** +
  schema function-calling, (3) genera i **casi di test dalle coppie storiche validate**. La
  sandbox (M14) esegue i test.
- Output = una **proposta** (analoga a una `Patch`): `{nome, codice, schema, test, esito_test,
  esempi}` salvata per l'approvazione umana. **Non registra nulla** nel registry.
- **AC**: dato un insieme di trace validati con un calcolo ricorrente, il Toolsmith propone un
  tool Python i cui test (dai trace) passano in sandbox; la proposta è ispezionabile; nulla è
  ancora attivo. Lo scenario ritenuta resta verde.

### M17 — Approvazione, attivazione e riscrittura della skill (chiude il ciclo)
**Perché**: chiude il §3.6 punto 4 ("la registra e aggiorna la skill perché la invochi").
Compone Toolsmith + Improver: il tool nuovo diventa attivo **e** la skill impara a usarlo.

- **UI admin** — pannello "Candidati Python" in Skills & Tools, gemello del pannello patch
  dell'Improver: diff del codice, test generati + esito, esempi storici, **Approva/Rifiuta**.
- Approva → `DAL.consolida_pytool` (M15) registra il tool; poi il Toolsmith propone una **patch
  di skill** riusando la macchina dell'Improver (§M5): la skill impara a **chiamare il tool
  prima**, con l'LLM come *fallback*. La patch passa dal **replay sul golden set** e
  dall'approvazione, esattamente come oggi.
- **Fallback non negoziabile**: se il tool consolidato erra, va in timeout o produce output
  fuori contratto, il runtime **ricade sull'LLM** (T1). Il tool è un'ottimizzazione, mai un
  single-point-of-failure — stesso spirito del fallback prudente del classificatore.
- **AC**: end-to-end — calcolo ricorrente → proposta Toolsmith → approvo → tool registrato +
  skill patchata (replay golden verde) → il re-run usa il tool deterministico (token ~0 su
  quello step) → un guasto forzato del tool ricade sull'LLM in modo pulito. Ritenuta verde.

### M18 — Harness di valutazione offline del tier T3
**Perché**: prima di *instradare* un workflow sul modello locale, bisogna *misurare* se è
abbastanza bravo. È il presupposto della distillazione (§3.7) e dell'escalation (§3.1).

- Riusa il dataset builder (`dataset.esempi_finetuning`, già presente). Nuovo `core/eval_t3.py`:
  **replay** degli esempi validati contro un **modello candidato T3** (via gateway, quindi un
  qualsiasi endpoint locale raggiungibile da litellm), con metriche di **function-calling
  accuracy** (tool giusto, argomenti giusti) rispetto al ground truth validato, e un confronto
  **accuratezza T3 vs T1 per workflow**.
- Report mostrato/scaricabile in Log & Dataset: quali workflow sono "pronti per T3". Nessun
  training qui — solo misura; nei test gira col trasporto LLM finto.
- **AC**: l'harness assegna un punteggio a un modello candidato sul set validato ed emette un
  report (accuratezza, regressioni vs T1); il test usa il trasporto finto.

### M19 — Attivazione T3 + escalation T3→T1 + runbook di fine-tuning
**Perché**: chiude l'anello del costo marginale. Oggi `gateway.modello("T3")` ricade
silenziosamente su T1 e l'escalation è "lavoro futuro": qui diventa reale.

- **Wiring T3**: `LLM_T3_MODEL` punta a un endpoint locale (Ollama/llama.cpp via base_url
  OpenAI-compatible di litellm); documentato in `.env.example`.
- **Escalation reale**: uno step instradato su T3 gira lì per primo; su **errore**, **bassa
  confidence** o **output fuori contratto** il gateway/runtime **escala a T1** e **traccia
  l'escalation** (l'osservabilità mostra la "% escalation" per workflow = segnale che il
  modello T3 va riaddestrato). Il manifest continua a dichiarare solo il *tier* (§3.1);
  l'idoneità a T3 discende dalla maturità di consolidamento e resta dato.
- **Training reale = runbook** (`docs/finetuning-runbook.md`): come prendere `finetuning.jsonl`,
  addestrare FunctionGemma in LoRA, servirlo in locale, puntarci `LLM_T3_MODEL`. **Non eseguito
  in-repo** (nessuna dipendenza GPU): T3 si accende quando il modello è pronto.
- **AC**: con `LLM_T3_MODEL` impostato (finto nei test) uno step su T3 gira su T3 ed escala a
  T1 su bassa confidence/errore, con l'escalation nel trace; senza la variabile il
  comportamento è invariato (T1). Il cost tracking mostra T3 ≈ 0.

### M20 — Entità di dominio mancanti (puro dato)
**Perché**: completa la copertura dell'analisi §3.3 e **riprova l'invariante §1 su scala**:
aggiungere un'entità = dati, zero codice nel runtime.

- Nuove entità come **puro dato**: `materiale`, `mezzo`, `lavorazione`, `scadenza` — schema in
  `seed_assets/schemas/`, riga in `ENTITY_TYPES`, vista in `views.sql`, e — dove nascono da un
  documento — un workflow (manifest + skill); le anagrafiche (mezzo, materiale) nascono dalla
  CRUD admin (M13, già disponibile). Seed + fixtures + test.
- **AC**: ogni entità è creabile (via CRUD e/o workflow), compare in viste/registro e nel
  cruscotto; **zero modifiche** a `runtime.py`/`gateway.py`/`dal.py` (a parte le righe di
  `ENTITY_TYPES`, che sono registry-dato). La suite resta verde.

### M21 — Registri e riepiloghi automatici: Pozzetti e Cronoprogramma
**Perché**: è la metà **interna** dell'ex-F3 (§6/§3.8): "registri e riepiloghi automatici
(pozzetti, cronoprogrammi)". Estende il registro per cantiere (M10) e l'Excel (M11).

- Entità `pozzetto` (registro dei manufatti di cantiere, con stato) e `cronoprogramma`
  (pianificazione lavorazioni vs avanzamento reale, da SAL/rapportini). Viste derivate che si
  **aggiornano da sole** a ogni documento.
- Il **cronoprogramma** confronta pianificato vs consuntivo (riusa lo scostamento §M9); i
  **pozzetti** sono un registro alimentato dai documenti (DDT/foto). Esposti in
  cruscotto/registro e nel report Excel (foglio dedicato).
- **AC**: il registro pozzetti e il riepilogo cronoprogramma si popolano dalle entità esistenti
  e si aggiornano a ogni nuovo documento; visibili in dashboard/registro e nell'xlsx.

## 3. Rischi e mitigazioni di Fase 3

| Rischio | Mitigazione |
|---|---|
| **Esecuzione di codice generato da un LLM** | Sandbox obbligatoria (M14) a runtime *e* nei test: subprocess isolato, import in whitelist, no rete/FS/ambiente, limiti CPU/memoria/tempo. Il codice è dato, mai importato in-process. Approvazione umana su diff + test verdi prima dell'attivazione. |
| Tool consolidato che sbaglia in produzione | Fallback all'LLM su errore/timeout/out-of-contract (M17): il tool è un'ottimizzazione, mai un SPOF. Test generati dai trace validati, non inventati. Reversibile via git; la rimozione libera di nuovo il candidato. |
| Candidati Python difficili da individuare | M16 parte dai *calcoli/normalizzazioni* (delta estratto→validato + regole), non dai parser di layout documentali (rimandati): tractabili e già presenti nei dati. Instrumentazione minima nel dataset, non nel runtime. |
| Modello T3 non abbastanza accurato | Non si instrada su T3 senza il via libera dell'harness (M18); escalation automatica a T1 (M19) con "% escalation" tracciata come segnale di ri-training. Training reale fuori repo (runbook), attivazione a modello pronto. |
| Portabilità sandbox (Windows dev / Linux prod) | Stessa interfaccia, due back-end: `resource`+no-net su Linux, subprocess+timeout+Job Object su Windows. Test su entrambe le forme d'abuso. |
| Rottura dello scenario ritenuta (M5) | È l'esempio guida del Toolsmith: test di regressione a ogni milestone; il fallback all'LLM garantisce che, con o senza tool, l'estrazione resti corretta. |

## 4. Non-goal della Fase 3 (restano fuori)

Integrazioni M365/Graph (watcher SharePoint, Planner, ingest Outlook), **SSO Entra ID**,
packaging/deploy di prodotto, backup/osservabilità operativa, test di carico, multi-tenant,
i18n, notifiche push → **Fase 4** (servizi esterni e hardening di prodotto). Il **training
LoRA reale** di FunctionGemma resta un runbook operativo fuori dal repo (M19): la fase cabla
attivazione e valutazione, non esegue il training. I **parser Python di layout documentali**
(estrazione deterministica da immagine) restano fuori: il Toolsmith di questa fase consolida
calcoli e trasformazioni, non l'OCR.
