# Piano di test & verifica — Integrazione ERP (ERPNext)

Come eseguire e verificare tutti i casi d'uso dell'integrazione, e come intervenire
in caso di problemi. Due livelli:

1. **Test automatici** (trasporto ERP finto, nessun ERPNext reale) — coprono la logica.
2. **Smoke test** contro un ERPNext **reale** — verifica deploy/configurazione.

## Come si eseguono

```bash
make setup        # una volta: venv Python 3.12 + dipendenze
make test-erp     # SOLO i test ERP, verbosi (veloci, trasporto finto)
make test         # intera suite del backend (include gli ERP)
make lint         # ruff + eslint

# Smoke contro un ERPNext reale (serve configurare le ERP_* nell'ambiente):
make erp-smoke              # connettività + Supplier + Cost Center
make erp-smoke ARGS=--full  # anche creazione Purchase Invoice con ritenuta
```

I test ERP sono marcati `@pytest.mark.erp`: `pytest -m erp` li seleziona tutti
(`make test-erp`). Sono tutti in `backend/tests/test_erp_*.py`.

## Cosa è coperto (caso d'uso → test)

| Caso d'uso | Dove |
|---|---|
| **Config da env** (assente/parziale/completa); interruttore `erp_attivo` | `test_erp_client.py` |
| Client HTTP: URL+header auth, 200, HTTP≥400, trasporto giù, non configurato | `test_erp_client.py` |
| **Translator fornitore→Supplier** (con/senza partita IVA) | `test_erp_translate.py` |
| **Translator cantiere→Cost Center** | `test_erp_translate.py` |
| **Translator fattura→Purchase Invoice**: righe (qty/rate), cost center, IVA in aggiunta | `test_erp_translate.py` |
| **Ritenuta d'acconto → riga in detrazione** (importo esatto) / fallback `apply_tds` | `test_erp_translate.py`, `test_erp_sync_e2e.py` |
| **Translator DDT→Purchase Receipt** (quantità, niente importi) | `test_erp_translate.py` |
| Invariante `totale ≈ imponibile + iva` | `test_erp_translate.py` |
| Mapping su **dati reali del seed** (fattura con ritenuta) | `test_erp_translate.py` |
| **Sync alla validazione**: backref `meta.erp_id`, ledger, commit git | `test_erp_sync_e2e.py` |
| **Idempotenza** sync (fattura e DDT) — nessun doppione | `test_erp_sync_e2e.py` |
| **Fornitore non duplicato** (riuso per partita IVA) | `test_erp_sync_e2e.py` |
| Fattura **senza cantiere** (niente cost center) / **senza fornitore** (issue) | `test_erp_sync_e2e.py` |
| **Errore ERP non blocca la validazione** (issue + ledger errore) | `test_erp_sync_e2e.py` |
| Tipo **non sincronizzabile** (SAL) → nessun effetto | `test_erp_sync_e2e.py` |
| **ERP non configurato** → no-op | `test_erp_sync_e2e.py` |
| **DDT → Purchase Receipt** end-to-end | `test_erp_sync_e2e.py` |
| **Read-back pagamenti**: crea/aggiorna, niente doppioni, pagato→parziale | `test_erp_pagamenti_e2e.py` |
| Entità `pagamento` **puro dato** visibile in `v_pagamenti` | `test_erp_pagamenti_e2e.py` |
| Read-back senza fatture sincronizzate / con errore di lettura | `test_erp_pagamenti_e2e.py` |
| **Stato sync** (contatori, da-sincronizzare, ultimi tentativi) | `test_erp_osservabilita_e2e.py` |
| **Re-sync** batch e singolo; **early-abort** con ERP giù; **recupero** dopo ripristino | `test_erp_osservabilita_e2e.py` |
| Re-sync singolo 404 / tipo non sincronizzabile / ERP non configurato | `test_erp_osservabilita_e2e.py` |
| **RBAC**: endpoint ERP solo admin (401 senza token, 403 operatore) | `test_erp_auth.py` |
| **Scarto bloccato** se il documento è a valle: bozza → "elimina", confermato → "annulla", ERP giù → "riprova" | `test_scarti_erp.py` |
| Scarto **permesso** a documento annullato (`docstatus` 2) o eliminato (404) | `test_scarti_erp.py` |
| Nessuna lettura a valle se il documento non è mai stato sincronizzato | `test_scarti_erp.py` |
| **Campi obbligatori di ERPNext**: padre del Cost Center, conto di costo sulle righe fattura, articolo sulle righe DDT | `test_erp_translate.py`, `test_erp_sync_e2e.py` |
| Resolver del master data (radice Cost Center, conto di costo dalla Company) | `test_erp_sync_e2e.py` |
| DDT senza `ERP_ITEM_DDT` → errore **azionabile** (dice cosa configurare) | `test_erp_sync_e2e.py` |
| Il finto rifiuta i payload incompleti come Frappe (la rete che regge i casi sopra) | `test_erp_sync_e2e.py` |
| Esiti di sincronizzazione (ok/errore) tracciati nel **logbook** | `test_erp_sync_e2e.py` |
| **Regressione ritenuta (M5)** — non deve mai rompersi | `test_improver_e2e.py::test_scenario_ritenuta` (+ runtime/views/toolsmith) |

Attrezzatura di test: `tests/fake_erp.py` — `ErpServerFinto` (finto server Frappe
stateful: crea/filtra documenti, GET-by-name, `guasta()`/`ripristina()` per simulare
guasti e ripristini) e `FakeTrasporto` (risposte predefinite). Iniettati via
`create_app(erp=...)` (fixture `crea_client(erp=...)`).

> Il finto è deliberatamente **severo**: rifiuta con 417 i payload senza i campi che
> ERPNext pretende (`OBBLIGATORI_TESTATA` / `OBBLIGATORI_RIGHE`) e parte con il master
> data che ogni istanza configurata possiede (Company + Cost Center radice). È la
> lezione del PoC: un finto gentile aveva lasciato passare tre bug che solo l'istanza
> reale ha respinto. Con `permissivo=True` si torna al comportamento indulgente per i
> test che non stanno provando il mapping.

## Verifica del deploy/integrazione (ERPNext reale)

Tre comandi, da zero a `[PASS]` (la prima volta scarica ~2 GB e crea il sito: qualche minuto):

```bash
make erp-up            # alza ERPNext in Docker (create-site è idempotente: si può ripetere)
make erp-dev-setup     # company, piano dei conti, conto ritenute, articolo DDT, API key
                       # → stampa le ERP_* da esportare (copia-incolla nella shell)
make erp-smoke ARGS=--full
```

`make erp-dev-setup` è **idempotente** e sostituisce i passaggi manuali nella UI di
ERPNext (setup wizard + *Generate Keys*). È solo per sviluppo/PoC: in produzione si
segue la procedura ERPNext con un utente API dedicato.

Poi la prova dall'app: valida una fattura e controlla `GET /api/erp/stato` + la
Purchase Invoice comparsa in ERPNext. Se l'app gira **in container** e ERPNext è sullo
stesso host, `ERP_BASE_URL` deve usare `host.docker.internal` (dentro al container
`localhost` è il container stesso); le `ERP_*` del `.env` arrivano già al servizio
`app` di `docker-compose.yml`.

I record creati dallo smoke hanno prefisso `WF-SMOKE` (facili da individuare/ripulire).

### Cosa è stato verificato contro un'istanza reale

ERPNext v15.118.1 in Docker, seed di Workflower, app in container (esito: tutto verde):

| Verifica | Esito |
|---|---|
| Smoke `--full`: connettività, Supplier, Cost Center, Purchase Invoice con ritenuta | `[PASS]` ×4 |
| Ritenuta d'acconto sul documento a valle (scenario M5) | riga *Deduct* 800,00 esatti; netto 4080 su 4880 |
| Imputazione al cantiere | `cost_center` = `Residenza Le Palme - AC` sulle righe |
| Validazione dall'app → Purchase Invoice | `erp_id` + `erp_synced` sull'envelope |
| Re-sync batch di 7 documenti (5 fatture + 2 DDT) | 7/7 ok, 0 errori |
| DDT → Purchase Receipt | creata (articolo generico non di magazzino) |
| Read-back pagamenti (M27) | fattura pagata → `pagamento` "pagato" 4080, visibile in `v_pagamenti` |
| Idempotenza di re-sync e read-back | 0 doppioni (read-back: 0 creati / 6 aggiornati) |
| **ERP giù** durante la validazione | documento **validato** comunque + issue automatica |
| Recupero a ERP tornato su | `POST /api/erp/risincronizza` → 1/1 ok |

## Triage — se qualcosa fallisce

| Sintomo | Dove guardare / cosa fare |
|---|---|
| `make test-erp` rosso | Il nome del test dice il caso d'uso; il fallimento è nella logica, non nell'ERP |
| Smoke: `[FAIL] connettività/auth` | `ERP_BASE_URL` errato o API key non valide/senza permessi |
| Smoke: `[FAIL] fattura→Purchase Invoice` | Quasi sempre master data ERPNext (item/conti/company): configurali o ometti `--full` |
| In produzione una fattura non arriva a valle | `GET /api/erp/stato` → se è tra le `da_sincronizzare`, `POST /api/erp/risincronizza`; guarda l'issue automatica e il ledger `data/dataset/erp_sync.jsonl` |
| ERP momentaneamente giù | La validazione regge comunque; a ERP tornato su, `POST /api/erp/risincronizza` recupera |
| Dubbi sull'importo ritenuta | La riga `Ritenuta d'acconto` (Deduct) porta l'importo esatto estratto da WF; vedi `test_erp_translate.py` |

Regola d'oro: **`make test` deve restare verde a ogni intervento**, e lo scenario
**ritenuta d'acconto** non si rompe mai (CLAUDE.md).
