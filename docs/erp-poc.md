# PoC integrazione ERP (ERPNext) — runbook M22

Questo documento è il **cancello go/no-go** del track "Integrazione ERP"
(`piano-implementazione-erp.md`, M22). Obiettivo: **provare a mano**, prima di
scrivere l'adattatore in Workflower, che il mapping regge — in particolare la
`fattura` con **ritenuta d'acconto** → *Purchase Invoice* con *Tax Withholding*, e
l'imputazione del costo al **cantiere** come *Cost Center*.

> Nota onestà: i comandi qui sotto **non sono stati eseguiti** contro un'istanza
> reale in questo repository — vanno lanciati nell'ambiente di sviluppo di chi fa
> il PoC. Il criterio go/no-go (in fondo) è ciò che decide se proseguire con M23+.

## 0. Contesto e confine

- Workflower resta il *system-of-record dei documenti* (estrazione + validazione umana).
- ERPNext è il *system-of-record contabile* a valle, alimentato **solo** dai documenti validati.
- Flusso **mono-direzionale** WF→ERP; l'unico ritorno è la lettura dello stato di pagamento (M27).
- ERPNext è una **dipendenza esterna**: gira in un suo deploy, Workflower lo raggiunge via HTTP.

## 1. Alzare un'istanza ERPNext di sviluppo

Due strade:

1. **Ufficiale (consigliata per qualcosa di stabile)**: il progetto
   [`frappe_docker`](https://github.com/frappe/frappe_docker) — segue il `README`
   e la guida `pwd.yml` per un'istanza completa.
2. **Rapida (PoC)**: lo starter incluso in questo repo:

   ```bash
   docker compose -f docker-compose.erpnext.yml up -d
   # attendere che il servizio `create-site` termini (bench new-site + install erpnext)
   docker compose -f docker-compose.erpnext.yml logs -f create-site
   ```

   UI su `http://localhost:8080` (utente `Administrator`, password da `ERP_ADMIN_PASSWORD`,
   default `admin`). Se `erp.localhost` non risolve, aggiungerlo a `/etc/hosts` o usare
   l'header `Host: erp.localhost`.

   > È un punto di partenza minimale: se `create-site` fallisce (tempi/versioni),
   > passare alla strada 1. La validazione del *mapping* non dipende da come è alzato l'ERP.

## 2. Credenziali API (token key:secret)

In ERPNext: **User → (Administrator) → Settings → API Access → Generate Keys**.
Si ottengono `api_key` e `api_secret`. Frappe autentica ogni chiamata REST con:

```
Authorization: token <api_key>:<api_secret>
```

Sono i valori che poi Workflower legge da `ERP_BASE_URL` / `ERP_API_KEY` / `ERP_API_SECRET`
(vedi `deploy.env.example`). Per il PoC si usano direttamente con `curl`.

```bash
export ERP=http://localhost:8080
export AUTH="Authorization: token <api_key>:<api_secret>"
```

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

## 4. Localizzazione italiana / SdI (verifica, non blocco)

Il ciclo passivo **non emette** verso SdI, quindi la localizzazione pesa poco qui.
Da annotare comunque per il futuro:

- App community e-invoicing per ERPNext: [`mascor/erpnext_fattura_elettronica`](https://github.com/mascor/erpnext_fattura_elettronica)
  — verificarne stato/manutenzione e compatibilità con la versione ERPNext scelta.
- Gestione nativa *Tax Withholding* per la ritenuta (usata al §3.3).

## 5. Criterio go/no-go

**GO** se tutte queste condizioni sono verificate a mano:

- [ ] Fornitore creabile come Supplier con `tax_id` (partita IVA).
- [ ] Cantiere rappresentabile come Cost Center e imputabile sulle righe.
- [ ] Fattura con ritenuta → Purchase Invoice con **importo ritenuta coerente** con `ritenuta_acconto`.
- [ ] `totale ≈ imponibile + iva` preservato.
- [ ] API REST raggiungibile con token `key:secret` (base per `core/erp.py`, già pronto in M23).

**NO-GO / rivalutare** se la ritenuta non è mappabile in modo affidabile o se la
versione ERPNext richiede un'app localizzazione instabile: in tal caso valutare il
*piano B* dell'analisi (Odoo per la sola profondità fiscale, o intermediario SdI dedicato).

## 6. Esito

Registrare qui la decisione (data, versione ERPNext provata, note sulla ritenuta):

```
Data:            ____
Versione ERPNext: ____
Ritenuta mappata: sì / no  — come: ____
Decisione:       GO / NO-GO
Note:            ____
```
