# Workflower — Piano di implementazione Fase 2 (M7–M12)

> **Contesto**: la v1 (PoC F1) è completa e verde ai test (M0–M6): giro end-to-end
> `carica-fattura`, due modalità UI, ciclo Improver con replay sul golden set. Questo
> documento estende il piano originale (`piano-implementazione.md`, che si ferma a M6)
> con la **Fase 2**, derivata dalla *Roadmap* §6 dell'analisi (`analisi-progettazione.md`)
> e dai *non-goal v1* §5 del piano — ora sbloccati. L'ancora fissa è **M11 = report
> mensili Excel (openpyxl)**, esplicitamente concordata.
>
> Valgono tutte le regole di `CLAUDE.md` e §6 del piano v1: `/data` è la fonte di
> verità (ogni mutazione = commit), scritture solo via `dal.py`, DuckDB read-only,
> modelli LLM mai hard-coded (tier da env), prompt/skill in italiano dentro
> `data/workflows/**`, UI Operatore senza termini tecnici, **pytest verde a ogni
> milestone**, e — non negoziabile — lo scenario "ritenuta d'acconto" (M5) non si
> rompe mai. Ogni milestone termina con un commit dedicato.

## 0. Obiettivo della Fase 2

Dimostrare che la tesi architetturale regge oltre la fattura: **aggiungere una
funzionalità = aggiungere dati** (schema + manifest + skill + vista), non codice nel
runtime. Si passa da un solo documento (fattura) a un **fascicolo di cantiere**
multi-entità (DDT, SAL, rapportini ore, computo), si chiude il ciclo economico
**confronto computo↔consuntivo** che il cliente ha chiesto, si consegna il dato dove
il cliente già vive (**Excel**), e si posano le fondamenta del tier locale a costo
marginale ~0 (**dataset builder** per il fine-tuning). Nessuna dipendenza da servizi
esterni (M365 resta F3): tutto è verificabile in locale con il trasporto LLM finto.

## 1. Principio guida (invariante di Fase 2)

> **Il runtime non cambia quando si aggiunge un'entità.** `runtime.py`,
> `gateway.py`, `dal.py`, `tracer.py` restano stabili. Una nuova entità è:
> (1) uno schema JSON in `seed_assets/schemas/`, (2) una riga nel registry
> `ENTITY_TYPES` di `dal.py`, (3) una vista in `views.sql`, (4) un workflow
> (manifest + skill) in `seed_assets/workflows/`. Tutto il resto è dato.

L'unica estensione strutturale ammessa è quella che introduce una **capacità nuova**
(non una nuova entità): l'instradamento per tipo documento (M7), il collegamento voci
(M9), la generazione Excel (M11), il dataset builder (M12). Ognuna vive in un modulo a
sé, iniettabile e testabile, senza toccare gli invarianti.

## 2. Milestone

### M7 — Instradamento documenti + entità DDT
**Perché**: oggi `POST /documents` esegue sempre `carica-fattura` (hard-coded). Per
avere più entità serve prima *decidere che documento è*. È la "classificazione
documenti (T2)" di §3.1 e il routing dei trigger di §3.4.

- **Classificatore** `classifica-documento` (workflow, tier T2): dalle pagine rese
  (`ocr_pdf`) sceglie il workflow d'ingresso tra quelli disponibili. Skill in
  `data/workflows/classifica-documento/`. Fallback prudente a `carica-fattura` se
  incerto — l'operatore non riceve **mai** un errore bloccante.
- **Entità `ddt`** (documento di trasporto): `ddt.schema.json` (fornitore_id,
  cantiere_id, numero, data, causale, riferimento_ordine?, righe[{descrizione,
  quantita, unita_misura}]). Un DDT descrive merce consegnata: niente IVA/totale.
- **Workflow `carica-ddt`** (manifest + `estrazione-ddt.md`): riusa
  `ocr_pdf`/`cerca_fornitore`/`cerca_cantiere`/`salva_bozza`. **Zero tool nuovi,
  zero runtime nuovo.**
- Viste `v_ddt`, `v_ddt_righe`; riga `ddt` in `ENTITY_TYPES` (`DDT-AAAA-nnnn`).
- **Infrastruttura riusabile** (una volta sola, qui): generatore fixtures generico
  (non solo fatture), fake LLM generico che legge qualunque documento sintetico +
  gestisce il classificatore, coda di revisione admin su *tutte* le bozze (non solo
  fatture).
- Seed: 2 DDT d'esempio. UI: dettaglio documento e revisione parlano "ddt".
- **AC**: il classificatore instrada fattura→`carica-fattura`, DDT→`carica-ddt`;
  upload DDT → bozza `ddt` conforme; il giro fattura (ritenuta inclusa) resta verde.

### M8 — Entità SAL e Rapportino Ore
**Perché**: completano l'insieme entità di F2 (avanzamento lavori + manodopera) e
alimentano il cruscotto con costo del lavoro e stato di avanzamento. Pura aggiunta di
dati, a riprova dell'invariante §1.

- **`sal`** (stato avanzamento lavori): cantiere_id, numero, data,
  importo_lavori_periodo, importo_progressivo, percentuale_avanzamento.
- **`rapportino`** (rapportino giornaliero di cantiere): cantiere_id, data,
  righe[{nominativo, mansione, ore, costo_orario?}].
- Workflow `carica-sal`, `carica-rapportino`; classificatore esteso a 4 tipi.
- Viste `v_sal`, `v_rapportini`, `v_rapportini_righe`; registry `SAL-AAAA-nnnn`,
  `RAP-AAAA-nnnn`. Fixtures + fake + seed + test.
- **AC**: upload SAL e rapportino → bozze conformi; il classificatore instrada 4 tipi;
  le viste espongono ore totali e avanzamento per cantiere.

### M9 — Computo di progetto + collegamento voci + scostamenti
**Perché**: è il "confronto computi/preventivi" richiesto dal cliente e
l'"aggiornamento automatico dei registri". Chiude l'anello economico previsto→speso.

- **`computo`** (computo metrico per cantiere): voci[{codice, descrizione,
  unita_misura, quantita, prezzo_unitario, importo, categoria}]. Seed di un computo
  per CNT-001; workflow `carica-computo` come bonus (l'estrazione di un computo è
  pesante: la fixture resta piccola).
- **Capacità nuova — collegamento**: tool `cerca_voce_computo` (fuzzy sulle voci del
  computo di un cantiere) e un servizio `collega` (T2) che abbina le righe di
  fattura/DDT alla voce di computo (`voce_computo_id`, già previsto nello schema).
  Endpoint admin per lanciarlo/rivederlo; nessuna scrittura automatica in `validato`.
- Viste `v_computo`, `v_computo_scostamento` (per voce: previsto vs consuntivo),
  `v_cantiere_scostamento`. Endpoint `/dashboard/scostamenti` + pannello admin.
- **AC**: le righe abbinate producono lo scostamento per voce e per cantiere; una voce
  sopra soglia è evidenziata; il collegamento è sempre revisionabile.

### M10 — Cruscotto avanzato + registro per cantiere
**Perché**: consolida tutte le entità in una vista di governo e in un "fascicolo"
per cantiere (il registro automatico di §3.8).

- `/dashboard/costs` esteso: costi per categoria fornitore, ore totali e costo
  manodopera, avanzamento SAL, scostamento su computo, alert sopra soglia.
- Endpoint `/cantieri/{id}/registro`: fascicolo consolidato (fatture, DDT, ore, SAL,
  scostamento) — il registro che si aggiorna da solo a ogni documento.
- UI admin: Cruscotto più ricco + pagina dettaglio Cantiere. L'Operatore beneficia
  automaticamente delle nuove viste in "Chiedi" (lo schema viste è auto-scoperto).
- **AC**: il registro di un cantiere mostra tutte le entità collegate con i totali;
  il cruscotto riflette ore, avanzamento e scostamento.

### M11 — Report mensili Excel (openpyxl) — *ancora della Fase 2*
**Perché**: "il cliente continua a vivere in Excel senza doverlo abbandonare" (§3.8).
Report mensili standard come `.xlsx` generati **deterministicamente dalle viste**.

- Dipendenza **openpyxl** (approvata). `backend/app/core/report.py`: costruisce un
  workbook con fogli *Riepilogo, Fatture, DDT, Ore, SAL, Scostamento computo*,
  intestazioni, formati numerici/euro, totali. Nessun LLM: pura proiezione delle viste.
- Endpoint `GET /reports/mensile.xlsx?cantiere=&anno=&mese=` (admin) → file scaricabile.
- UI admin: pulsanti di download (per cantiere, per mese).
- **AC**: il test genera l'xlsx e **lo rilegge con openpyxl** verificando fogli e
  totali chiave; download funzionante dalla UI.

### M12 — Dataset builder (fine-tuning) + pagina Skills & Tools
**Perché**: apre F4. "Ogni tool call è un potenziale esempio di training" (ADR-5) e la
UI deve mostrare registry e candidati al consolidamento (§3.6 / pagina §4 mai costruita).
Nessun Toolsmith automatico, nessun fine-tuning reale (restano non-goal): solo la
**raccolta** e i **contatori**, come da §3.7/§3.6.

- **Dataset builder**: marca `validated_by_user` sulle tool call il cui run ha prodotto
  un'entità poi validata; endpoint `GET /dataset/finetuning.jsonl` che filtra le tool
  call validate nel formato per FunctionGemma. Backfill a partire dai run già validati.
- **Pagina Skills & Tools** (admin): registry dei tool nativi con conteggio d'uso dai
  trace, ciclo di vita (`esplorativa|consolidata`), e i candidati al consolidamento
  (fingerprint query, già calcolati). Chiude l'elenco pagine di §4.
- **Tier T3**: wiring documentato di escalation T3→T1 nel gateway (bassa confidence /
  errore), senza attivare un modello locale.
- **AC**: il builder produce esempi solo dai run validati; la pagina mostra tool,
  contatori e candidati; i test coprono il filtro di validazione.

## 3. Rischi e mitigazioni di Fase 2

| Rischio | Mitigazione |
|---|---|
| Scope creep per milestone | Ogni milestone è additivo e chiude con test verdi + commit; l'infrastruttura riusabile (fixtures/fake generici) è front-loaded in M7. |
| Estrazione multi-entità nel fake LLM | Un unico fake generico legge i documenti sintetici (layout deterministico che generiamo noi) e instrada per marker di skill, come già fa il fake fatture. |
| Rottura dello scenario ritenuta (M5) | Test di regressione dedicato eseguito a ogni milestone; il classificatore ha fallback a `carica-fattura`. |
| Collegamento voci troppo ambizioso (M9) | `collega` è un servizio a sé, revisionabile, che non scrive mai `validato`; il computo può essere seminato senza estrazione. |
| Excel e formati locali (M11) | Generazione deterministica dalle viste; test che rilegge l'xlsx (nessun confronto visivo fragile). |

## 4. Non-goal della Fase 2 (restano fuori)

Integrazioni M365/Graph (watcher SharePoint, Planner, ingest Outlook) — F3, richiedono
servizi esterni. Toolsmith **automatico** e fine-tuning reale di FunctionGemma — F4, qui
si raccoglie solo il dataset e si contano i candidati. Redis, multi-tenant, i18n,
notifiche push. Il tier T3 si *predispone* ma non si attiva (nessun modello locale).
