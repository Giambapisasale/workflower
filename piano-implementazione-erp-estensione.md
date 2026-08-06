# Workflower — Piano di implementazione: Estensione dati ERP (M30–M36)

> **Contesto**: il track Integrazione ERP (M22–M29) è completo: `fattura`/`ddt` validati
> diventano Purchase Invoice/Receipt, con read-back dello stato di pagamento, osservabilità
> e re-sync (`docs/erp-integrazione.md`). L'analisi `analisi-estensione-dati-erp.md` ha
> censito **cosa ancora non passa** e lo ha ordinato in tre fasce. Questo piano le traduce
> in milestone eseguibili: **fascia A** (M30–M31), **fascia B** (M32–M35), **fascia C
> nella parte decisa** (M36: Budget solo "Warn" opt-in + read-back scadenziario;
> il ciclo attivo C2 resta un non-goal, come da analisi).
>
> Valgono tutte le regole di `CLAUDE.md` e l'invariante del track ERP: l'ERP è un sistema
> esterno a valle, la sincronizzazione è un effetto della validazione umana (o un'azione
> esplicita dell'ufficio), best-effort, idempotente, tracciata nel ledger; un fallimento
> apre una issue e non blocca mai la validazione. `runtime.py`/`gateway.py`/`dal.py`
> invariati (nessun nuovo punto-dato richiesto: `Meta.erp_id`/`erp_synced` esistono già).
> **Pytest verde a ogni milestone; la regressione "ritenuta d'acconto" (M5) non si rompe
> mai. Ogni milestone termina con un commit dedicato.**
>
> **Numerazione**: il track ERP arriva a M29 → questo track parte da **M30**.

---

## 0. Obiettivo del track

Portare a valle **tutto il dato aziendale che compete all'ERP**: anagrafiche complete
(fornitori con indirizzo/contatti, cantieri come Project, materiali a listino, mezzi come
cespiti con ammortamento, dipendenti), documenti più ricchi (PDF originale allegato,
scadenza di pagamento, ore dei rapportini, avanzamento dei SAL) e un read-back più utile
(data di pagamento, scadenziario) — senza spostare il confine: il cost-control gestionale
(scostamenti per voce, TCO, costo manodopera) resta di Workflower.

## 1. Punti di aggancio verificati (dal codice, non dal desiderio)

- `api/review.py::valida()` chiama già `applica_sincronizzazione(dal, aggiornata, erp)`:
  per sincronizzare `rapportino` e `sal` **basta estendere `TIPI_SINCRONIZZABILI`** —
  `TIPI_REVISIONABILI` li include già. Zero modifiche a review.py.
- `meta.origine` porta il percorso del blob originale relativo a `data/`: l'allegato (A1)
  non ha bisogno dell'entità `documento`.
- `Meta.erp_id`/`erp_synced` esistono per *ogni* envelope: le anagrafiche caricate dal
  batch possono portare il backref senza toccare il model layer.
- Il fake (`tests/fake_erp.py::ErpServerFinto`) è **severo** (417 sui campi che ERPNext
  pretende): ogni nuovo DocType entra con i suoi campi obbligatori nel finto, così i
  mapping incompleti falliscono nei test e non contro l'istanza reale (lezione M22–M28,
  confermata dalla memoria "il finto deve rifiutare come il reale").
- Il fake oggi gestisce solo GET/POST su `/api/resource/...`: servono **PUT** (M31/M36),
  filtri su tabelle figlie a 4 elementi (M31: Payment Entry Reference) e
  `/api/method/frappe.client.attach_file` (M30).

## 2. Milestone

### M30 — Fascia A "documenti più ricchi": Project, fornitore completo, PDF allegato
**Perché**: ciò che già passa, passa magro; il valore più alto al costo più basso è
completare i record esistenti (A1+A2+A3 dell'analisi).

- **A2** Translator puro `cantiere_a_project` (nome→`project_name`, date→
  `expected_start_date`/`expected_end_date`, `budget`→`estimated_costing`, cost center
  collegato); resolver `_risolvi_project` (upsert per `project_name`); `project` su
  testata+righe della Purchase Invoice e righe della Purchase Receipt.
- **A3** Translator `fornitore_a_address` / `fornitore_a_contact` (paese di default
  `Italy`, override `ERP_PAESE`); `categoria`→Supplier Group (upsert del gruppo);
  creati insieme al Supplier nuovo; l'arricchimento degli esistenti arriva col batch M31.
- **A1** `ErpClient.chiama_metodo` (POST `/api/method/...`); dopo la creazione del
  documento a valle, upload del blob di `meta.origine` via `frappe.client.attach_file`
  (base64, JSON puro: nessun multipart). Best-effort *dentro* la sync: un allegato
  fallito logga un warning ma il documento resta sincronizzato (l'allegato è corredo,
  non contabilità). Documenti senza blob (seed) → nessun tentativo.
- Fake esteso: naming per Project/Address/Contact/Supplier Group, endpoint
  `attach_file` → DocType `File`; severità: `Project.project_name`,
  `Address.address_line1/city/country`.
- **AC**: e2e con ERP finto — la fattura validata produce Project con date/budget,
  `project` su testata e righe, Supplier nuovo con Address+Contact+gruppo, File allegato
  alla PI; fallimento del solo allegato non fa fallire la sync; fattura senza blob non
  chiama `attach_file`. Test tabellari sui nuovi translator. Suite verde.

### M31 — Fascia A "operatività": data di pagamento + carica-anagrafiche
**Perché**: chiudere i due buchi operativi — `pagamento.data` dichiarato e mai riempito,
e le anagrafiche che nascono a valle solo se citate da un documento (A4+A5).

- **A4** `rileggi_pagamenti` legge anche i **Payment Entry** (filtro su tabella figlia
  `Payment Entry Reference.reference_name`, `docstatus=1`) e valorizza `pagamento.data`
  con l'ultima `posting_date`; una chiamata in più solo per le fatture non `non_pagato`.
- **A5** Facade `carica_anagrafiche(dal, erp)` guidata da un **registro estendibile**
  (`fornitore`, `cantiere` ora; `materiale`/`mezzo`/`dipendente`/`lavorazione` nelle
  milestone successive): upsert per chiave naturale, arricchimento degli esistenti
  (Address/Contact mancanti; `supplier_group` via PUT quando la categoria c'è), backref
  `meta.erp_id` sull'anagrafica, riga di ledger per esito. Endpoint admin
  `POST /api/erp/carica-anagrafiche` + pulsante nel pannello `Admin → Contabilità`
  («Carica le anagrafiche in contabilità»), lessico dell'ufficio.
- `ErpClient.aggiorna_documento` (PUT); fake: PUT + filtri a 4 elementi + helper
  `registra_pagamento`.
- **AC**: e2e — dopo `registra_pagamento` sul finto, il read-back riempie
  `pagamento.data`; il batch porta a valle tutti i fornitori (8) e cantieri (3) del seed
  con backref e ledger; il secondo giro non crea doppioni; con ERP spento l'endpoint
  risponde `erp_non_configurato`. Pulsante visibile solo con integrazione accesa.
  Suite verde.

### M32 — B1: la scadenza di pagamento entra in fattura (e nello scadenziario ERP)
**Perché**: il confine assegna all'ERP lo scadenziario fornitori, ma nessuno gli dà la
scadenza: `due_date` = data fattura, scadenziario finto. È il fix "estendere = dati".

- Schema `fattura`: campo `scadenza_pagamento` (date, nullable, **non** required — come
  `destinatario`: le fatture registrate prima restano valide) in
  `backend/app/seed_assets/schemas/` **e** `data/schemas/` (il repo dati non si aggiorna
  da solo).
- Skill di estrazione `carica-fattura` (seed **e** `data/workflows/`): istruzione per
  leggere la scadenza (anche "30 gg d.f." → data), null se assente.
- Translator: `due_date` sulla Purchase Invoice quando `scadenza_pagamento` ≥ data
  fattura (difensivo: una scadenza precedente alla data è un errore di lettura, si omette).
- Vista `v_fatture` (seed e `data/config/views.sql`): colonna `scadenza_pagamento`.
- **AC**: test tabellari (con/senza scadenza; scadenza incoerente ignorata); e2e — bozza
  con scadenza validata → PI con `due_date`; la regressione ritenuta resta verde;
  `test_views` aggiornato. Suite verde.

### M33 — B3: mezzi propri → Asset (ammortamento), manutenzioni → Asset Repair
**Perché**: il registro cespiti è materia fiscale = ERP; i campi (`valore_acquisto`,
`vita_utile_anni`, `anno`) esistono già e non li legge nessuno a valle. Il TCO
gestionale resta di WF (`v_mezzi_tco`).

- Config: `ERP_ASSET_ITEM` (articolo cespite generico) e `ERP_ASSET_LOCATION`;
  `scripts/erp_dev_setup.py` esteso e idempotente: Location, Item cespite
  (`is_fixed_asset=1`), Asset Category con i conti standard, stampa delle nuove env.
- Translator `mezzo_a_asset`: solo `proprieta="proprio"` **con** `valore_acquisto`
  (altrimenti "saltato" con motivo parlante, mai un errore); `is_existing_asset=1`,
  ammortamento a quote costanti quando c'è `vita_utile_anni`. `manutenzione_a_asset_repair`:
  documentale (`capitalize_repair_cost=0` — il costo vero arriva già dalla fattura
  dell'officina: niente doppio costo), `repair_cost`, stato Completed.
- Batch M31 esteso: `mezzo` (upsert per `asset_name`) e `manutenzione` (dopo i mezzi;
  backref su entrambi). Senza le env → salto con messaggio che dice cosa configurare
  (pattern `ERP_ITEM_DDT`).
- Fake: severità `Asset.item_code/gross_purchase_amount`, `Asset Repair.asset/failure_date`.
- **AC**: mezzo proprio → Asset con piano d'ammortamento nel payload; noleggio →
  saltato con motivo; manutenzione → Asset Repair agganciato all'Asset; idempotenza;
  env mancanti → messaggio azionabile. Suite verde.

### M34 — B2: materiali → Item con listino
**Perché**: il listino interno è un'anagrafica Item già pronta; a valle abilita analisi
d'acquisto e prepara le righe codificate (che restano fuori scope finché l'estrazione
non collega riga→materiale).

- Config: `ERP_ITEM_GROUP` (default `All Item Groups`). Translator `materiale_a_item`
  (`codice`→`item_code`, fallback all'id `MAT-…`; `is_stock_item=0`); UOM upsert per
  nome quando presente; **Item Price** su "Standard Buying" quando c'è
  `prezzo_unitario` (aggiornato via PUT se cambia); **Item Supplier** quando c'è il
  fornitore abituale (risolto/creato prima).
- Batch esteso: `materiale` dopo i fornitori.
- **AC**: batch → Item + Item Price + Item Supplier per i materiali del seed;
  idempotente al secondo giro (prezzo aggiornato, non duplicato); materiale senza
  codice usa l'id entità. Suite verde.

### M35 — B4: dipendenti → Employee, lavorazioni → Activity Type, rapportini → Timesheet
**Perché**: portare le ore per cantiere accanto ai costi d'acquisto nel Project ERP.
Analitico, non contabile: il Timesheet non genera scritture (niente doppia verità).

- Translator `dipendente_a_employee` (Employee è nel core v15, HRMS non serve): i campi
  che ERPNext pretende e WF non ha (genere, date) entrano come **valori di cortesia
  espliciti e documentati** in `docs/erp-integrazione.md`, mai inventati silenziosamente.
  `lavorazione_a_activity_type`. `rapportino_a_timesheets`: **un Timesheet per
  dipendente risolto** (time_logs con data+ore, `activity_type` dalla lavorazione,
  `project` dal cantiere); le righe senza `dipendente_id` (terzi/squadre) **si contano
  e si dichiarano**, non si inventano.
- `TIPI_SINCRONIZZABILI` += `rapportino` (l'aggancio in `valida()` c'è già):
  `meta.erp_id` = nomi Timesheet uniti; rapportino senza righe risolte → "saltato" con
  motivo nel ledger (ricomparirà tra i "rimasti indietro": è un invito a collegare il
  dipendente, non rumore). Batch esteso: `lavorazione`, `dipendente`.
- Fake: severità Employee (`first_name/gender/date_of_birth/date_of_joining/company`),
  Timesheet (`time_logs.from_time/hours`).
- **AC**: rapportino validato con 2 dipendenti risolti → 2 Timesheet con ore giuste e
  righe saltate contate; rapportino tutto-terzi → saltato tracciato; idempotenza;
  test tabellari. Suite verde.

### M36 — B5 + fascia C decisa: avanzamento SAL, Budget "Warn", scadenziario; docs
**Perché**: chiudere il quadro con l'avanzamento sul Project, l'unico pezzo di fascia C
senza controindicazioni (Budget solo "Warn", opt-in) e il read-back dello scadenziario.
**C2 (ciclo attivo) resta fuori**, come da analisi.

- **B5** `TIPI_SINCRONIZZABILI` += `sal`: alla validazione, PUT sul Project del cantiere
  (`percent_complete`, metodo Manual); SAL senza cantiere → errore parlante (issue).
- **C1** opt-in `ERP_BUDGET_WARN=1`: nel batch cantieri, upsert **Budget** annuale sul
  Cost Center (conto di costo di default, anno da `data_inizio`,
  `action_if_annual_budget_exceeded="Warn"` — mai "Stop": una PI bloccata dal budget
  sarebbe una politica gestionale trapiantata a valle).
- **C3** Schema `pagamento` + campi `scadenza`/`residuo` (nullable, seed e data);
  read-back li riempie da `due_date`/`outstanding_amount` della PI; vista `v_pagamenti`
  aggiornata.
- Docs: `docs/erp-integrazione.md` (nuove sezioni: anagrafiche, allegati, cespiti,
  manodopera, valori di cortesia, nuove env), `deploy.env.example` esteso; il test
  "SAL non sincronizzabile" viene sostituito da un equivalente su un tipo davvero
  fuori ciclo.
- **AC**: SAL validato → `percent_complete` aggiornato sul Project; con
  `ERP_BUDGET_WARN` il batch crea il Budget (senza, no); read-back riempie
  scadenza/residuo; docs ed env example allineati. Suite completa verde.

## 3. Rischi e mitigazioni (specifici del track)

| Rischio | Mitigazione |
|---|---|
| Doppio costo manutenzioni (Asset Repair + fattura officina) | Asset Repair sempre documentale (`capitalize_repair_cost=0`), niente scritture |
| Doppia verità sul lavoro (Timesheet vs viste WF) | Timesheet analitico, mai payroll; tariffe gestionali restano in WF |
| Budget che blocca le PI | Solo "Warn", opt-in via env; default spento |
| Duplicati Address/Contact sugli arricchimenti | Upsert per Dynamic Link al Supplier + tipo, non per nome |
| Employee/Asset pretendono campi che WF non estrae | Valori di cortesia espliciti nel translator + documentati; il fake li pretende come il reale |
| Righe rapportino senza `dipendente_id` | Si sincronizzano solo le risolte; le saltate si contano nel ledger (mai zero silenzioso) |
| Più chiamate REST alla validazione (project, allegato…) | Best-effort, timeout corto invariato; l'allegato fallito non tocca l'esito della sync |
| Il fake troppo gentile sui nuovi DocType | Ogni DocType nuovo entra con i suoi obbligatori nel finto (417), stessa disciplina M22–M28 |
| Schemi/skill del repo dati vivo non aggiornati | Ogni modifica tocca sia `seed_assets` sia `data/` (memoria: "il repo dati non si aggiorna da solo") |

## 4. Non-goal del track

Il **ciclo attivo** (C2: Customer, Sales Invoice dal SAL, SdI) resta fuori, come da
analisi; nessuna scrittura ERP→WF oltre i read-back in sola lettura; nessun custom
field/DocType in ERPNext; le righe codificate a listino (riga→`materiale_id`) aspettano
l'estensione dell'estrazione; nessuna modifica a `runtime.py`/`gateway.py`/`dal.py`.

## 5. File toccati (rappresentativi)

**Backend** — `core/erp.py` (translator/facade/read-back/batch), `api/erp.py`
(carica-anagrafiche), `tests/fake_erp.py` (PUT, filtri figli, attach_file, severità),
`tests/test_erp_*.py` (nuovi casi), `seed_assets/schemas/{fattura,pagamento}.schema.json`,
`seed_assets/config/views.sql`, `seed_assets/workflows/carica-fattura/skills/*.md`.
**Dati** — `data/schemas/{fattura,pagamento}.schema.json`, `data/config/views.sql`,
`data/workflows/carica-fattura/skills/*.md`.
**Frontend** — `admin/Erp.tsx`, `admin/api.ts` (tipi onesti: i nullable dichiarati tali).
**Script/deploy** — `scripts/erp_dev_setup.py`, `deploy.env.example`,
`docs/erp-integrazione.md`.

## 6. Verifica end-to-end

`make test` (o `pytest backend/tests`) verde a ogni milestone, inclusi
`test_improver_e2e.py::test_scenario_ritenuta` e i test M22–M28 esistenti;
`make test-erp` come giro rapido; smoke opzionale contro l'istanza reale
(`make erp-smoke`) per i lotti con master data nuovo (M33/M34). Nessuna CI nel repo:
verifica manuale per milestone + commit dedicato, come nei track precedenti.
