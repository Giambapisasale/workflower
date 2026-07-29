# PoC integrazione ERP (ERPNext) — runbook M22

Questo documento è il **cancello go/no-go** del track "Integrazione ERP"
(`piano-implementazione-erp.md`, M22). Obiettivo: **provare a mano**, prima di
scrivere l'adattatore in Workflower, che il mapping regge — in particolare la
`fattura` con **ritenuta d'acconto** → *Purchase Invoice* con *Tax Withholding*, e
l'imputazione del costo al **cantiere** come *Cost Center*.

> Stato: **eseguito** contro un'istanza reale (ERPNext v15.118.1 / Frappe v15.116.0
> in Docker) — esito **GO**, vedi §6. I tre prerequisiti che ERPNext pretende e che
> il PoC ha fatto emergere sono in §3bis.

## 0. Contesto e confine

- Workflower resta il *system-of-record dei documenti* (estrazione + validazione umana).
- ERPNext è il *system-of-record contabile* a valle, alimentato **solo** dai documenti validati.
- Flusso **mono-direzionale** WF→ERP; l'unico ritorno è la lettura dello stato di pagamento (M27).
- ERPNext è una **dipendenza esterna**: gira in un suo deploy, Workflower lo raggiunge via HTTP.

## 1. Avviare ERPNext con Docker

Requisiti: Docker + Docker Compose. La prima volta scarica ~2 GB di immagini e crea il
sito: metti in conto qualche minuto.

**Opzione A — compose incluso in questo repo** (consigliata: un solo comando):

```bash
# dalla radice del repo
docker compose -f docker-compose.erpnext.yml up -d

# segui la creazione del sito: termina quando il container create-site esce con codice 0
docker compose -f docker-compose.erpnext.yml logs -f create-site
docker compose -f docker-compose.erpnext.yml ps          # create-site → "Exited (0)" = pronto
```

Poi apri **http://localhost:8080/app** → utente **`Administrator`**, password **`admin`**.

> **Usa `/app`, non la radice.** ERPNext ha due facce sulla stessa porta: la *scrivania*
> (`/app`, l'gestionale) e il *portale* pubblico (`/`, il sito per fornitori e clienti).
> Il portale mostra solo i documenti dell'utente collegato a quel fornitore: aprire una
> fattura da lì — `/purchase-invoices/ACC-PINV-…` — risponde **403 "Non Consentito"**
> anche all'Administrator. Le fatture sincronizzate si guardano in
> `/app/purchase-invoice`.

Comandi utili:

```bash
docker compose -f docker-compose.erpnext.yml ps          # stato dei servizi
docker compose -f docker-compose.erpnext.yml down        # ferma (mantiene i dati)
docker compose -f docker-compose.erpnext.yml down -v     # AZZERA tutto (volumi inclusi)
ERPNEXT_VERSION=v15 docker compose -f docker-compose.erpnext.yml up -d   # pinna la versione
```

**Opzione B — file ufficiale `pwd.yml`** (fonte di verità di frappe_docker):

```bash
curl -O https://raw.githubusercontent.com/frappe/frappe_docker/main/pwd.yml
docker compose -f pwd.yml up -d
```

Il compose incluso ricalca `pwd.yml` (stessi servizi: db MariaDB, redis, configurator,
create-site, backend, frontend, websocket, worker, scheduler). In **produzione** segui la
[guida ufficiale frappe_docker](https://github.com/frappe/frappe_docker).

## 2. Credenziali API (token key:secret)

Servono a Workflower per parlare con ERPNext. In ERPNext:
**icona utente (in alto a destra) → My Settings → sezione *API Access* → Generate Keys**
(oppure *Settings → API Access* sull'utente Administrator). Ottieni `api_key` e `api_secret`
(il secret si vede **una sola volta**: copialo subito).

Frappe autentica ogni chiamata REST con l'header:

```
Authorization: token <api_key>:<api_secret>
```

Per le prove manuali con `curl`:

```bash
export ERP=http://localhost:8080
export AUTH="Authorization: token <api_key>:<api_secret>"
curl -sS "$ERP/api/method/frappe.auth.get_logged_user" -H "$AUTH"   # deve rispondere "Administrator"
```

## 2bis. Collegare Workflower all'istanza

Workflower legge la configurazione ERP **dall'ambiente** (mai hard-coded). Bastano le tre
variabili obbligatorie; le altre migliorano il mapping.

```bash
export ERP_BASE_URL=http://localhost:8080     # l'URL dell'istanza (in prod: https://erp.tuodominio.it)
export ERP_API_KEY=<api_key>
export ERP_API_SECRET=<api_secret>
# opzionali ma consigliate per Purchase Invoice/Cost Center reali:
export ERP_COMPANY="La Tua Azienda"           # nome azienda in ERPNext
export ERP_CONTO_RITENUTA="Ritenute - X"      # account_head della ritenuta (X = sigla azienda)
export ERP_CONTO_IVA="IVA ns credito - X"     # opzionale
```

- **Sviluppo locale**: esporta le variabili nella shell che lancia `make dev` (o mettile in
  un file caricato dal tuo shell profile). Se non sono impostate, l'integrazione è **spenta**
  e Workflower funziona come prima (nessun errore).
- **Deploy con docker-compose** (Workflower): aggiungi le stesse `ERP_*` al servizio `app`
  in `docker-compose.yml` / al tuo `.env` (vedi `deploy.env.example`). Se ERPNext gira nello
  stesso compose/host, usa il nome-servizio o l'IP raggiungibile (non `localhost`, che dentro
  al container punta al container stesso).

Verifica il collegamento **senza scrivere codice**:

```bash
make erp-smoke                 # connettività + Supplier + Cost Center
make erp-smoke ARGS=--full     # anche una Purchase Invoice con ritenuta (serve master data)
```

Deve stampare `[PASS]`. Dall'app: valida una fattura e controlla `GET /api/erp/stato` e la
comparsa della Purchase Invoice in ERPNext. Dettagli operativi in `docs/erp-integrazione.md`;
i test automatici e il triage in `docs/erp-test-plan.md`.

## 3. Mappatura da provare a mano

Riferimento dati Workflower: `backend/app/seed_assets/schemas/fattura.schema.json`
(`fornitore_id`, `cantiere_id`, `numero`, `data`, `imponibile`, `iva`, `totale`,
`ritenuta_acconto`, `righe[]`). Il caso ritenuta del seed è `FT-2026-0004` /
fixture `fattura-studio-bianchi.pdf` (ritenuta d'acconto in calce).

### 3.1 Fornitore → Supplier

```bash
curl -sS -X POST "$ERP/api/resource/Supplier" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"supplier_name":"Studio Bianchi","supplier_group":"Services","supplier_type":"Company","tax_id":"01234567890"}'
```

### 3.2 Cantiere → Cost Center

```bash
curl -sS -X POST "$ERP/api/resource/Cost Center" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"cost_center_name":"Cantiere Via Roma","company":"<La Tua Azienda>","is_group":0}'
```

### 3.3 Fattura con ritenuta → Purchase Invoice + Tax Withholding

Punti da verificare:

- le **righe** (`items[]`) portano `cost_center` = il cantiere (imputazione del costo);
- `imponibile`/`iva`/`totale` tornano (`totale ≈ imponibile + iva`);
- la **ritenuta d'acconto** è gestita nativamente come *Tax Withholding Category*
  applicata al Supplier, oppure come riga di *Purchase Taxes and Charges* deduttiva —
  **questo è il punto critico del go/no-go**.

```bash
curl -sS -X POST "$ERP/api/resource/Purchase Invoice" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{
    "supplier": "Studio Bianchi",
    "bill_no": "12/2026",
    "bill_date": "2026-03-10",
    "apply_tds": 1,
    "items": [
      {"item_name":"Prestazione professionale","description":"Parcella","qty":1,"rate":4000,"cost_center":"Cantiere Via Roma - XYZ"}
    ]
  }'
```

Verificare nel documento creato che l'importo della ritenuta corrisponda a quello
letto da Workflower (`ritenuta_acconto`), e che il netto a pagare sia coerente.

## 3bis. Tre cose che ERPNext pretende (emerse dal PoC)

Il finto server dei test le lasciava passare; un'istanza reale no. Tutte e tre sono
ora coperte dai test (`test_erp_translate.py`, `test_erp_sync_e2e.py`) e configurabili
dall'ambiente — con `make erp-dev-setup` sono già pronte sull'ERPNext di sviluppo.

| Cosa | Perché | Come |
|---|---|---|
| **Padre del Cost Center** | i Cost Center sono un albero: `Please enter parent cost center` | derivato dalla Company (radice omonima); override `ERP_PARENT_COST_CENTER` |
| **Conto di costo sulle righe fattura** | senza `item_code` ERPNext non lo deriva: `Expense account is mandatory for item` | derivato da `Company.default_expense_account`; override `ERP_CONTO_COSTO` |
| **Articolo sulle righe DDT** | la Purchase Receipt è un documento di magazzino: `Item None does not exist` | `ERP_ITEM_DDT` = codice di un articolo generico **non di magazzino** (`is_stock_item=0`), così non movimenta il magazzino e la descrizione del DDT resta sulla riga |

Le prime due si risolvono da sole leggendo la Company: non serve configurarle. La
terza è **obbligatoria** per sincronizzare i DDT — senza, la sincronizzazione del
singolo DDT si fermerebbe con un messaggio che dice cosa impostare (la validazione
del documento in Workflower regge comunque, come per ogni errore ERP).

## 4. Localizzazione italiana / SdI (verifica, non blocco)

Il ciclo passivo **non emette** verso SdI, quindi la localizzazione pesa poco qui.
Da annotare comunque per il futuro:

- App community e-invoicing per ERPNext: [`mascor/erpnext_fattura_elettronica`](https://github.com/mascor/erpnext_fattura_elettronica)
  — verificarne stato/manutenzione e compatibilità con la versione ERPNext scelta.
- Gestione nativa *Tax Withholding* per la ritenuta (usata al §3.3).

## 5. Criterio go/no-go

**GO** se tutte queste condizioni sono verificate a mano — tutte **verificate** su
ERPNext v15 (fattura `07/2026` del seed: imponibile 4000, IVA 880, ritenuta 800):

- [x] Fornitore creabile come Supplier con `tax_id` (partita IVA).
- [x] Cantiere rappresentabile come Cost Center e imputabile sulle righe
      (`Residenza Le Palme - AC` sulla riga, sotto la radice della Company).
- [x] Fattura con ritenuta → Purchase Invoice con **importo ritenuta coerente** con
      `ritenuta_acconto`: riga *Deduct* di **800,00** esatti sul conto `Ritenute - AC`.
- [x] `totale ≈ imponibile + iva` preservato: `net_total` 4000 + IVA 880 = **4880**;
      dedotta la ritenuta il netto a pagare è **4080**.
- [x] API REST raggiungibile con token `key:secret` (base per `core/erp.py`, già pronto in M23).

**NO-GO / rivalutare** se la ritenuta non è mappabile in modo affidabile o se la
versione ERPNext richiede un'app localizzazione instabile: in tal caso valutare il
*piano B* dell'analisi (Odoo per la sola profondità fiscale, o intermediario SdI dedicato).

## 6. Esito

```
Data:             2026-07-27
Versione ERPNext: v15.118.1 (Frappe v15.116.0), immagine frappe/erpnext:v15, MariaDB 10.6
Ritenuta mappata: sì — riga di Purchase Taxes and Charges "Deduct", charge_type
                  "Actual", account_head = ERP_CONTO_RITENUTA, importo esatto letto
                  da Workflower (nessuna delega al calcolo di ERPNext). Verificata
                  sul documento creato: 800,00 su 4000 di imponibile, netto 4080.
Decisione:        GO
Note:             il piano dei conti italiano di ERPNext (country=Italy) fornisce già
                  i conti IVA 22/10/4%; il conto ritenute va aggiunto (lo fa
                  `make erp-dev-setup`). Tre campi obbligatori emersi solo contro
                  l'istanza reale: vedi §3bis. Verificato anche oltre il PoC:
                  DDT→Purchase Receipt, read-back pagamenti, re-sync e tenuta con
                  ERP giù (dettagli in docs/erp-test-plan.md).
```
