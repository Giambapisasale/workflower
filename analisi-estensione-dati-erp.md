# Analisi: quali altri dati mappare e caricare su ERPNext

> Estensione di `analisi-integrazione-erp.md` (solo analisi, nessun codice). L'integrazione
> M22–M28 è viva e verde: questa analisi censisce **tutto ciò che Workflower possiede e non
> spinge ancora a valle**, valuta per ogni dato il DocType ERPNext candidato, e propone
> priorità e confini. Valgono le scelte già prese: ciclo passivo, ERP a valle,
> mono-direzionale WF→ERP con read-back in sola lettura, `runtime.py`/`gateway.py`/`dal.py`
> invariati.

---

## 1. Stato attuale — cosa passa già

| Workflower | → | ERPNext (DocType) | Note |
|---|---|---|---|
| `fornitore` | → | Supplier | upsert per P.IVA; **solo** `ragione_sociale` + `tax_id` + gruppo di default |
| `cantiere` | → | Cost Center | **solo** il nome, creato al volo alla prima fattura del cantiere |
| `fattura` | → | Purchase Invoice (+ items + taxes) | righe a testo libero, IVA e **ritenuta d'acconto** (M5) |
| `ddt` | → | Purchase Receipt | righe con articolo generico `ERP_ITEM_DDT` |
| stato pagamento | ← | Purchase Invoice (lettura) | entità `pagamento` (`stato`, `importo_pagato`) |

Due osservazioni che guidano il resto dell'analisi:

1. **Ciò che passa, passa magro.** Del `fornitore` arrivano 2 campi su 7; del `cantiere` 1 su 9.
   L'ERP ha i record ma non i dati per *usarli* (pagare un fornitore senza indirizzo,
   leggere un cost center senza date né budget).
2. **Un pezzo del confine dichiarato è scoperto.** `analisi-integrazione-erp.md` §4 assegna
   a ERPNext «pagamenti, tesoreria, **scadenziario fornitori**» — ma Workflower non estrae né
   spinge la **scadenza di pagamento** della fattura: ERPNext mette `due_date = data fattura`
   e lo scadenziario che "possiede" è di fatto vuoto/sbagliato.

## 2. Inventario completo: entità Workflower ↔ DocType ERPNext

Tutte le entità di `ENTITY_TYPES` (17), con il candidato naturale in ERPNext v15 *core*
(nessuna app aggiuntiva: Employee, Timesheet, Asset, Item, Project, Budget sono nel core;
solo payroll/presenze/Vehicle richiederebbero l'app HRMS, qui non necessaria).

| Entità | Dati (demo) | DocType ERPNext candidato | Verdetto |
|---|---|---|---|
| `fornitore` | 8 | Supplier ✅ + **Address, Contact, Supplier Group** | **arricchire** (A) |
| `cantiere` | 3 | Cost Center ✅ + **Project** | **arricchire** (A) |
| `fattura` | ✅ | Purchase Invoice ✅ + **allegato PDF, project, due date** | **arricchire** (A/B) |
| `ddt` | ✅ | Purchase Receipt ✅ + **project** | **arricchire** (A) |
| `pagamento` | ✅ (read-back) | + **data da Payment Entry** | **arricchire** (A) |
| `materiale` | 3 | **Item** (+ Item Price, Item Supplier) | **nuovo** (B) |
| `mezzo` | 3 | **Asset** (+ Asset Category) — solo mezzi *propri* | **nuovo** (B) |
| `manutenzione` | 2 | **Asset Repair** / Asset Maintenance Log | **nuovo** (B, con cautela) |
| `dipendente` | 4 | **Employee** | **nuovo** (B) |
| `lavorazione` | 3 | **Activity Type** | **nuovo** (B, serve al Timesheet) |
| `rapportino` | ✅ | **Timesheet** | **nuovo** (B) |
| `sal` | ✅ | **Project.percent_complete** / Sales Invoice | B (avanzamento) / C (ciclo attivo) |
| `computo` | 2 | **Budget** (per Cost Center/Project) | C (granularità diversa) |
| `scadenza` | 4 | ToDo / Event | **resta in WF** |
| `cronoprogramma` | 1 | Task | **resta in WF** |
| `pozzetto` | 3 | — (nessun DocType naturale) | **resta in WF** |
| `documento` | ✅ | File (allegato) | il **blob** sì, il metadato no |

Legenda fasce: **A** = alto valore/basso rischio, non cambia il confine; **B** = valore
reale ma con prerequisiti (PoC, qualità dati, master data ERP); **C** = cambia il confine
o lo scope, decisione esplicita da prendere prima.

---

## 3. Fascia A — arricchire ciò che già passa (nessun nuovo confine)

### A1. Allegare il PDF originale alla Purchase Invoice / Purchase Receipt
Il valore fiscale più alto al costo più basso. L'entità `documento` collega già blob ed
entità estratta (`entity_id`): dopo la sync, una chiamata a `POST /api/method/upload_file`
di Frappe (`attached_to_doctype`/`attached_to_name` = il `meta.erp_id` appena ottenuto)
mette **il documento originale sul record contabile**. Chi lavora in ERPNext (commercialista,
revisore) vede la pezza d'appoggio senza entrare in Workflower.
- Prerequisiti: nessuno. Rientra nella facciata `sincronizza` come passo best-effort.
- Rischio: dimensione blob (il compose ha `CLIENT_MAX_BODY_SIZE: 50m`, ampio).

### A2. `cantiere` → Project (oltre al Cost Center)
Oggi il cantiere a valle è un centro di costo anonimo. Il DocType **Project** porta ciò che
il Cost Center non può: `expected_start_date`/`expected_end_date` (da `data_inizio`/
`data_fine_prevista`), `estimated_costing` (da `budget`), e — se si valorizza `project`
sulle righe di Purchase Invoice/Receipt — ERPNext **aggrega da solo il costo d'acquisto
per progetto** (`total_purchase_cost`) e offre il cruscotto di progetto nativo.
- Mapping: `nome`→`project_name`, date→date attese, `budget`→`estimated_costing`,
  Cost Center collegato al Project; `project` su testata/righe di PI e PR.
- `committente` resta stringa finché non si decide il ciclo attivo (fascia C: Customer).
- Idempotenza: upsert per `project_name` (come oggi per il Cost Center).

### A3. `fornitore` arricchito → Address + Contact + Supplier Group
I campi già estratti e oggi scartati: `indirizzo`+`comune` → **Address** (DocType separato,
collegato via Dynamic Link), `pec`+`telefono` → **Contact**, `categoria` → **Supplier Group**
(upsert del gruppo, fallback su quello di default). Un Supplier senza indirizzo è un
record a metà per chiunque debba pagarlo o scrivergli.
- Attenzione: upsert non solo alla creazione — se il fornitore esiste già a valle,
  arricchirlo senza duplicare Address/Contact (chiave: link al Supplier + tipo).

### A4. Read-back più ricco: la data di pagamento
Lo schema `pagamento` ha già il campo `data` — **che il read-back non riempie mai**
(`rileggi_pagamenti` deriva stato e importo dalla Purchase Invoice, non legge i Payment
Entry). Interrogare i **Payment Entry** riferiti alla PI dà la data (e il dettaglio) dei
pagamenti: campo già dichiarato, zero modifiche di schema.

### A5. Caricamento iniziale delle anagrafiche (operativo, non nuovo mapping)
Oggi Supplier e Cost Center nascono **al volo**, alla prima fattura che li cita: gli 8
fornitori e i 3 cantieri del repo arrivano a valle solo se e quando compaiono su un
documento. Un'azione admin «Carica le anagrafiche in contabilità» (accanto a *Re-invia gli
arretrati* in `Admin → Contabilità`) fa l'upsert in blocco di fornitori e cantieri — e
domani di materiali/mezzi/dipendenti. Stesso pattern best-effort + ledger del re-sync M28.

---

## 4. Fascia B — nuovi flussi (valore reale, prerequisiti veri)

### B1. La scadenza di pagamento della fattura → `due_date` / Payment Schedule
**Colma il buco del confine (§1.2).** Perché ERPNext possa possedere lo scadenziario
fornitori, la fattura deve portare i termini di pagamento. Oggi `fattura.schema.json`
non li estrae: serve **un campo in più nell'estrazione** (`scadenza_pagamento` o
`termini_pagamento`, nullable come `destinatario` — stessa retro-compatibilità) e il
mapping su `due_date`/`payment_schedule` della Purchase Invoice. Da lì i report nativi
Accounts Payable / Accounts Receivable Aging diventano veri.
- È la dimostrazione del principio «estendere = dati»: schema + prompt skill, non cornice.
- Nota: molte fatture di cantiere riportano "30/60 gg d.f." — il translator può derivare
  la data; se il documento tace, `due_date` resta = data fattura (comportamento attuale).

### B2. `materiale` → Item (+ Item Price + Item Supplier)
Il listino interno (codice, descrizione, UM, prezzo, fornitore abituale) è un'anagrafica
Item già pronta: `codice`→`item_code`, `prezzo_unitario`→Item Price su "Standard Buying",
`fornitore_id`→Item Supplier. Articoli **non di magazzino** (`is_stock_item=0`), coerenti
con la scelta già fatta per `ERP_ITEM_DDT`.
- **Limite onesto**: le righe di fattura/DDT oggi *non* referenziano `materiale` (portano
  `voce_computo_id`/`mezzo_id`, non `materiale_id`). Finché il collegamento riga→materiale
  non esiste nell'estrazione, gli Item a valle sono anagrafica di listino, non righe
  codificate: i DDT continuano a usare l'articolo generico. Il passo dopo — un
  `materiale_id` nullable sulle righe, risolto come oggi si risolve `voce_computo_id` —
  è di nuovo «dati, non codice», ma è un progetto di qualità dell'estrazione, non di sync.

### B3. `mezzo` (di proprietà) → Asset, `manutenzione` → Asset Repair
I campi ci sono già tutti: `valore_acquisto`, `vita_utile_anni`, `anno`, `matricola`/`targa`.
L'**ammortamento è materia fiscale** — per il confine dichiarato spetta all'ERP: Asset con
`is_existing_asset=1` (mezzi già in azienda, senza documento d'acquisto), Asset Category
con i conti di ammortamento, e ERPNext genera il piano e le scritture. La `manutenzione`
(data, tipo, costo, officina, contaore) diventa **Asset Repair**: storico interventi
agganciato al cespite.
- Solo i mezzi `proprieta="proprio"`: il noleggio non è un cespite (il suo costo arriva
  già come fattura del noleggiatore).
- **Rischio doppio costo**: se l'intervento dell'officina arriva *anche* come fattura
  (righe `tipo_costo="manutenzione"`), l'Asset Repair va tenuto **documentale** (non
  capitalizzato, niente scritture GL) o riconciliato — altrimenti il costo entra due volte.
- Prerequisito ERP: Asset Category + conti (estensione di `erp_dev_setup.py`).
- Il **TCO gestionale resta di Workflower** (`v_mezzi_tco`): all'ERP va il registro
  cespiti fiscale, non il costo orario pieno.

### B4. `dipendente` → Employee, `lavorazione` → Activity Type, `rapportino` → Timesheet
Il trittico della manodopera. Employee e Timesheet sono nel **core** ERPNext (l'app HRMS
serve solo per paghe/presenze, fuori scope). Un rapportino validato → un **Timesheet**
(data, dipendente, ore, `activity_type` dalla lavorazione, `project` dal cantiere): il
progetto ERP mostra costo acquisti *e* ore/costo manodopera insieme, senza scritture
contabili (il Timesheet non movimenta la contabilità finché non c'è payroll/billing —
resta analitico, quindi **non** crea doppia verità contabile).
- Prerequisiti di qualità: passa solo la riga con `dipendente_id` risolto — e
  l'esperienza sul campo dice che spesso è null (lavoratori di terzi, squadre); le righe
  non risolte restano solo in WF. La tariffa può viaggiare come Activity Cost per
  dipendente o `costing_rate` sulla riga.
- Prerequisito ERP: Employee pretende qualche campo anagrafico che WF non estrae (es.
  data di assunzione) → valori di cortesia o config; da verificare nel PoC.
- Cautela sul confine: il **costo manodopera gestionale resta di WF**
  (`v_rapportini_righe`); a valle va il *documento* ore per il quadro di progetto.

### B5. `sal` → avanzamento del Project
Leggero e senza contabilità: alla validazione di un SAL, aggiornare
`percent_complete` (metodo "Manual") del Project del cantiere con
`percentuale_avanzamento`. Chiude il cerchio con A2 (il cruscotto di progetto ERP mostra
costi + avanzamento). La parte *contabile* del SAL (fatturare al committente) è fascia C.

---

## 5. Fascia C — cambiano confine o scope (decidere prima, poi mappare)

### C1. `computo`/`cantiere.budget` → Budget ERPNext
ERPNext ha il DocType **Budget** per Cost Center/Project con azioni al superamento
(Warn/Stop) — ma è **per conto contabile**, non per voce di computo: il controllo
scostamenti per voce (`v_scostamento_voci`) non è replicabile lì ed è già il cuore di WF.
Mappabile solo il **budget complessivo** del cantiere sul conto di costo di default:
dà l'allarme contabile nativo al submit delle PI. Sconsigliata l'azione "Stop": una PI
rifiutata dal budget farebbe fallire la sync (issue) per una politica gestionale che
appartiene a WF. *Verdetto: opzionale, solo come "Warn"; il cost control per voce resta WF.*

### C2. Ciclo attivo: `committente` → Customer, `sal` → Sales Invoice
È il non-goal dichiarato del track ERP. Se lo scope cambia, la strada è: `committente`
(oggi stringa su `cantiere`) promosso ad anagrafica o mappato a **Customer**, SAL validato →
**Sales Invoice** sul Project (con ritenuta a garanzia, IVA in split payment/reverse charge
a seconda del committente — materia SdI/fiscale non banale, vedi rischi dell'analisi
originale). *Verdetto: non ora; se ne riparla con l'emissione elettronica.*

### C3. Read-back aggiuntivi (ERP → WF)
Oltre alla data di pagamento (A4): lo **scadenziario** (outstanding + due date per
fornitore) riletto in WF arricchirebbe il cruscotto senza aprire scritture inverse.
Da fare solo come oggi: campi in sola lettura su entità-dato, mai l'ERP che scrive
in `/data` come master.

---

## 6. Cosa NON mappare (e perché)

| Dato | Perché resta in Workflower |
|---|---|
| `pozzetto` | Registro tecnico di cantiere: nessun DocType naturale, nessun valore contabile. È l'esempio vivo di «entità = dati» interno. |
| `cronoprogramma` | Il Task/Gantt ERPNext duplicherebbe la pianificazione → doppia verità sul *tempo* come quella evitata sui *costi*. Il confronto pianificato/consuntivo è cost intelligence WF. |
| `scadenza` (permessi, adempimenti) | ToDo/Event ERPNext non aggiungono nulla: lo scadenzario operativo è UI di WF. Le sole scadenze "di pagamento" passano per la via giusta: la `due_date` della fattura (B1). |
| `documento` (metadato di ingest) | Chi ha caricato, run, esiti: telemetria di WF. A valle va solo il blob come allegato (A1). |
| `issues`, `golden`, `logs`, `traces`, `patches` | Meccanica interna del sistema LLM, non dati aziendali. |
| Campi riga `voce_computo_id`, `mezzo_id`, `tipo_costo` | Confermata la scelta M24: sono le dimensioni del cost control WF; ERPNext non ha una dimensione "mezzo" sulle righe spesa e forzarla (custom field) sposterebbe il confine senza necessità. |

## 7. Dati che *non esistono ancora* e varrebbe estrarre proprio per l'ERP

L'analisi al §2 mappa l'esistente; questi sono i campi assenti che sbloccherebbero il
valore a valle (tutti = schema + prompt, «dati non codice»):

1. **Termini/scadenza di pagamento in fattura** (→ B1) — il più importante.
2. **IBAN / modalità di pagamento del fornitore** — per pagare dall'ERP senza reinserimento.
3. **`materiale_id` sulle righe** di fattura/DDT (→ B2) — righe codificate a listino.
4. **Condizioni di pagamento abituali del fornitore** (es. "60 gg d.f.") → `payment_terms`
   del Supplier, default per le fatture senza scadenza esplicita.

## 8. Priorità consigliata e dipendenze

```
A1 allegato PDF ─────────────────────────────► subito, standalone
A2 cantiere→Project ────► B5 SAL→avanzamento   (B5 dipende da A2)
A3 fornitore arricchito ─────────────────────► subito, standalone
A4 data pagamento (read-back) ───────────────► subito, standalone
A5 carica-anagrafiche admin ─────────────────► subito; ospita B2/B3/B4 anagrafiche
B1 due date fattura ◄── estrazione nuova (schema fattura + skill)
B2 materiale→Item ◄──── (righe codificate richiedono materiale_id: dopo)
B3 mezzo→Asset + manutenzione→Asset Repair ◄── Asset Category in erp_dev_setup
B4 dipendente/lavorazione/rapportino→Timesheet ◄── qualità dipendente_id
C* solo dopo decisione esplicita di scope
```

Un ordine pragmatico in tre lotti: **Lotto 1 = fascia A** (5 interventi, nessun nuovo
confine, nessuna estrazione nuova); **Lotto 2 = B1 + B3** (il buco dello scadenziario e
il registro cespiti: i due più "fiscali", coerenti col mandato dell'ERP); **Lotto 3 =
B2 + B4 + B5** (listino, manodopera, avanzamento: valore analitico, prerequisiti di
qualità dati).

## 9. Come (pattern invariato) e nuove configurazioni

- **Stesso telaio M23–M28**: translator = funzioni pure con test tabellari in
  `core/erp.py`; facciata best-effort; ledger `erp_sync.jsonl`; backref su `meta`;
  issue sugli errori; idempotenza per chiave naturale (P.IVA, `project_name`,
  `item_code`=`materiale.codice`, matricola/targa per gli Asset, `fattura_id`+data per
  i Timesheet).
- **Trigger**: i *documenti* (rapportino, sal) seguono la via esistente — validazione →
  sync (estensione di `TIPI_SINCRONIZZABILI`); le *anagrafiche* (materiale, mezzo,
  dipendente) non hanno una "validazione" → upsert lazy quando citati + azione batch A5.
- **Nuove env prevedibili** (stesso pattern `ERP_*`): `ERP_ITEM_GROUP` (gruppo degli Item
  da listino), `ERP_ASSET_CATEGORY` o i conti cespiti/ammortamento per B3; ogni PoC di
  fascia B estende `erp_dev_setup.py` per restare riproducibile.
- **Per ogni lotto**: PoC go/no-go stile M22 prima del codice (in particolare B3 — piano
  ammortamento — e B4 — campi obbligatori di Employee), `make test` verde, regressione
  ritenuta intatta.

## 10. Rischi specifici di questa estensione

| Rischio | Mitigazione |
|---|---|
| Doppio costo manutenzioni (Asset Repair + fattura officina) | Asset Repair documentale (no GL); riconciliare via `tipo_costo` |
| Doppia verità sul lavoro (Timesheet vs `v_rapportini_righe`) | Timesheet resta analitico (mai payroll); WF unica fonte del costo orario gestionale |
| Budget ERP che blocca le PI (azione Stop) | Solo "Warn"; il controllo scostamenti resta WF |
| Arricchimento anagrafiche che duplica Address/Contact | Upsert per link Supplier + tipo, non solo per nome |
| Employee/Asset pretendono campi che WF non ha | PoC per lotto; valori di cortesia espliciti e documentati, mai inventati silenziosamente |
| Righe rapportino senza `dipendente_id` (frequente) | Sincronizzare solo le righe risolte; contatore "saltate" nel ledger, mai zero silenzioso |
| Più chiamate REST per validazione (PDF, Project, Address…) | Restano best-effort e fuori dal percorso di validazione; timeout corto già in essere |

---

## 11. Riferimenti

- `analisi-integrazione-erp.md` — confine e razionale (questa analisi lo estende, non lo cambia)
- `piano-implementazione-erp.md` (M22–M29) — telaio riusato per ogni nuovo lotto
- `backend/app/core/erp.py` — client, translator, facciata, read-back attuali
- `docs/erp-integrazione.md` — stato operativo M22–M28
- `data/schemas/*.schema.json` — le 17 entità censite al §2
- `scripts/erp_dev_setup.py`, `docker-compose.erpnext.yml` (v15) — ambiente riproducibile
- ERPNext v15 core: Project/Task/Timesheet/Activity Type (modulo projects), Asset/Asset
  Repair (assets), Item/Item Price (stock), Budget (accounts), Employee (setup — HRMS non
  richiesta), Address/Contact (frappe), `upload_file` (allegati)
