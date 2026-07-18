# Workflower

Sistema **LLM-driven** per il controllo costi dei cantieri edili. L'idea (vedi
[`analisi-progettazione.md`](analisi-progettazione.md)) è rovesciare l'approccio
tradizionale: le funzionalità non sono codice, ma **workflow dichiarativi
eseguiti da agenti LLM**. Il codice costruisce solo la cornice stabile — storage,
runtime, UI, sicurezza — e i workflow (prompt, skill, schemi) sono **dati
versionati in Git**, che gli agenti stessi migliorano con approvazione umana.

Questa è la PoC (F1): il giro completo del workflow **carica-fattura** con due
modalità UI (Operatore mobile-first e Admin) e il **ciclo di auto-miglioramento**.

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

## Comandi

| Comando | Cosa fa |
|---|---|
| `make setup` | Prima installazione (venv + dipendenze) |
| `make dev` | Backend (:8000) + frontend (:5173) |
| `make seed` | Crea il repo dati `./data` (git separato) |
| `make fixtures` | Genera 3 PDF fattura sintetici in `./fixtures` |
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

Dettagli: [`analisi-progettazione.md`](analisi-progettazione.md) (architettura e
ADR) e [`piano-implementazione.md`](piano-implementazione.md) (contratti e
milestone). `mockup.html` è il riferimento UX.

## Note

- **Senza chiave LLM** non giri il flusso reale, ma i **test** funzionano lo
  stesso: usano un trasporto LLM finto e deterministico. Lancia `make test`.
- Lo scenario **ritenuta d'acconto** è la *definition of done* della v1 ed è
  coperto da un test end-to-end che non deve mai rompersi
  (`backend/tests/test_improver_e2e.py`).
- I dati d'esempio sono immaginari (cantieri, fornitori e fatture della zona di
  Catania) e servono solo alla demo.
