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
| **Regressione ritenuta (M5)** — non deve mai rompersi | `test_improver_e2e.py::test_scenario_ritenuta` (+ runtime/views/toolsmith) |

Attrezzatura di test: `tests/fake_erp.py` — `ErpServerFinto` (finto server Frappe
stateful: crea/filtra documenti, GET-by-name, `guasta()`/`ripristina()` per simulare
guasti e ripristini) e `FakeTrasporto` (risposte predefinite). Iniettati via
`create_app(erp=...)` (fixture `crea_client(erp=...)`).

## Verifica del deploy/integrazione (ERPNext reale)

1. Alza ERPNext (vedi `docs/erp-poc.md` / `docker-compose.erpnext.yml`).
2. Genera le API key in ERPNext ed esporta `ERP_BASE_URL`, `ERP_API_KEY`,
   `ERP_API_SECRET` (e `ERP_COMPANY`, `ERP_CONTO_RITENUTA` per il passo `--full`).
3. `make erp-smoke` → deve stampare `[PASS]` su connettività, Supplier, Cost Center.
   Con `ARGS=--full` verifica anche la Purchase Invoice con ritenuta.
4. Prova reale dall'app: valida una fattura e controlla `GET /api/erp/stato` +
   la Purchase Invoice comparsa in ERPNext.

I record creati dallo smoke hanno prefisso `WF-SMOKE` (facili da individuare/ripulire).

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
