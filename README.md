# Workflower

Sistema **LLM-driven** per il controllo costi dei cantieri edili. L'idea (vedi
[`analisi-progettazione.md`](analisi-progettazione.md)) è rovesciare l'approccio
tradizionale: le funzionalità non sono codice, ma **workflow dichiarativi
eseguiti da agenti LLM**. Il codice costruisce solo la cornice stabile — storage,
runtime, UI, sicurezza — e i workflow (prompt, skill, schemi) sono **dati
versionati in Git**, che gli agenti stessi migliorano con approvazione umana.

La PoC (F1) è il giro completo del workflow **carica-fattura** con due modalità
UI (Operatore mobile-first e Admin) e il **ciclo di auto-miglioramento**. La
**Fase 2** (M7–M13, vedi [`piano-implementazione-fase2.md`](piano-implementazione-fase2.md))
la estende **senza toccare il runtime**: instradamento automatico dei documenti e
quattro entità (fattura, **DDT**, **SAL**, **rapportino ore**), **computo** con
confronto previsto/consuntivo, **registro** consolidato per cantiere, **report
Excel** e raccolta del dataset per il tier locale.

La **Fase 3** (M14–M21, vedi [`piano-implementazione-fase3.md`](piano-implementazione-fase3.md))
punta al **costo marginale ~0**: consolidare le operazioni ricorrenti in *codice
deterministico come dato*. Aggiunge la **sandbox** per il codice generato, il
**registry dei tool Python**, il **Toolsmith** (che propone tool a partire dai
trace validati), il **tier locale T3** con misura offline ed escalation a T1, e —
sempre come puro dato — nuove **entità di dominio** e i **registri automatici**
(pozzetti, cronoprogramma). Anche qui `runtime.py`/`gateway.py`/`dal.py` restano
la cornice stabile.

## Cosa fa, in una riga

Foto/PDF di una fattura → estrazione LLM → bozza validata contro schema →
revisione dell'ufficio → se qualcosa non torna, l'**Improver** propone una patch
al workflow, la prova sui casi già validati (golden set) e — dopo l'ok umano —
pubblica una nuova versione che estrae correttamente. Il dato finisce nel
cruscotto costi.

## Prerequisiti

- **Python 3.12** (`py -3.12` su Windows)
- **Node 18+** (per il frontend)
- **git** (il repo dati è un repo git separato, creato dal seed)

## Avvio rapido

```bash
make setup           # venv backend + dipendenze + npm install
cp .env.example .env  # poi inserisci una chiave LLM (Anthropic/OpenAI/Gemini)
make demo            # crea il repo dati d'esempio + le fixture + stampa il giro guidato
make dev             # backend :8000, frontend :5173
```

Apri:
- **Operatore** (mobile-first): <http://localhost:5173/op>
- **Admin** (ufficio): <http://localhost:5173/admin>

I modelli LLM **non sono mai hard-coded**: si scelgono in `.env`
(`LLM_T1_MODEL` = SOTA per estrazione/Improver, `LLM_T2_MODEL` = medio per
text-to-SQL e giudizio). Qualunque modello supportato da litellm.

### Utenti demo

| Utente | Codice | Ruolo | Cantiere |
|---|---|---|---|
| `salvo` | `1111` | operatore | Residenza Le Palme |
| `giuseppe` | `2222` | operatore | Scuola Manzoni |
| `marco` | `3333` | operatore | Capannone Etna Sud |
| `giovanna` | `9999` | **admin** | tutti |

## Il giro della demo (≈ 5 minuti)

**Operatore** (`/op`, accedi come `salvo` / `1111`):

1. *Carica un documento* → scegli `fixtures/fattura-studio-bianchi.pdf` (una
   parcella con **ritenuta d'acconto in calce**).
2. Il sistema legge e mostra il riepilogo. La v1.0 del workflow **non conosce**
   la ritenuta: manca.
3. *👎 Qualcosa non torna* → scrivi «manca la ritenuta d'acconto» → *Invia*.
   Risposta: «🤝 Grazie! Ci pensiamo noi».

**Admin** (`/admin`, accedi come `giovanna` / `9999`):

4. **Cruscotto**: costi per cantiere, ritenute, scostamenti sul budget.
5. **Segnalazioni**: trovi la segnalazione dell'operatore → *Migliora il workflow*.
6. **Workflows**: l'Improver ha proposto una **patch** (diff colorato) e l'ha
   provata sul **golden set** (replay N/N). Se non ci sono regressioni →
   *Approva e applica*: il workflow passa a **v1.1** e il documento d'origine
   viene rielaborato — ora la ritenuta (800 €) c'è.
7. **Revisione**: apri la bozza corretta, confronta con l'originale, *Salva come
   validato* (entra nel golden set come regressione futura).
8. **Interroga**: «Quali fatture hanno una ritenuta d'acconto?» → SQL generato +
   tabella (guardrail: solo SELECT sulle viste, LIMIT forzato).
9. **Log & Dataset**: costo per documento, tool call, export `toolcalls.jsonl`,
   query ricorrenti (candidate al consolidamento in tool).

### Il giro della Fase 2 (multi-entità e costi)

Carica anche gli altri documenti sintetici (come operatore, o come admin senza
vincolo di cantiere): `fixtures/ddt-edil-sud.pdf`, `fixtures/sal-capannone-etna.pdf`,
`fixtures/rapportino-le-palme.pdf`. Il **classificatore** li riconosce e li instrada
al workflow giusto — nessun codice nuovo, solo un manifest per tipo.

10. **Cruscotto**: oltre ai costi, i KPI di DDT, SAL, ore e costo manodopera. I
    nomi dei cantieri aprono il **registro** (fascicolo consolidato: fatture, DDT,
    ore, avanzamento, scostamento) con **Scarica Excel**.
11. **Scostamenti**: il confronto **computo ↔ consuntivo** per voce e per cantiere.
    In *Revisione* di una fattura, *Collega al computo* abbina le righe alle voci
    (deterministico) e la spesa risale nello scostamento.
12. **Skills & Tools**: il registry dei tool con i contatori d'uso e il **dataset
    di fine-tuning** — solo le tool call dei documenti validati diventano esempi
    (scaricabili come `finetuning.jsonl`).
13. **Report Excel**: dal cruscotto, *Scarica report Excel* genera un `.xlsx` con
    i fogli Riepilogo, Fatture, DDT, Ore, SAL e Scostamento computo.

### Il giro della Fase 3 (costo marginale ~0)

La terza forma di consolidamento è il **codice deterministico**, trattato come
dato esattamente come viste e tool parametrici.

14. **Skills & Tools → Candidati Python**: il **Toolsmith** individua i calcoli
    ricorrenti dal *delta fra bozza estratta e dato validato* (l'esempio guida è
    il **calcolo della ritenuta d'acconto**) e propone una **funzione Python** con
    i test **generati dai trace storici**. La proposta è ispezionabile: codice,
    test + esito in **sandbox**, esempi. *Approva* → il tool è registrato
    (`data/tools/<nome>/`, eseguito **solo** in sandbox isolata) e la skill viene
    patchata per chiamarlo, con l'LLM come **fallback** se il tool sbaglia.
15. **Log & Dataset → Idoneità T3**: l'**harness** (`/api/dataset/eval-t3`) rigioca
    gli esempi validati contro un modello locale candidato e ne misura la
    *function-calling accuracy* vs T1 per workflow, indicando i workflow "pronti".
    Con `LLM_T3_MODEL` impostato, uno step su T3 gira in locale (costo ~0) ed
    **escala a T1** su errore/bassa confidence, con la **% escalation** tracciata.
16. **Anagrafiche e registri**: nuove entità di dominio come puro dato
    (**materiale**, **mezzo**, **lavorazione**, **scadenza**) e i **registri
    automatici** — **pozzetti** (manufatti con stato) e **cronoprogramma**
    (pianificato vs consuntivo, dall'ultimo SAL) — che si aggiornano da soli a
    ogni documento e finiscono nel cruscotto, nel registro e nel report Excel.

## Comandi

| Comando | Cosa fa |
|---|---|
| `make setup` | Prima installazione (venv + dipendenze) |
| `make dev` | Backend (:8000) + frontend (:5173) |
| `make seed` | Crea il repo dati `./data` (git separato) |
| `make fixtures` | Genera i PDF sintetici in `./fixtures` (fatture + DDT/SAL/rapportino) |
| `make demo` | Seed + fixtures + istruzioni del giro |
| `make test` | Test backend (pytest) |
| `make lint` | Ruff (backend) + ESLint (frontend) |

## Architettura in breve

- **Storage**: il file system è la fonte di verità (un JSON per entità, repo git
  separato in `./data`, ogni mutazione = commit). **DuckDB** legge quei file per
  le query — nessun DB server, nessun ORM (ADR-1).
- **Gateway** (litellm): i workflow dichiarano un *tier* (T1/T2), non un modello
  (ADR-2).
- **Workflow-as-data**: manifest YAML + skill Markdown in `data/workflows/`, in
  italiano; l'Improver li modifica, gli umani approvano (ADR-3).
- **Bozza-first**: nessun dato diventa `validato` senza conferma umana (ADR-4).
- **Due modalità nette**: Operatore (uso, meccanica LLM invisibile) e Admin
  (governo ed evoluzione). L'operatore non approva mai patch (ADR-6).

- **Aggiungere un'entità = aggiungere dati** (Fase 2/3): uno schema JSON, una riga
  nel registry, una vista, un manifest con skill. `runtime.py`, `gateway.py`,
  `dal.py` non cambiano. Così DDT, SAL, rapportini, computo — e le entità di
  Fase 3 (materiale, mezzo, lavorazione, scadenza, pozzetto, cronoprogramma) —
  girano sullo stesso motore della fattura.
- **Consolidare = dato, non codice** (Fase 3): le operazioni ricorrenti diventano
  viste `v_*`, tool parametrici `t_*` o **tool Python** in `data/tools/`. Il
  codice generato è *dato versionato, approvato, eseguito solo in sandbox isolata*
  e mai importato in-process; il tool è un'ottimizzazione con **fallback all'LLM**.
- **Tier del modello = dato**: i workflow dichiarano un tier (T1/T2/**T3** locale),
  mai un modello. L'idoneità a T3 si *misura* prima di instradare (harness offline)
  e l'escalation a T1 protegge sempre l'esito.

Dettagli: [`analisi-progettazione.md`](analisi-progettazione.md) (architettura e
ADR), [`piano-implementazione.md`](piano-implementazione.md) (contratti e
milestone v1), [`piano-implementazione-fase2.md`](piano-implementazione-fase2.md)
(M7–M13) e [`piano-implementazione-fase3.md`](piano-implementazione-fase3.md)
(M14–M21). Il fine-tuning del tier locale è un runbook operativo:
[`docs/finetuning-runbook.md`](docs/finetuning-runbook.md). `mockup.html` è il
riferimento UX.

## Note

- **Senza chiave LLM** non giri il flusso reale, ma i **test** funzionano lo
  stesso: usano un trasporto LLM finto e deterministico. Lancia `make test`.
- Lo scenario **ritenuta d'acconto** è la *definition of done* della v1 ed è
  coperto da un test end-to-end che non deve mai rompersi
  (`backend/tests/test_improver_e2e.py`); in Fase 3 lo stesso calcolo è anche
  l'esempio guida del Toolsmith (`test_toolsmith_m17.py`).
- Il **codice generato** gira solo in **sandbox isolata** (subprocess, import in
  whitelist, niente rete/FS/ambiente, limiti CPU/memoria/tempo): mai importato
  in-process. Le forme d'abuso sono coperte da `test_sandbox.py`.
- I dati d'esempio sono immaginari (cantieri, fornitori e fatture della zona di
  Catania) e servono solo alla demo.
