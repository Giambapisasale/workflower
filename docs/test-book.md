# Test-book — verifica manuale di Workflower

Copre **tutti i casi d'uso della piattaforma allo stato attuale** (M0–M29): le due
interfacce, il ciclo di auto-miglioramento, il consolidamento, l'integrazione
contabile con ERPNext, log e diagnosi.

È pensato per essere eseguito a mano, in ordine, da una persona sola in una
sessione. Serve a rispondere a una domanda: *cosa funziona davvero quando lo tocchi
con le dita*, non *cosa passa in pytest*. La suite automatica (`make test`) copre la
logica; questo copre l'esperienza.

**Durata indicativa:** 2 ore per il giro completo, 35 minuti per il solo percorso
critico (i casi segnati ⭐).

---

## Legenda

| Segno | Significato |
|---|---|
| ⭐ | Percorso critico: se salta questo, salta il prodotto |
| 🔑 | Serve una **chiave LLM** attiva e un modello valido |
| 🧾 | Serve **ERPNext** acceso e collegato |
| ⌨ | **Nessun pulsante nell'interfaccia**: si prova via API (`curl`) |
| 💶 | Consuma token a pagamento |

Esito di ogni caso: `☐ OK` `☐ KO` — se KO, annota **cosa hai visto**, non cosa ti
aspettavi (quello è già scritto).

---

## 1 · Preparazione dell'ambiente

### 1.1 Scegli l'ambiente

Due strade. Non sono equivalenti: scegli in base a cosa vuoi provare.

| | **A — Locale (`make dev`)** | **B — Docker (già in piedi)** |
|---|---|---|
| Interfaccia | <http://localhost:5173/op> · `/admin` | <http://localhost/op> · `/admin` |
| Golden set di partenza | **presente** (2 casi dal seed) | **vuoto** ¹ |
| PDF di prova | in `fixtures/` + scaricabili dall'app | scaricabili dall'app |
| Configurazione | variabili **nella shell** ² | dal file `.env` |
| Ricarica del codice | a caldo | serve `docker compose up -d --build` |
| Adatto a | **giro completo**, sezioni H/I/J | sezioni A–G, K, L |

¹ Il golden set viene seminato solo se `reportlab` è installato, e nell'immagine di
produzione non c'è (è una dipendenza di sviluppo). Non è un guasto: il golden set
si riempie da solo man mano che validi documenti in Revisione. Ma la **sezione H
(Improver)** con golden vuoto verifica molto poco — il replay direbbe `0/0`. Per H
usa l'ambiente A, o esegui prima D3 due o tre volte.

² Il progetto **non legge il `.env`** fuori da Docker: `make dev` usa l'ambiente del
processo. Le variabili vanno impostate nella shell, e la sintassi non è
intercambiabile fra shell (in `cmd.exe` `set X="v"` mette le virgolette *dentro* al
valore).

### 1.2 Ambiente A — locale, da zero

Il `data/` che hai adesso sul disco è di una milestone vecchia: non ha dipendenti,
mezzi, pozzetti, pagamenti né i workflow `toolsmith`/`diagnostico`. **Non
sovrascriverlo** — semina un repo dati nuovo accanto:

PowerShell:

```bash
$env:DATA_DIR = "./data-test"; $env:JWT_SECRET = "una-stringa-lunga-almeno-32-caratteri"; $env:LLM_T1_MODEL = "gpt-5.5"; $env:LLM_T2_MODEL = "gpt-5.4"; $env:OPENAI_API_KEY = "sk-..."; $env:LOG_LEVEL = "INFO"
```

poi, nella **stessa** finestra:

```bash
make demo
```

```bash
make dev
```

Per provare anche la contabilità (sezione K), aggiungi **prima** di `make dev`, sempre
nella stessa finestra — nota `localhost`, non `host.docker.internal`, perché qui
l'app gira sull'host:

```bash
$env:ERP_BASE_URL = "http://localhost:8080"; $env:ERP_API_KEY = "..."; $env:ERP_API_SECRET = "..."; $env:ERP_COMPANY = "Aitho Costruzioni"; $env:ERP_CONTO_RITENUTA = "Ritenute - AC"; $env:ERP_CONTO_IVA = "IVA 22% - AC"; $env:ERP_ITEM_DDT = "WF-MATERIALE-CANTIERE"
```

### 1.3 Ambiente B — Docker

```bash
docker compose up -d
```

```bash
docker compose -f docker-compose.erpnext.yml up -d
```

Le `ERP_*` devono stare nel `.env` con `ERP_BASE_URL=http://host.docker.internal:8080`
(dentro al container `localhost` è il container stesso). Se mancano, l'integrazione
è **spenta in silenzio** e tutta la sezione K non è eseguibile.

### 1.4 Utenti

| Utente | Codice | Ruolo | Cantiere |
|---|---|---|---|
| `salvo` | `1111` | operatore | Residenza Le Palme (CNT-001) |
| `giuseppe` | `2222` | operatore | Scuola Manzoni (CNT-002) |
| `marco` | `3333` | operatore | Capannone Etna Sud (CNT-003) |
| `giovanna` | `9999` | **ufficio (admin)** | tutti |

ERPNext: <http://localhost:8080/app> — `Administrator` / `admin`. La scrivania è
`/app`; la radice `/` è il portale fornitori e nega i documenti con **403**.

### 1.5 Baseline attesa dopo il seed

3 cantieri · 8 fornitori · 4 dipendenti · 2 computi · **5 fatture** · 2 DDT · 2 SAL ·
2 rapportini · 3 materiali · 3 mezzi · 2 manutenzioni · 3 lavorazioni · 4 scadenze ·
3 pozzetti · 1 cronoprogramma · 0 documenti caricati · 0 segnalazioni · 0 patch.

Riferimenti ricorrenti in questo test-book:

- **FT-2026-0004** — parcella FRN-007 su CNT-001, imponibile 4.000, IVA 880,
  totale 4.880, **ritenuta 800** (netto 4.080). È lo scenario M5.
- **fattura-studio-bianchi.pdf** — lo stesso fornitore e gli stessi importi in PDF
  (numero 15/2026 dell'08/07/2026), da caricare a mano.
- Il **golden set** del seed contiene **2 casi**, le due fatture *senza* ritenuta: la
  terza è esclusa di proposito, è ciò che l'Improver deve imparare.
- Budget: CNT-001 1.850.000 € · CNT-002 640.000 € · CNT-003 2.300.000 €.
- Tariffe orarie: Salvo 28 €/h · Giuseppe 25 €/h · Marco 30 €/h.

### 1.6 Token per le prove via API (⌨)

```bash
curl -s -X POST http://localhost/api/auth/login -H "Content-Type: application/json" -d "{\"username\":\"giovanna\",\"pin\":\"9999\"}"
```

Copia il campo `token` e usalo come `-H "Authorization: Bearer <token>"`. In
ambiente A sostituisci `http://localhost` con `http://localhost:8000`.

---

## 2 · Pre-flight

Cinque minuti che evitano di scoprire a metà sessione che l'ambiente è muto.

**T0.1 ⭐ · L'app risponde**
`GET /api/health` → `{"status":"ok"}` e `/op` mostra la schermata di accesso.
`☐ OK ☐ KO`

**T0.2 ⭐ · Il repo dati è quello nuovo**
La cartella `entities/` contiene **17** sottocartelle (fra cui `dipendenti`,
`pozzetti`, `pagamenti`) e `workflows/` ne contiene **9** (fra cui `toolsmith` e
`diagnostico`). Se ne vedi 8 e 7, stai usando il repo dati vecchio: la metà dei casi
qui sotto non è eseguibile.
`☐ OK ☐ KO`

**T0.3 ⭐ 🔑 💶 · Il modello risponde**
Da Admin → **Interroga**, chiedi «Quante fatture ci sono?». Deve tornare SQL +
tabella. Se qui vedi un errore di modello (nome non valido, chiave scaduta,
quota), **tutte** le prove 🔑 falliranno a cascata: risolvi prima.
`☐ OK ☐ KO` — modello usato: ____________

**T0.4 🧾 · ERPNext è collegato**
`make erp-smoke ARGS=--full` → **4 `[PASS]`**. In alternativa, Admin →
**Contabilità** non deve dire «L'integrazione contabile non è configurata».
`☐ OK ☐ KO`

**T0.5 · La suite automatica è verde**
`make test`. Non è un test manuale, è la rete sotto: se è rossa, i KO che troverai
sotto sono probabilmente conseguenze, non cause.
`☐ OK ☐ KO` — esito: ____ passed, ____ failed

---

## 3 · A — Accesso, ruoli e permessi

**A1 ⭐ · Accesso operatore**
Apri `/op` → nome `salvo` → *Avanti* → codice `1111` → *Entra*.
**Atteso:** «Ciao Salvo 👷 · cantiere Residenza Le Palme» e quattro bottoni grandi
(Carica un documento / Le mie ore / I miei documenti / Chiedi qualcosa).
`☐ OK ☐ KO`

**A2 · Codice sbagliato**
Stesso giro con codice `0000`.
**Atteso:** «Nome o codice non giusti. Riprova.» — nessun dettaglio tecnico, nessun
codice HTTP a schermo.
`☐ OK ☐ KO`

**A3 ⭐ · Accesso ufficio**
Apri `/admin` → `giovanna` / `9999`.
**Atteso:** barra con 12 voci (Cruscotto, Dati, Scostamenti, Revisione,
Segnalazioni, Interroga, Workflows, Skills & Tools, Dataset, Contabilità, Log,
Diagnosi).
`☐ OK ☐ KO`

**A4 ⭐ · L'operatore non entra nell'ufficio**
Con la sessione di `salvo` attiva, apri `/admin`.
**Atteso:** «Questa è l'area dell'ufficio. Il tuo accesso è da operatore.» con il
link per tornare. Nessuna pagina admin visibile, nemmeno per un istante.
`☐ OK ☐ KO`

**A5 · Un operatore non vede i documenti di un altro**
Con `salvo` carica un documento (vedi B1). Esci, entra come `giuseppe`, apri *I miei
documenti*.
**Atteso:** il documento di Salvo **non** compare.
`☐ OK ☐ KO`

**A6 ⌨ · Nessun token = 401**
`curl http://localhost/api/dashboard/costs` senza header.
**Atteso:** `401`, corpo `{"detail":"accesso richiesto"}`.
`☐ OK ☐ KO`

**A7 ⌨ · Token operatore su rotta d'ufficio = 403**
Fai login come `salvo` via API, poi chiama `/api/dashboard/costs` con quel token.
**Atteso:** `403`, «operazione riservata all'ufficio (admin)».
`☐ OK ☐ KO`

**A8 ⌨ · Cantiere non assegnato**
Come `salvo`, `POST /api/documents` con `cantiere_id=CNT-003`.
**Atteso:** `403`, «cantiere non assegnato all'utente».
`☐ OK ☐ KO`

**A9 · Uscita**
Tocca *esci* in entrambe le interfacce.
**Atteso:** si torna alla schermata di accesso; ricaricando la pagina non si rientra
da soli.
`☐ OK ☐ KO`

---

## 4 · B — Operatore: caricamento e ciclo del documento

Tutti i casi di questa sezione sono 🔑💶: ogni caricamento è una chiamata al modello.

**B0 · Scarica i documenti di esempio**
`/op` → *Carica un documento* → in fondo, «Non hai un documento? Scarica un esempio».
**Atteso:** **6** esempi (3 fatture, 1 DDT, 1 SAL, 1 rapportino); il download parte e
il PDF si apre.
`☐ OK ☐ KO`

**B1 ⭐ 🔑 💶 · Fattura: caricamento ed estrazione**
Come `salvo`, carica `fattura-calcestruzzi-etna.pdf`.
**Atteso:** «Sto leggendo il documento…», poi «Ho letto: fattura!» con un riepilogo
in italiano semplice (fornitore, numero, data, imponibile, IVA, totale). Nessun
termine tecnico, nessun JSON, nessuna confidence a schermo.
`☐ OK ☐ KO`

**B2 ⭐ 🔑 💶 · Il classificatore instrada da solo**
Carica `ddt-edil-sud.pdf`, `sal-capannone-etna.pdf`, `rapportino-le-palme.pdf`.
**Atteso:** il riepilogo dice rispettivamente «bolla/ddt», «stato avanzamento»,
«rapportino» — tre tipi diversi senza che tu abbia scelto niente.
`☐ OK ☐ KO`

**B3 ⭐ 🔑 💶 · La ritenuta non c'è (è previsto)**
Carica `fattura-studio-bianchi.pdf`.
**Atteso:** il riepilogo riporta imponibile 4.000, IVA 880, totale 4.880 e **non**
la ritenuta di 800: la v1.0 del workflow non la conosce. Serve per la sezione H.
`☐ OK ☐ KO`

**B4 ⭐ · Conferma**
Sul riepilogo, tocca *👍 Sì*.
**Atteso:** «🤝 Grazie! Ci pensiamo noi.» La conferma **non** valida il dato: in
Revisione (D1) il documento resta una bozza da controllare.
`☐ OK ☐ KO`

**B5 ⭐ · Segnalazione in un tocco**
Su un altro documento, *👎 Qualcosa non torna* → scrivi «manca la ritenuta
d'acconto» → *Invia*.
**Atteso:** «🤝 Grazie! Ci pensiamo noi.» e la segnalazione compare in Admin →
**Segnalazioni** (H1).
`☐ OK ☐ KO`

**B6 · Segnalazione vuota**
Prova a inviare una segnalazione senza testo.
**Atteso:** non parte; nessun errore tecnico.
`☐ OK ☐ KO`

**B7 ⭐ · Elenco a semaforo**
*I miei documenti*.
**Atteso:** un documento per riga con 🟢/🟡/🔴, titolo, quando («oggi», «ieri», il
giorno della settimana) e una frase di stato. 🟢 «Tutto a posto.» · 🟡 «Lo sto
ancora leggendo…» / «In lavorazione: la controlla l'ufficio.» / «Segnalazione
inviata: ci pensa l'ufficio.» · 🔴 «Serve una mano: se ne occupa l'ufficio, ti
avvisiamo noi.»
`☐ OK ☐ KO`

**B8 · Dettaglio del documento**
Tocca una riga.
**Atteso:** lo stesso riepilogo leggibile del caricamento, con conferma/segnalazione
se non ancora date.
`☐ OK ☐ KO`

**B9 · Formato che il sistema non sa leggere**
Carica un `.zip`, un `.docx` o un `.txt` (i formati letti sono solo `.pdf`, `.png`,
`.jpg`, `.jpeg`).
**Atteso:** semaforo 🔴 con «Serve una mano: se ne occupa l'ufficio», e una
segnalazione automatica in Admin → Segnalazioni. **Nessun crash, nessun 500.**
`☐ OK ☐ KO`

**B10 · File troppo pesante**
Carica un file oltre il limite (**>15 MB**).
**Atteso:** «Il file è troppo pesante. Prova con una foto del documento.»
`☐ OK ☐ KO`

**B11 · File vuoto**
Carica un file da 0 byte.
**Atteso:** «Il file sembra vuoto. Riprova a fotografare il documento.»
`☐ OK ☐ KO`

**B12 · Foto invece di PDF** 🔑 💶
Fotografa con il telefono una delle fatture stampate (o fai uno screenshot JPG del
PDF) e caricala.
**Atteso:** viene letta come il PDF. Se la lettura è peggiore, annota **quali campi**
sbaglia: è un dato utile, non un KO automatico.
`☐ OK ☐ KO` — campi sbagliati: ______________________

**B13 · Si può uscire durante la lettura**
Carica un documento e torna subito alla home senza aspettare.
**Atteso:** «Puoi anche uscire: lo trovi tra poco in "I miei documenti"» — e infatti
dopo qualche secondo è lì, con l'esito giusto.
`☐ OK ☐ KO`

**B14 · Scelta del cantiere con più cantieri**
Solo se hai un utente con più di un cantiere (o come admin da API).
**Atteso:** prima del caricamento compare «Di quale cantiere è?»; con un solo
cantiere la domanda **non** compare (viene scelto da solo).
`☐ OK ☐ KO ☐ N/A`

**B15 · Nessun termine tecnico**
Rileggi tutte le schermate operatore toccate finora.
**Atteso:** zero occorrenze di «workflow», «LLM», «entità», «confidence», «bozza»,
«JSON», «run», «schema», codici HTTP o id tecnici.
`☐ OK ☐ KO` — termini trovati: ______________________

---

## 5 · C — Operatore: ore e domande

**C1 ⭐ · Consuntivo ore, giro completo**
`/op` → *Le mie ore* → giorno *Oggi* → cantiere → ore → attività (o *Salta*) →
*Invia le ore*.
**Atteso:** «🤝 Grazie! Ho segnato le tue ore.» Una domanda alla volta, nessun form
compilato.
`☐ OK ☐ KO`

**C2 · Le ore arrivano in revisione**
Admin → **Revisione**.
**Atteso:** un rapportino **bozza** con quelle ore, cantiere e dipendente giusti. Le
ore dell'operaio non si auto-validano.
`☐ OK ☐ KO`

**C3 · Cantiere dove non risulti allocato** ⌨
`POST /api/consuntivo` come `salvo` con `cantiere_id=CNT-002`.
**Atteso:** `403`, «non risulti allocato a questo cantiere in questa data».
`☐ OK ☐ KO`

**C4 · Ore non valide** ⌨
Stesso endpoint con `ore: 0` o negative.
**Atteso:** `400`, «le ore devono essere maggiori di zero».
`☐ OK ☐ KO`

**C5 · Utente non collegato a un dipendente**
Con un utente senza scheda dipendente (crearlo da Admin → Dati → Utenti non è
previsto: salta se non applicabile).
**Atteso:** «Non risulti tra i dipendenti. Parlane con l'ufficio.»
`☐ OK ☐ KO ☐ N/A`

**C6 ⭐ 🔑 💶 · Chiedi qualcosa (operatore)**
*Chiedi qualcosa* → «Quanto abbiamo speso in questo cantiere?».
**Atteso:** una risposta in italiano sui **propri** cantieri. Non deve comparire SQL
(quello è roba d'ufficio) né dati di cantieri non assegnati.
`☐ OK ☐ KO`

**C7 · La domanda non risponde**
Fai una domanda senza senso («ciao come stai»).
**Atteso:** una frase gentile («Non riesco a rispondere adesso…») e nessuna traccia
tecnica.
`☐ OK ☐ KO`

---

## 6 · D — Ufficio: revisione e validazione

**D1 ⭐ · La coda di revisione**
Admin → **Revisione**.
**Atteso:** una riga per bozza con documento, fornitore, cantiere, data, totale e
**confidenza**. Con tutto validato: «Niente da rivedere: tutte le bozze sono
validate.»
`☐ OK ☐ KO`

**D2 ⭐ · Dettaglio: originale a fianco dei campi**
Apri una bozza.
**Atteso:** a sinistra il **PDF originale** in anteprima, a destra i campi estratti
con un badge di confidenza per campo (verde ≥90%, giallo ≥75%, rosso sotto) e la
tabella delle righe.
`☐ OK ☐ KO`

**D3 ⭐ · Valida**
*Salva come validato*.
**Atteso:** il badge passa da «bozza» a «validato · giovanna»; la riga sparisce dalla
coda; il caso entra nel **golden set** (verificabile in `golden/GOLD-*.json`). Se
l'ERP è collegato, parte anche la sincronizzazione (K2).
`☐ OK ☐ KO`

**D4 · Doppia validazione**
Rivalida lo stesso documento (ricarica e riprova via API).
**Atteso:** nessun doppione, nessun errore: risponde `gia_validato`.
`☐ OK ☐ KO`

**D5 ⭐ · Nota su un campo**
Su un campo, *+ nota* → «l'IVA è al 10%, non al 22%» → *ok*.
**Atteso:** la nota compare accanto al campo con 💬 e resta dopo il ricaricamento.
`☐ OK ☐ KO`

**D6 ⭐ · Correggi i dati a mano**
*Modifica dati* → cambia un importo → *Salva modifiche*.
**Atteso:** il valore cambia; se violi lo schema (es. testo in un campo numerico) il
salvataggio è rifiutato con un messaggio comprensibile, non con un traceback.
`☐ OK ☐ KO`

**D7 ⭐ · Collega al computo**
Su una **fattura** non ancora validata di un cantiere che ha un computo (CNT-001 o
CNT-002), *Collega al computo*.
**Atteso:** «Collegate N righe su M alle voci di computo». Su un cantiere senza
computo: «Nessun computo per questo cantiere…». Dopo la validazione, la spesa risale
in **Scostamenti** (E6).
`☐ OK ☐ KO`

**D8 ⭐ · Anagrafica mancante: creala dal documento**
Serve un documento il cui fornitore **non** è in anagrafica. Due modi:

- *non distruttivo (preferito):* carica un documento — anche la **foto** di una
  fattura vera o scritta a mano — di un fornitore che non è fra gli 8 del seed;
- *deterministico con le fixture:* elimina prima **FT-2026-0004**, poi **FRN-007**
  (Studio Tecnico Ing. Bianchi), poi carica `fattura-studio-bianchi.pdf`. In
  quest'ordine: un fornitore ancora referenziato non si può eliminare (F7b).
  ⚠️ Così azzeri la ritenuta di baseline — esegui **prima** E4 e G2.

**Atteso:** in revisione compare il riquadro **«Riferimenti da completare»** con
badge *Manca*, il valore letto dal documento («letto dal documento: …») e due
bottoni: *Crea Fornitore dal documento* (form precompilato con ragione sociale e
partita IVA) e *Collega esistente*. Alla creazione, il riferimento si risolve e il
riquadro sparisce.
`☐ OK ☐ KO`

**D9 · Collega un'anagrafica esistente**
Stesso riquadro, *Collega esistente* → scegli dall'elenco → *Collega*.
**Atteso:** il riferimento si popola, nessuna anagrafica nuova creata.
`☐ OK ☐ KO`

**D10 · Segnalazione visibile in revisione**
Apri la bozza di un documento su cui l'operatore ha segnalato (B5).
**Atteso:** banner ambra «Segnalazione aperta: …» con il testo dell'operatore e il
link alle Segnalazioni.
`☐ OK ☐ KO`

**D11 · Mostra dati grezzi**
*Mostra dati*.
**Atteso:** il JSON dell'entità, leggibile, e *Nascondi dati* lo richiude. È l'unica
finestra tecnica ammessa, ed è nell'area d'ufficio.
`☐ OK ☐ KO`

**D12 · Trace del run**
Admin → **Segnalazioni** → su una segnalazione, *Mostra trace*. (È l'**unico** punto
dell'interfaccia da cui si apre un trace: da Revisione il `run_id` viene passato solo
all'Improver.)
**Atteso:** input, prompt, tool call, esito, **costo** e **latenza** della singola
esecuzione.
`☐ OK ☐ KO`

---

## 7 · E — Ufficio: controllo costi, registro e scostamenti

**E1 ⭐ · Cruscotto**
Admin → **Cruscotto**.
**Atteso:** KPI in alto — Speso (fatture), Totale IVA, Ritenute d'acconto, Ore
manodopera, Costo manodopera, Costo mezzi/noli, Avanzamento (SAL), Scostamento
computo. Con la sola baseline del seed i numeri sono stabili: rieseguendo la pagina
non cambiano.
`☐ OK ☐ KO`

**E2 ⭐ · Costi per cantiere**
Tabella «Costi per cantiere».
**Atteso:** i 3 cantieri con speso, budget e **consumo %**. CNT-001 su 1.850.000 €,
CNT-002 su 640.000 €, CNT-003 su 2.300.000 €. Le percentuali sono coerenti con
speso/budget.
`☐ OK ☐ KO`

**E3 · Fornitori principali**
**Atteso:** classifica per speso, con numero di fatture per fornitore.
`☐ OK ☐ KO`

**E4 ⭐ · Ritenute d'acconto**
**Atteso:** il KPI vale **800 €** sulla baseline (la sola FT-2026-0004). Se hai
validato anche la fattura Bianchi caricata a mano dopo il miglioramento (H6),
diventa 1.600 €.
`☐ OK ☐ KO` — valore letto: __________

**E5 ⭐ · Registro di cantiere**
Clicca il nome di un cantiere nel Cruscotto.
**Atteso:** il fascicolo — anagrafica, fatture, DDT, ore, SAL, avanzamento — con i
vuoti dichiarati («Nessuna fattura su questo cantiere», «Nessun DDT», «Nessuno stato
avanzamento») invece di tabelle vuote.
`☐ OK ☐ KO`

**E6 ⭐ · Scostamenti**
Admin → **Scostamenti**.
**Atteso:** per ogni cantiere con computo, le voci con Previsto / Speso / Consumo, e
le **voci sopra soglia** evidenziate. Dopo D7 la spesa collegata compare sulla voce
giusta.
`☐ OK ☐ KO`

**E7 · Cantiere senza computo**
Apri gli scostamenti di CNT-003.
**Atteso:** «Questo cantiere non ha voci di computo.» — non una tabella vuota né un
errore.
`☐ OK ☐ KO`

**E8 ⭐ · Report Excel completo**
Cruscotto → scarica il report mensile.
**Atteso:** un `.xlsx` che si apre, con i fogli **Riepilogo, Fatture, DDT, Ore, SAL,
Scostamento**; i totali coincidono con quelli a schermo.
`☐ OK ☐ KO`

**E9 · Report Excel di un solo cantiere**
Dalla pagina del cantiere, scarica il report.
**Atteso:** stessi fogli, filtrati su quel cantiere.
`☐ OK ☐ KO`

**E10 · Scorciatoie di creazione**
Dal Cruscotto: *+ Cantiere*, *+ Fornitore*, *+ Fattura a mano*.
**Atteso:** portano al form giusto in Dati, già sul tipo corretto.
`☐ OK ☐ KO`

---

## 8 · F — Ufficio: anagrafiche e dati (CRUD generico)

La regola del progetto è che un'entità nuova è *dato, non codice*. Qui si verifica
che il CRUD sia davvero generico su **tutti** i tipi.

**F1 ⭐ · Elenco dei tipi**
Admin → **Dati**.
**Atteso:** due gruppi, **16 tipi** in tutto.
**Anagrafiche** (12): cantiere, fornitore, dipendente, computo, materiale, mezzo,
manutenzione, lavorazione, scadenza, pozzetto, cronoprogramma, pagamento.
**Documenti gestionali** (4): fattura, DDT, SAL, rapportino.
Il tipo di sistema `documento` **non** deve comparire: nasce e vive nel flusso di
caricamento (`GET /api/entities/documento` → `404`, «tipo non gestibile a mano»).
`☐ OK ☐ KO`

**F2 ⭐ · Il form nasce dallo schema**
Apri *Nuovo* su tre tipi diversi (es. materiale, mezzo, scadenza).
**Atteso:** i campi, i tipi (numero, data, elenco), gli obbligatori e i menù dei
**riferimenti** (es. cantiere) sono quelli dello schema JSON, senza che nessuno abbia
scritto un form a mano.
`☐ OK ☐ KO`

**F3 ⭐ · Crea**
Crea un materiale nuovo.
**Atteso:** id assegnato secondo il formato del tipo (`MAT-004`), l'entità compare in
elenco, e nel repo dati c'è **un commit git** con quella creazione.
`☐ OK ☐ KO`

**F4 · Modifica**
Cambia un campo e salva.
**Atteso:** valore aggiornato + nuovo commit.
`☐ OK ☐ KO`

**F5 · Validazione dello schema**
Metti testo in un campo numerico, o lascia vuoto un obbligatorio.
**Atteso:** messaggio d'errore che dice **quale** campo e **perché**; nessun
salvataggio parziale.
`☐ OK ☐ KO`

**F6 · Cancella**
Elimina l'entità creata in F3.
**Atteso:** conferma esplicita prima; poi sparisce; commit git.
`☐ OK ☐ KO`

**F7 · Riferimento inesistente** ⌨
`POST /api/entities/fattura` con `cantiere_id: "CNT-999"`.
**Atteso:** `422` con un messaggio che nomina il riferimento mancante.
`☐ OK ☐ KO`

**F7b ⭐ · Non si cancella ciò che è ancora usato**
Prova a eliminare **FRN-001** (usato da FT-2026-0001).
**Atteso:** `409` — «Fornitore FRN-001 è ancora usato da N documenti (…): rimuovi o
sposta prima i collegamenti.» L'elenco dei documenti è mostrato (max 8, poi «…»).
`☐ OK ☐ KO`

**F8 · Id malformato** ⌨
`GET /api/entities/fattura/../../etc/passwd`.
**Atteso:** `400`/`404`, **mai** un file fuori dal repo dati.
`☐ OK ☐ KO`

**F9 · Registri automatici**
Apri i pozzetti (3 dal seed) e il cronoprogramma (1).
**Atteso:** i pozzetti hanno uno **stato**; il cronoprogramma mostra pianificato vs
consuntivo, allineato all'ultimo SAL.
`☐ OK ☐ KO`

---

## 9 · G — Ufficio: interrogazione in linguaggio naturale

Tutti 🔑💶.

**G1 ⭐ 🔑 💶 · Domanda semplice**
Admin → **Interroga** → «Quanto abbiamo speso per ogni cantiere?».
**Atteso:** l'**SQL generato** in chiaro + la tabella dei risultati.
`☐ OK ☐ KO`

**G2 ⭐ 🔑 💶 · La domanda della demo**
«Quali fatture hanno una ritenuta d'acconto?».
**Atteso:** sulla baseline, una riga: **FT-2026-0004**, ritenuta 800.
`☐ OK ☐ KO`

**G3 🔑 💶 · Domanda su ore e manodopera**
«Quante ore sono state fatte per cantiere questo mese?».
**Atteso:** tabella coerente con il Cruscotto (E1).
`☐ OK ☐ KO`

**G4 ⭐ · Guardrail: solo lettura**
«Cancella tutte le fatture» (o una domanda che induca una `DELETE`).
**Atteso:** rifiuto esplicito — «sono ammesse solo query di lettura (SELECT)» o
«parola non ammessa: …». **Nessuna** riga toccata: riverifica il conteggio fatture
dopo.
`☐ OK ☐ KO`

**G5 · Guardrail: una query per volta**
Induci due statement separati da `;`.
**Atteso:** «è ammessa una sola query per volta».
`☐ OK ☐ KO`

**G6 · Guardrail: LIMIT forzato**
Una domanda che restituirebbe tutto.
**Atteso:** l'SQL mostrato contiene un `LIMIT` (max 1000) anche se non l'hai chiesto.
`☐ OK ☐ KO`

**G7 · Nessun risultato**
Una domanda con risposta vuota («fatture del 2019»).
**Atteso:** «Nessun risultato.» — non un errore.
`☐ OK ☐ KO`

**G8 · Le query si accumulano**
Ripeti **due volte** la stessa domanda, poi vai in **Skills & Tools**.
**Atteso:** la domanda compare fra le «Query ricorrenti» con badge `×2`. Serve per la
sezione I.
`☐ OK ☐ KO`

---

## 10 · H — Segnalazioni e auto-miglioramento (Improver)

⚠️ Ambiente A consigliato: con golden set vuoto il replay non dimostra niente.
Se sei in B, esegui prima D3 su almeno due documenti.

**H1 ⭐ · La segnalazione arriva**
Admin → **Segnalazioni**, dopo B5.
**Atteso:** la nota dell'operatore con documento, autore, data, e il bottone
*Migliora il workflow*. Le segnalazioni automatiche (B9) sono nello stesso elenco.
`☐ OK ☐ KO`

**H2 · Chiudi una segnalazione**
Chiudi una segnalazione a mano.
**Atteso:** sparisce dalle aperte, resta nello storico.
`☐ OK ☐ KO`

**H3 ⭐ 🔑 💶 · L'Improver propone una patch**
Da una segnalazione, *Migliora il workflow*, poi vai in **Workflows**.
**Atteso:** una **patch** in attesa con: motivo, analisi, **diff colorato** della
skill/manifest, e l'esito del **replay sul golden set** senza regressioni — in
ambiente A, sulla baseline, **`2/2`**.
`☐ OK ☐ KO` — replay: ____ / ____

**H4 ⭐ · Approva e applica**
*Approva e applica*.
**Atteso:** il workflow passa da **v1.0 a v1.1** (versione visibile in Workflows) e il
**documento d'origine viene rielaborato** in automatico.
`☐ OK ☐ KO`

**H5 ⭐ · La correzione si vede**
Torna in **Revisione** e apri la bozza rielaborata di `fattura-studio-bianchi.pdf`.
**Atteso:** ora c'è `ritenuta_acconto = 800`. È la *definition of done* del prodotto.
`☐ OK ☐ KO`

**H6 · La validazione la rende una regressione**
Valida quella bozza.
**Atteso:** entra nel golden set; il replay della patch successiva la include.
`☐ OK ☐ KO`

**H7 · Rifiuta una patch**
Chiedi un secondo miglioramento e questa volta *Rifiuta*.
**Atteso:** la patch resta come rifiutata, la versione del workflow **non** cambia,
nessun documento rielaborato.
`☐ OK ☐ KO`

**H8 ⭐ 🔑 💶 · Detta una regola in italiano**
Da **Revisione** (riquadro «Migliora il workflow») o da **Workflows**, scrivi una
regola: «individua il fornitore dalla partita IVA, non dalla ragione sociale».
**Atteso:** diventa una proposta di patch con lo **stesso** replay sul golden set. Le
note sui campi (D5) del documento sono incluse in automatico.
`☐ OK ☐ KO`

**H9 · Il replay protegge dalle regressioni**
Chiedi un miglioramento palesemente dannoso («non estrarre più il totale»).
**Atteso:** il replay segnala le regressioni (`N-k/N`) e lo dice **prima**
dell'approvazione. La patch è approvabile lo stesso — è una decisione umana — ma il
rischio è dichiarato.
`☐ OK ☐ KO`

**H10 · Statistiche dei run**
In **Workflows**, guarda i contatori per workflow.
**Atteso:** numero di run, esiti e versione corrente per ogni workflow. (Il trace del
singolo run si apre da Segnalazioni — vedi D12.)
`☐ OK ☐ KO`

**H11 ⭐ · L'operatore non approva mai**
Cerca, nell'interfaccia operatore, qualunque modo di approvare una patch.
**Atteso:** non esiste. L'operatore segnala, l'ufficio decide.
`☐ OK ☐ KO`

---

## 11 · I — Consolidamento: viste, tool parametrici, Toolsmith

**I1 ⭐ · I candidati compaiono**
Admin → **Skills & Tools**, dopo G8.
**Atteso:** in «Query ricorrenti — candidate al consolidamento», la tua domanda con
`×2` e i bottoni *Crea vista* / *Crea tool*.
`☐ OK ☐ KO`

**I2 ⭐ · Crea una vista**
*Crea vista* → nome `spesa_mensile` → conferma.
**Atteso:** nasce `v_spesa_mensile` in «Viste consolidate», con data e autore; il
candidato si marca `✓`. È un **commit git** in `config/views.sql`.
`☐ OK ☐ KO`

**I3 · La vista è interrogabile**
In **Interroga**, chiedi qualcosa che la usi (o cita il nome della vista).
**Atteso:** risponde senza rigenerare la query originale; numeri identici a prima.
`☐ OK ☐ KO`

**I4 ⭐ · Crea un tool parametrico**
Su una query ricorrente con un valore variabile (es. il nome di un cantiere), *Crea
tool* → nome → assegna un nome al parametro (`cantiere`) → conferma.
**Atteso:** nasce `t_<nome>(cantiere)` in «Tool parametrici (macro)».
`☐ OK ☐ KO`

**I5 · Tool senza parametri**
Prova *Crea tool* su una query senza letterali.
**Atteso:** «Nessun valore da parametrizzare in questa query: conviene "Crea
vista".» — e il bottone di creazione resta disabilitato.
`☐ OK ☐ KO`

**I6 · Rimozione reversibile**
*Rimuovi* su una vista e su un tool, con conferma *Sì, rimuovi*.
**Atteso:** spariscono, la query torna fra le ricorrenti, ogni rimozione è un commit
git reversibile.
`☐ OK ☐ KO`

**I7 · Registry dei tool nativi**
Card «Tool nativi (Python)».
**Atteso:** elenco delle funzioni deterministiche di sistema con descrizione,
**contatore d'uso** e badge di ciclo di vita.
`☐ OK ☐ KO`

**I8 ⌨ 🔑 💶 · Toolsmith: candidati**
Non c'è interfaccia. `GET /api/toolsmith/candidati` con token admin.
**Atteso:** i campi corretti in modo ricorrente (il delta fra bozza estratta e dato
validato). Serve aver validato più documenti con correzioni ripetute — la ritenuta
d'acconto è l'esempio guida.
`☐ OK ☐ KO`

**I9 ⌨ 🔑 💶 · Toolsmith: proponi**
`POST /api/toolsmith/proponi` con `{nome, tipo, campi_input, campo_output, workflow}`.
**Atteso:** una proposta con **codice Python**, schema, e **test generati dai trace
storici**, eseguiti in **sandbox**.
`☐ OK ☐ KO`

**I10 ⌨ · Toolsmith: approva**
`GET /api/toolsmith/proposte`, poi `POST /api/toolsmith/proposte/{id}/approve`.
**Atteso:** il tool è registrato in `data/tools/<nome>/` (dato versionato), la skill è
patchata per chiamarlo, e l'LLM resta come **fallback**. Il codice **non** viene mai
importato nel processo.
`☐ OK ☐ KO`

**I11 ⌨ · Toolsmith: rifiuta**
`POST /api/toolsmith/proposte/{id}/reject`.
**Atteso:** nessun tool registrato, nessuna skill toccata.
`☐ OK ☐ KO`

> **Nota da riportare.** Il README annuncia «Skills & Tools → Candidati Python» e
> «Dataset → Idoneità T3» come pagine dell'interfaccia. **Non esistono**: sono solo
> API. Non è un guasto del backend, è un buco di interfaccia — segnalalo come tale.

---

## 12 · J — Dataset, costi e tier locale

**J1 ⭐ · Costo per documento**
Admin → **Dataset**.
**Atteso:** costo LLM totale, costo per documento, totale documenti, tool call
registrate, esempi di fine-tuning. Con `LLM_T1/T2` a modelli veri i costi sono >0 e
credibili.
`☐ OK ☐ KO`

**J2 · Export delle tool call**
*Esporta toolcalls.jsonl*.
**Atteso:** un `.jsonl` che si apre, una riga per tool call.
`☐ OK ☐ KO`

**J3 · Export per il fine-tuning**
Skills & Tools → *⬇ Scarica finetuning.jsonl*.
**Atteso:** contiene **solo** gli esempi dei documenti validati dall'ufficio; il
conteggio coincide con il KPI «Esempi fine-tuning». Con 0 esempi il bottone è
disabilitato.
`☐ OK ☐ KO`

**J4 · Query ricorrenti nel Dataset**
Card «Query ricorrenti».
**Atteso:** le domande poste a Interroga con quante volte; con nessuna: «Nessuna
query registrata: prova la pagina Interroga.»
`☐ OK ☐ KO`

**J5 ⌨ 🔑 💶 · Idoneità T3**
Nessuna interfaccia. `GET /api/dataset/eval-t3?candidato=T3&riferimento=T1` con
`LLM_T3_MODEL` impostato su un modello locale.
**Atteso:** accuratezza del candidato contro T1 sugli esempi validati, e quali
workflow sono «pronti per T3». Senza `LLM_T3_MODEL`, salta.
`☐ OK ☐ KO ☐ N/A`

**J6 · Escalation T3→T1**
Solo con T3 attivo: carica un documento che il modello locale sbaglia.
**Atteso:** lo step escala a T1 e l'escalation è tracciata nel trace/logbook.
`☐ OK ☐ KO ☐ N/A`

---

## 13 · K — Contabilità: integrazione ERPNext 🧾

Il piano dettagliato (test automatici + smoke + triage) è in
[`docs/erp-test-plan.md`](erp-test-plan.md). Qui c'è solo la parte **manuale**.

**K1 ⭐ 🧾 · La pagina Contabilità**
Admin → **Contabilità**.
**Atteso:** contatori per tipo (validate / sincronizzate / da sincronizzare),
l'elenco dei rimasti indietro, il registro dei tentativi. Lessico d'ufficio
(«arrivato in contabilità»), non `erp_id`.
`☐ OK ☐ KO`

**K2 ⭐ 🧾 · Validare sincronizza**
Valida una fattura in Revisione (D3), poi apri
<http://localhost:8080/app/purchase-invoice>.
**Atteso:** la Purchase Invoice c'è, con fornitore e **cost center = il cantiere**
sulle righe. In Contabilità il contatore «sincronizzate» sale di 1.
`☐ OK ☐ KO`

**K3 ⭐ 🧾 · La ritenuta d'acconto a valle**
Valida una fattura con ritenuta (la Bianchi di H5/H6) e aprila in ERPNext.
**Atteso:** una riga **Deduct** «Ritenuta d'acconto» da **800,00** esatti; netto
**4.080** su 4.880.
`☐ OK ☐ KO`

**K4 🧾 · DDT → Purchase Receipt**
Valida un DDT.
**Atteso:** una Purchase Receipt in `/app/purchase-receipt`, con le quantità e
**senza importi**, riga sull'articolo generico non di magazzino.
`☐ OK ☐ KO`

**K5 ⭐ 🧾 · Idempotenza**
Rivalida (o ri-sincronizza) lo stesso documento.
**Atteso:** **nessun doppione** a valle: il documento ha già `erp_id` e non viene
reinviato.
`☐ OK ☐ KO`

**K6 · Fornitore non duplicato**
Valida due fatture dello stesso fornitore.
**Atteso:** un solo Supplier in ERPNext (riuso per partita IVA).
`☐ OK ☐ KO`

**K7 ⭐ 🧾 · ERP giù non blocca la validazione**
`make erp-down`, poi valida una fattura.
**Atteso:** il documento **è validato lo stesso**; compare una **segnalazione
automatica** e una riga `errore` nel registro dei tentativi. L'ufficio non si accorge
di un guasto a valle se non guardando la pagina Contabilità.
`☐ OK ☐ KO`

**K8 ⭐ 🧾 · Recupero degli arretrati**
`make erp-up`, aspetta che risponda, poi Contabilità → *Re-invia gli arretrati*.
**Atteso:** i documenti rimasti indietro passano a sincronizzati; il registro mostra
`ok`. Con niente da fare: «Non c'era nulla da re-inviare.»
`☐ OK ☐ KO`

**K9 · Riprova singola**
Su un documento in elenco, *Riprova*.
**Atteso:** sincronizza quel solo documento.
`☐ OK ☐ KO`

**K10 ⭐ 🧾 · Read-back dei pagamenti**
Segna una Purchase Invoice come pagata in ERPNext, poi Contabilità → *Rileggi i
pagamenti*.
**Atteso:** nasce/si aggiorna un'entità **pagamento** con stato `pagato` e importo;
visibile in Dati → Pagamento e nella vista `v_pagamenti`. Rieseguendolo: 0 creati,
N aggiornati (nessun doppione).
`☐ OK ☐ KO`

**K11 · Tipo non sincronizzabile**
Valida un **SAL**.
**Atteso:** nessun effetto sull'ERP, nessun errore, nessuna riga di registro.
`☐ OK ☐ KO`

**K12 · Integrazione spenta**
Ferma l'app, togli le `ERP_*`, riavvia. Apri Contabilità.
**Atteso:** «L'integrazione contabile non è configurata.», nessuna azione offerta, lo
storico resta visibile. Validare funziona esattamente come prima.
`☐ OK ☐ KO`

**K13 · Il registro dei tentativi**
Card «Registro dei tentativi».
**Atteso:** quando, documento, esito, e per i fallimenti **il motivo** — leggibile,
non un traceback. Corrisponde a `data/dataset/erp_sync.jsonl`.
`☐ OK ☐ KO`

**K14 · La scrivania, non il portale**
Apri <http://localhost:8080/purchase-invoices/ACC-PINV-2026-00001> (senza `/app`).
**Atteso:** **403 «Non Consentito»** — è il portale fornitori. Le fatture si guardano
in `/app/purchase-invoice`. Serve a riconoscere l'errore quando ricapita.
`☐ OK ☐ KO`

---

## 14 · L — Log e diagnosi

**L1 ⭐ · La pagina Log**
Admin → **Log**.
**Atteso:** conteggi per livello, elenco degli eventi di tutte le fasi (api, dal,
gateway, runtime, tool, sandbox, improver, erp), **errori in evidenza**.
`☐ OK ☐ KO`

**L2 ⭐ · Filtri**
Filtra per livello minimo `ERROR`, per fase `erp`, per testo, per periodo.
**Atteso:** i filtri si combinano; con nessun risultato: «Nessun evento per questi
filtri.»
`☐ OK ☐ KO`

**L3 ⭐ · Livello a runtime**
Cambia il livello attivo da `INFO` a `DEBUG`, genera traffico, torna a `INFO`.
**Atteso:** l'effetto è **immediato** senza riavviare, e la scelta **sopravvive al
riavvio** (è in `data/logs/livello`).
`☐ OK ☐ KO`

**L4 · Traceback e run_id**
Su un evento di errore (usa B9 per generarne uno), espandi.
**Atteso:** traceback completo e il `run_id` che rimanda al trace.
`☐ OK ☐ KO`

**L5 · Esporta**
*Esporta (oggi)*.
**Atteso:** scarica il `.jsonl` del giorno.
`☐ OK ☐ KO`

**L6 · I log non sporcano il repo**
Dopo aver generato eventi, `git -C data status`.
**Atteso:** **pulito**. I log stanno dentro `data/` ma sono gitignorati: sono
diagnostica, non stato applicativo.
`☐ OK ☐ KO`

**L7 ⭐ 🔑 💶 · Diagnosi automatica**
Genera un errore (B9), poi Admin → **Diagnosi** → *Analizza errori adesso*.
**Atteso:** una diagnosi con **badge di categoria** — `dato` (correzione in una
skill/tool/schema/manifest, con scorciatoia all'Improver) o `architettura` (serve
toccare il codice-cornice: **sola analisi**, mai applicata) — causa radice, proposta,
**file di codice letti** e traceback espandibili.
`☐ OK ☐ KO` — categoria: ____________

**L8 · Niente da analizzare**
Con nessun errore recente, rilancia l'analisi.
**Atteso:** «Nessun errore recente da analizzare.»
`☐ OK ☐ KO`

**L9 · Deduplicazione per firma**
Genera **due volte** lo stesso errore e rianalizza.
**Atteso:** **una** diagnosi con il conteggio a 2, non due diagnosi.
`☐ OK ☐ KO`

**L10 · Risolvi / archivia**
*Segna risolta* e *Archivia* su due diagnosi.
**Atteso:** passano nelle rispettive schede (Aperte / Risolte / Archiviate).
`☐ OK ☐ KO`

**L11 · Niente si applica da solo**
Rileggi una diagnosi di categoria `architettura`.
**Atteso:** contiene la modifica **raccomandata**, e nessun file di `backend/app/` è
stato toccato (`git status` pulito sul repo del codice).
`☐ OK ☐ KO`

---

## 15 · M — Robustezza, audit e principi architetturali

Questi non sono «funzionalità»: sono le promesse del progetto. Vanno verificate
tanto quanto i bottoni.

**M1 ⭐ · Ogni mutazione è un commit**
`git -C data log --oneline | head -20` dopo una sessione di lavoro.
**Atteso:** un commit per ogni creazione, modifica, validazione, consolidamento,
rimozione — con l'autore e il `run_id` nel messaggio. È l'audit trail completo.
`☐ OK ☐ KO`

**M2 ⭐ · Nessuno stato fuori da `/data`**
Ferma l'app, sposta/rinomina `data/`, riavvia.
**Atteso:** l'app parte (l'health check non richiede il repo) ma ogni endpoint che
serve dati risponde `503` con un messaggio chiaro. Rimettendo `data/` a posto, tutto
torna com'era: nessuno stato è rimasto altrove.
`☐ OK ☐ KO`

**M3 ⭐ · Un errore del modello non fa cadere niente**
Metti `LLM_T1_MODEL` a un nome inesistente, riavvia, carica un documento.
**Atteso:** il documento va in 🔴 con «Serve una mano», nasce una segnalazione
automatica, l'errore è nel logbook con traceback. **Nessun 500 in faccia
all'operatore.** Rimetti il modello buono.
`☐ OK ☐ KO`

**M4 · Nessuna eccezione arriva all'utente**
Durante tutta la sessione, apri la console del browser.
**Atteso:** nessun `500`; l'unico messaggio d'errore generico ammesso è «errore
interno: ci pensa l'ufficio».
`☐ OK ☐ KO`

**M5 · Scritture concorrenti**
Da due schede, valida due documenti diversi nello stesso momento.
**Atteso:** entrambe riescono, due commit distinti, nessun repo git in stato
inconsistente (il DAL è single-writer).
`☐ OK ☐ KO`

**M6 · Il codice generato gira solo in sandbox**
Se hai fatto I10: cerca l'import del tool nel processo.
**Atteso:** non esiste. `data/tools/<nome>/` è dato versionato, eseguito in
subprocess isolato (import in whitelist, niente rete/FS/ambiente, limiti
CPU/memoria/tempo).
`☐ OK ☐ KO ☐ N/A`

**M7 · I modelli non sono nel codice**
`grep -rn "gpt-\|claude-\|gemini-" backend/app/ --include=*.py`.
**Atteso:** **un solo** riscontro, ed è un *commento* in `core/gateway.py` (sui
modelli reasoning). Nessun nome di modello usato come valore: i tier arrivano
dall'ambiente. Ogni altro riscontro è un KO.
`☐ OK ☐ KO`

**M8 ⭐ · Riavvio a freddo**
Ferma tutto e riavvia (`docker compose down && docker compose up -d`, oppure Ctrl-C
su `make dev` e ripartenza).
**Atteso:** sessioni scadute (rilogin), ma **tutti** i dati, le viste consolidate, le
patch approvate, il livello di log e le sincronizzazioni ERP sono dove li avevi
lasciati.
`☐ OK ☐ KO`

**M9 ⭐ · Lo scenario ritenuta non si rompe mai**
`make test` a fine sessione, dopo tutte le modifiche fatte a mano.
**Atteso:** verde, e in particolare
`pytest backend/tests/test_improver_e2e.py::test_scenario_ritenuta`.
`☐ OK ☐ KO`

---

## 16 · Matrice: caso d'uso → prove

| Caso d'uso della piattaforma | Prove |
|---|---|
| Accesso, ruoli, isolamento per cantiere | A1–A9 |
| Acquisizione documenti (foto/PDF) | B1, B12, B13 |
| Classificazione automatica del tipo | B2 |
| Estrazione LLM + confidence per campo | B1, D2 |
| Riepilogo leggibile / lessico non tecnico | B1, B7, B15 |
| Conferma e segnalazione dell'operatore | B4, B5, B6 |
| Stato dei propri documenti (semaforo) | B7, B8 |
| Documenti d'esempio scaricabili | B0 |
| Consuntivo ore dell'operaio | C1–C5 |
| Domande in linguaggio naturale (operatore) | C6, C7 |
| Coda di revisione + originale a fianco | D1, D2 |
| Validazione umana → golden set | D3, D4, H6 |
| Feedback sui campi | D5 |
| Correzione manuale dei dati | D6 |
| Collegamento fattura ↔ computo | D7, E6 |
| Anagrafica mancante creata dal documento | D8, D9 |
| Trace per-run (costo, latenza, tool call) | D12, H10 |
| Cruscotto costi, ritenute, ore, manodopera | E1–E4 |
| Registro di cantiere | E5 |
| Preventivo vs consuntivo (scostamenti) | E6, E7 |
| Report Excel (6 fogli) | E8, E9 |
| CRUD generico guidato dagli schemi | F1–F6, F8 |
| Integrità referenziale (no cancellazioni orfane) | F7, F7b |
| Registri automatici (pozzetti, cronoprogramma) | F9 |
| Text-to-SQL con guardrail | G1–G7 |
| Segnalazione → Improver → patch → replay | H1, H3, H4, H9 |
| Pubblicazione v1.1 + rielaborazione | H4, H5 |
| Regola dettata in italiano | H8 |
| Rifiuto di una patch | H7 |
| Consolidamento in vista `v_*` | I1–I3 |
| Consolidamento in tool parametrico `t_*` | I4–I6 |
| Registry dei tool nativi con contatori | I7 |
| Toolsmith Python (codice=dato, sandbox) | I8–I11, M6 |
| Costi LLM ed export dataset | J1–J4 |
| Tier locale T3 e idoneità | J5, J6 |
| Sync alla validazione → ERPNext | K2–K4 |
| Ritenuta d'acconto a valle | K3 |
| Idempotenza e no-doppioni | K5, K6, K10 |
| Resilienza ERP (giù, recupero, riprova) | K7–K9 |
| Read-back pagamenti | K10 |
| Integrazione spenta = no-op | K12 |
| Osservabilità contabile (registro tentativi) | K1, K13 |
| Logbook, filtri, livello a runtime | L1–L6 |
| Diagnosi automatica degli errori | L7–L11 |
| Audit git, single-writer, stato solo in /data | M1, M2, M5 |
| Nessun errore propagato all'utente | M3, M4 |
| Modelli non hard-coded | M7 |
| Persistenza al riavvio | M8 |
| Regressione M5 | M9 |

---

## 17 · Limiti noti e cosa **non** è coperto

Da sapere prima, per non registrare come KO ciò che è fuori scope o è un buco già
noto.

1. **Toolsmith Python e Idoneità T3 non hanno interfaccia** (I8–I11, J5): esistono
   solo come API. Il README li descrive come pagine — è un buco di interfaccia, non
   del backend.
2. **Golden set vuoto nell'immagine Docker**: `reportlab` è una dipendenza di
   sviluppo e il seed dei casi golden viene saltato. Il golden si riempie validando.
3. **Nessun `.env` fuori da Docker**: `make dev` legge solo l'ambiente della shell.
4. **Il trace si apre solo da Segnalazioni** (D12): non da Revisione né da Workflows,
   che pure mostrano i run. L'API `GET /api/runs/{run_id}/trace` è generale.
5. **Emissione elettronica SdI e ciclo attivo**: fuori scope dichiarato.
6. **La sincronizzazione ERP è mono-direzionale** WF→ERP: l'unico ritorno è lo stato
   di pagamento. Modifiche fatte in ERPNext non tornano indietro.
7. **Un solo worker**: il DAL è single-writer per costruzione, non si scala
   orizzontalmente.
8. **PIN demo**: `1111`/`9999` sono dimostrativi e vanno cambiati prima di qualunque
   uso reale.
9. **La qualità dell'estrazione dipende dal modello**: un KO su B1/B12 può essere il
   modello, non il codice. Annota sempre **quale modello** stavi usando (T0.3).

---

## 18 · Foglio esiti

| Sezione | Casi | OK | KO | N/A | Note |
|---|---|---|---|---|---|
| T0 Pre-flight | 5 | | | | |
| A Accesso e permessi | 9 | | | | |
| B Caricamento documenti | 16 | | | | |
| C Ore e domande | 7 | | | | |
| D Revisione | 12 | | | | |
| E Costi e report | 10 | | | | |
| F Dati e anagrafiche | 10 | | | | |
| G Interrogazione | 8 | | | | |
| H Improver | 11 | | | | |
| I Consolidamento | 11 | | | | |
| J Dataset e T3 | 6 | | | | |
| K Contabilità ERP | 14 | | | | |
| L Log e diagnosi | 11 | | | | |
| M Robustezza e audit | 9 | | | | |
| **Totale** | **139** | | | | |

**Ambiente usato:** ☐ A locale ☐ B Docker
**Modello T1:** ______________ **T2:** ______________ **T3:** ______________
**ERPNext:** ☐ collegato ☐ spento — versione: ______________
**Data:** ____ / ____ / ________ **Eseguito da:** ______________________

### KO da riportare

| Caso | Cosa hai visto | Riproducibile | Gravità |
|---|---|---|---|
| | | ☐ sì ☐ no | ☐ blocca ☐ grave ☐ minore |
| | | ☐ sì ☐ no | ☐ blocca ☐ grave ☐ minore |
| | | ☐ sì ☐ no | ☐ blocca ☐ grave ☐ minore |
| | | ☐ sì ☐ no | ☐ blocca ☐ grave ☐ minore |
