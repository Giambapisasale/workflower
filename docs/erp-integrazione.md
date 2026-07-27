# Integrazione ERP (ERPNext) — guida operativa

Workflower riflette i documenti del **ciclo passivo** già validati in **ERPNext**, che
fa da *system-of-record contabile a valle*. Il flusso è **mono-direzionale** WF→ERP, con
un solo ritorno in lettura (stato di pagamento). Vedi `analisi-integrazione-erp.md` per il
razionale e `piano-implementazione-erp.md` per le milestone (M22–M29).

Stato: **M22–M28 implementati** (client, translator, sync alla validazione, DDT, read-back
pagamenti, osservabilità e re-sync). Restano il deploy affiancato e l'hardening (M29).

## Quickstart (docker → collega → test)

```bash
# 1) AVVIA ERPNext con Docker (prima volta: scarica immagini + crea il sito, qualche minuto)
make erp-up
#    → http://localhost:8080/app   utente: Administrator   password: admin
#    (la scrivania è /app; la radice / è il portale fornitori e nega i documenti con 403)

# 2) PREPARA e COLLEGA: crea company, conti, articolo DDT e API key; stampa le ERP_*
make erp-dev-setup
#    stampa DUE blocchi, servono entrambi:
#      1) righe ERP_*=... da incollare nel file .env  → le legge l'app in container
#      2) righe export ERP_*=... da incollare in shell → le usano erp-smoke e pytest
#    Senza il blocco 1 nel .env l'integrazione parte SPENTA, senza dirlo.

# 3) VERIFICA il collegamento (nessun codice) e i test
make erp-smoke                 # smoke contro l'ERPNext reale (connettività, Supplier, Cost Center)
make erp-smoke ARGS=--full     # anche Purchase Invoice con ritenuta
make test-erp                  # test automatici dell'integrazione (trasporto finto, veloci)
```

`make erp-dev-setup` è idempotente e serve **solo in sviluppo**: sostituisce il setup wizard
e il *Generate Keys* dalla UI. In produzione si segue la procedura ERPNext con un utente API
dedicato (*My Settings → API Access → Generate Keys*).

Se l'app gira **in container** e ERPNext è sullo stesso host, `ERP_BASE_URL` deve puntare a
`host.docker.internal:8080`: dentro al container `localhost` è il container stesso. Le `ERP_*`
del `.env` arrivano già al servizio `app` di `docker-compose.yml`.

Se le `ERP_*` non sono impostate, l'integrazione è **spenta** e Workflower funziona come
prima. Passi dettagliati e alternative (file `pwd.yml` ufficiale) in `docs/erp-poc.md`;
mappa casi d'uso → test e triage in `docs/erp-test-plan.md`.

## Principio

- L'ERP è un **sistema esterno**: Workflower non guadagna un DB, non importa codice ERPNext
  in-process, e **non espone la scrittura ERP al modello** (ADR-4). La sincronizzazione è un
  effetto della **validazione umana**, best-effort: un fallimento apre una issue e **non**
  fa cadere la validazione.
- Confine: WF possiede estrazione, validazione e cost-control; ERPNext possiede la parte
  fiscale (Purchase Invoice/Receipt, partita doppia, IVA, pagamenti).

## Configurazione (da ambiente, mai hard-coded)

| Variabile | Obbligatoria | Uso |
|---|---|---|
| `ERP_BASE_URL` | sì | URL dell'istanza ERPNext (es. `https://erp.miosito.it`) |
| `ERP_API_KEY` / `ERP_API_SECRET` | sì | token API (`Authorization: token key:secret`) |
| `ERP_COMPANY` | per Cost Center / PI reali | azienda ERPNext su cui imputare |
| `ERP_CONTO_RITENUTA` | consigliata | account_head della riga ritenuta d'acconto (in detrazione) |
| `ERP_CONTO_IVA` | opzionale | account_head della riga IVA (in aggiunta) |
| `ERP_ITEM_DDT` | per i DDT | codice articolo delle righe di Purchase Receipt: ERPNext ne pretende uno esistente. Usare un articolo generico **non di magazzino** (`is_stock_item=0`) |
| `ERP_SUPPLIER_GROUP` | opzionale | gruppo Supplier (default `All Supplier Groups`) |
| `ERP_CONTO_COSTO` | opzionale | `expense_account` delle righe fattura. Se assente si deriva da `Company.default_expense_account` |
| `ERP_PARENT_COST_CENTER` | opzionale | padre dei Cost Center dei cantieri. Se assente si deriva dalla radice della Company |

Le ultime due sono **override**: ERPNext pretende sia il padre del Cost Center sia il conto
di costo sulle righe (le righe non portano `item_code`), ma entrambi sono derivabili dalla
Company, quindi normalmente non vanno configurati. `ERP_ITEM_DDT` invece **serve** per
sincronizzare i DDT: senza, la sincronizzazione del singolo DDT si ferma con un messaggio
che dice cosa impostare (la validazione del documento regge, come per ogni errore ERP).

**Se le tre `ERP_*` obbligatorie non sono tutte presenti, l'integrazione è spenta**
(`erp_attivo()` falso): la sincronizzazione è un no-op e Workflower funziona come prima.

Le credenziali si generano in ERPNext: *User (Administrator) → Settings → API Access →
Generate Keys*. Per alzare un'istanza di sviluppo vedi `docs/erp-poc.md` e
`docker-compose.erpnext.yml`.

## Cosa succede alla validazione

Quando l'ufficio valida una `fattura` o un `ddt` (`POST /api/review/{id}/validate`), oltre
al golden set parte — best-effort — la sincronizzazione ERP:

1. **Fornitore** → Supplier (upsert per partita IVA).
2. **Cantiere** → Cost Center (upsert; richiede `ERP_COMPANY`), imputato sulle righe.
3. Documento → **Purchase Invoice** (fattura, con ritenuta in detrazione e IVA) o
   **Purchase Receipt** (DDT, merce senza importi).
4. In caso di **successo**: backref `meta.erp_id`/`meta.erp_synced` sull'envelope + riga `ok`
   nel ledger `data/dataset/erp_sync.jsonl`.
5. In caso di **errore** (ERP giù, mapping rifiutato…): **issue automatica** ("ci pensa
   l'ufficio") + riga `errore` nel ledger. La validazione **resta valida**.

La sincronizzazione è **idempotente**: un documento con `meta.erp_id` già valorizzato non
viene reinviato.

I documenti arrivati si guardano nella **scrivania** di ERPNext: `/app/purchase-invoice`
(fatture), `/app/purchase-receipt` (DDT), `/app/cost-center` (cantieri). Non dal portale
alla radice del sito: quello è la vetrina per fornitori e clienti e nega i documenti.

## Scartare un documento già arrivato a valle

Se l'ufficio **scarta** un inserimento (Revisione → *Scarta*) che è già stato
sincronizzato, Workflower **si ferma**: prima va sistemato in ERPNext, poi si scarta
qui. Altrimenti resterebbero due verità in disaccordo — Workflower senza la fattura,
ERPNext con la fattura nei conti.

La verifica è una **lettura** del `docstatus` del documento a valle, e l'istruzione
cambia con il suo stato, perché in Frappe le due cose sono diverse:

| Stato a valle | `docstatus` | Cosa fare in ERPNext | Scarto |
|---|---|---|---|
| Bozza (è come nasce da WF) | 0 | **eliminala** — una bozza non si annulla | bloccato |
| Confermata (è nei conti) | 1 | **annullala** (*Cancel*) | bloccato |
| Annullata | 2 | niente | permesso |
| Non c'è più (404) | — | niente | permesso |
| ERP irraggiungibile o spento | — | riprovare quando risponde | bloccato |

Workflower **non scrive annullamenti** nell'ERP: la scrittura verso valle resta un
effetto della sola validazione (ADR-4). Bloccare è la scelta prudente; l'alternativa —
propagare il `cancel` — è stata scartata di proposito.

## Endpoint admin

| Metodo / rotta | Cosa fa |
|---|---|
| `GET /api/erp/stato` | Contatori per tipo (validate / sincronizzate / da sincronizzare), elenco dei documenti da sincronizzare, ultimi tentativi dal ledger |
| `POST /api/erp/risincronizza` | Ri-sincronizza tutti i documenti validati rimasti senza backref; si ferma dopo N fallimenti consecutivi (ERP giù) |
| `POST /api/erp/risincronizza/{entity_id}` | Ri-sincronizza un singolo documento (pulsante "riprova") |
| `POST /api/erp/rileggi-pagamenti` | Rilegge lo stato di pagamento delle fatture sincronizzate → entità `pagamento` |

Tutti riservati all'ufficio (admin).

## Resilienza

- **Timeout corto** sul client HTTP: l'ERP a valle non rallenta la validazione.
- **Best-effort per documento**: un errore non propaga (issue + ledger), non blocca WF.
- **Early-abort del re-sync**: il batch si ferma dopo `MAX_ERRORI_CONSECUTIVI` (default 5)
  fallimenti di fila, così un ERP irraggiungibile non fa martellare centinaia di documenti.
- **Recupero**: quando l'ERP torna su, `POST /api/erp/risincronizza` recupera gli arretrati.

## Read-back pagamenti

L'unico flusso ERP→WF, in **sola lettura**. `POST /api/erp/rileggi-pagamenti` interroga la
Purchase Invoice a valle di ogni fattura sincronizzata, ne deriva lo stato
(`pagato`/`parziale`/`non_pagato`) e l'importo, e crea/aggiorna un'entità **`pagamento`**
(idempotente per `fattura_id`), visibile nella vista `v_pagamenti`. `pagamento` è **puro
dato** (schema + riga `ENTITY_TYPES` + vista, nessun workflow).

## Ledger

`data/dataset/erp_sync.jsonl` — log append-only di ogni tentativo (`ts`, `entity_id`,
`esito`, `erp_id`, `errore`, `run_id`), committato in git come ogni mutazione. È l'audit
trail e l'input dell'osservabilità/re-sync.

## Pannello admin "Contabilità"

`Admin → Contabilità` (`/admin/erp`) è la faccia visibile di tutto questo, senza curl:

- **contatori per tipo** (quanti documenti validati sono arrivati a valle);
- **elenco dei rimasti indietro** con un pulsante *Riprova* per documento, e
  *Re-invia gli arretrati* per il recupero in blocco;
- **registro dei tentativi** dal ledger, con il motivo di ogni fallimento;
- *Rileggi i pagamenti* per il read-back.

Con l'integrazione spenta la pagina lo dice e non mostra azioni (resta lo storico).
Il lessico è quello dell'ufficio — "arrivato in contabilità", non "erp_id".

## Note

- Gli esiti di sincronizzazione finiscono anche nel **logbook** (fase `erp`): successo a
  `INFO`, fallimento a `ERROR` con traceback — così sono visibili in `Admin → Log` e
  analizzabili dalla diagnosi automatica, non solo come issue e riga di ledger.
- L'emissione elettronica SdI e il ciclo attivo restano **fuori scope** (vedi non-goal del piano).
