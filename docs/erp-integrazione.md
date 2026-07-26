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
docker compose -f docker-compose.erpnext.yml up -d
docker compose -f docker-compose.erpnext.yml logs -f create-site   # attendi che finisca
#    → http://localhost:8080   utente: Administrator   password: admin

# 2) COLLEGA Workflower: in ERPNext genera le API key (My Settings → API Access → Generate Keys)
export ERP_BASE_URL=http://localhost:8080
export ERP_API_KEY=<api_key>
export ERP_API_SECRET=<api_secret>
export ERP_COMPANY="La Tua Azienda"        # per Cost Center / Purchase Invoice
export ERP_CONTO_RITENUTA="Ritenute - X"   # account_head della ritenuta

# 3) VERIFICA il collegamento (nessun codice) e i test
make erp-smoke                 # smoke contro l'ERPNext reale (connettività, Supplier, Cost Center)
make erp-smoke ARGS=--full     # anche Purchase Invoice con ritenuta
make test-erp                  # test automatici dell'integrazione (trasporto finto, veloci)
```

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
| `ERP_SUPPLIER_GROUP` | opzionale | gruppo Supplier (default `All Supplier Groups`) |

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

## Note

- Il pannello admin "Sincronizzazioni ERP" (UI React) consuma `GET /api/erp/stato` e i due
  `risincronizza`: è un follow-up di UI (nessuna logica nuova lato backend).
- L'emissione elettronica SdI e il ciclo attivo restano **fuori scope** (vedi non-goal del piano).
