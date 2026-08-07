# Test-book — verifica manuale di Workflower

Copre **tutti i casi d'uso della piattaforma allo stato attuale** (M0–M29): le due
interfacce, il ciclo di auto-miglioramento, il consolidamento, l'integrazione
contabile con ERPNext, log e diagnosi, il parser documenti su GPU e il controllo
che il documento sia intestato a noi.

Per la parte «come si usa e come si mostra a un cliente» c'è
[`guida_utente/`](../guida_utente/README.md), che condivide con questo test-book i
documenti d'esempio (`guida_utente/esempi/`).

È pensato per essere eseguito a mano, in ordine, da una persona sola in una
sessione. Serve a rispondere a una domanda: *cosa funziona davvero quando lo tocchi
con le dita*, non *cosa passa in pytest*. La suite automatica (`make test`) copre la
logica; questo copre l'esperienza.

**Durata indicativa:** 2 ore e mezza per il giro completo, 40 minuti per il solo
percorso critico (i casi segnati ⭐).

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

| | **A — Locale (`make dev`)** | **B — Docker** |
|---|---|---|
| Interfaccia | <http://localhost:5173/op> · `/admin` | <http://localhost/op> · `/admin` |
| Golden set di partenza | **2 casi dal seed** | **2 casi dal seed** ¹ |
| PDF di prova | in `fixtures/` + scaricabili dall'app | scaricabili dall'app |
| Configurazione | variabili **nella shell** ² | dal file `.env` |
| Ricarica del codice | a caldo | serve `docker compose up -d --build` |
| Adatto a | sviluppo e giro completo | **ambiente di prova realistico** |

¹ Gli originali dei casi golden sono asset versionati e vengono **copiati**, non
ridisegnati: il golden set esiste anche nell'immagine di produzione, dove
`reportlab` (dipendenza di sviluppo) non è installato. Prima era vuoto nel
container, e il replay di una patch diceva `0/0` — cioè non dimostrava niente.

² Il confine è sottile e vale conoscerlo. **L'app legge il `.env` anche fuori da
Docker**, ma per un effetto collaterale: `litellm` chiama `load_dotenv()` quando
viene importato, quindi `make dev` si ritrova nell'ambiente tutto il `.env`,
`ERP_*` comprese. Gli **script** invece no — `scripts/erp_smoke.py` non importa il
gateway, quindi per lui le variabili vanno **nella shell**, e la sintassi non è
intercambiabile (in `cmd.exe` `set X="v"` mette le virgolette *dentro* al valore).
Nei test il `.env` viene ripulito di proposito (`conftest.erp_non_configurato`):
un test non deve trovarsi collegato all'ERP reale per caso.

### 1.2 Ambiente da zero, in ordine

La sequenza completa per ripartire come da prima installazione. **Cancella dati**:
il repo `data/`, il volume dell'app e i volumi ERPNext.

```bash
docker compose down -v
```
```bash
docker compose -f docker-compose.erpnext.yml down -v
```
```bash
make reseed
```
```bash
make erp-up
```

Attendi che il sito ERPNext esista (la prima volta sono minuti):

```bash
docker compose -f docker-compose.erpnext.yml logs -f create-site
```

Poi prepara l'ERP e collega:

```bash
make erp-dev-setup
```

Stampa due blocchi. Il **blocco 1** va nel `.env` (usa `host.docker.internal`, che è
come il container raggiunge l'host); il blocco della tua shell serve agli script
dall'host. Infine:

```bash
docker compose up -d
```
```bash
make erp-smoke ARGS=--full
```

L'entrypoint del container fa il seed da solo quando il volume è vuoto. `make reseed`
serve al `data/` locale, per l'ambiente A e per `pytest`.

**Il parser documenti su GPU** (serve ai casi con Word ed Excel — B9b–B9d, D2b):

```bash
make docling-up
```
```bash
make docling-check
```

Deve stampare solo `PASS`, compresa la riga sulla GPU. In `.env` va il valore per
l'**host** (`DOCLING_URL=http://127.0.0.1:5001`): il compose lo riscrive da sé nel
nome di servizio per il container.

**Su un ambiente che esisteva già** — cioè quasi sempre, tranne la prima
installazione — il seed non tocca il repo dati, quindi manifest e schemi restano
quelli del giorno in cui è stato creato. Prima di iniziare:

```bash
make data-sync
```
```bash
make data-sync ARGS=--applica
```

Se lo salti, i casi che riguardano funzioni nuove falliscono **senza dare
errore** — il che è peggio di un KO, perché sembra un problema del prodotto.

**Per rifare la demo senza perdere i golden** (alternativa a `make reseed`, che
azzera anche quelli):

```bash
make demo-reset ARGS=--applica
```

### 1.3 Ambiente A — locale

PowerShell:

```bash
$env:JWT_SECRET = "una-stringa-lunga-almeno-32-caratteri"; $env:LLM_T1_MODEL = "gpt-5.5"; $env:LLM_T2_MODEL = "gpt-5.4"; $env:OPENAI_API_KEY = "sk-..."; $env:LOG_LEVEL = "INFO"
```

poi, nella **stessa** finestra:

```bash
make fixtures
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
Da Admin → **Interroga**, chiedi «Quante fatture ci sono?». Deve tornare una
risposta leggibile, fonti semantiche e trace. Se qui vedi un errore di modello (nome non valido, chiave scaduta,
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
**Atteso:** barra che include Cruscotto, Dati, Scostamenti, Revisione,
Segnalazioni, Agente dati, Evoluzione agente, Workflows, Run, Skills & Tools,
Dataset, Contabilità, Log, Diagnosi). Nessuna voce promette interrogazioni tecniche.
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

**B3 ⭐ 🔑 💶 · La parcella con la ritenuta**
Carica `fattura-studio-bianchi.pdf`.
**Atteso:** imponibile 4.000, IVA 880, totale 4.880. Sulla **ritenuta di 800** dipende
dal modello: la skill v1.0 non la nomina, quindi un modello debole la salta — ed è il
punto di partenza del giro dell'Improver (sezione H). Un T1 forte la estrae comunque
(verificato: `gpt-5.5` la prende, confidenza 100%). Annota quale dei due casi vedi: se
la ritenuta c'è già, per provare H3–H5 serve un'altra istruzione (es. «riporta la
descrizione delle righe in maiuscolo»), non questa.
`☐ OK ☐ KO` — ritenuta estratta dalla v1.0: ☐ sì ☐ no

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
Carica un `.zip` o un `.txt` (`guida_utente/esempi/12-file-non-leggibile.txt`).
**Atteso:** semaforo 🔴 con «Serve una mano: se ne occupa l'ufficio», e una
segnalazione automatica in Admin → Segnalazioni. **Nessun crash, nessun 500.**
`☐ OK ☐ KO`

**B9b · Word ed Excel senza il parser su GPU**
Con il sidecar **spento** (`make docling-down`), carica
`guida_utente/esempi/03-fattura-word.docx`.
**Atteso:** stesso esito di B9 — rifiutato subito, 🔴 e segnalazione. Il rifiuto è
voluto: senza parser nessuno saprebbe leggerlo, e accettarlo darebbe un semaforo
rosso mezz'ora dopo invece di un no chiaro adesso.
`☐ OK ☐ KO`

**B9c ⭐ · Word con il parser su GPU acceso** 🔑 💶
`make docling-up && make docling-check` (tutto PASS), poi ricarica
`guida_utente/esempi/03-fattura-word.docx`.
**Atteso:** viene **accettato** e letto come una fattura: fornitore «Ferramenta
Siciliana S.r.l.», numero `512/2026`, imponibile `3250`, IVA `715`, totale `3965`,
tre righe. In Admin → Run il trace mostra `leggi_documento` (non `ocr_pdf`).
`☐ OK ☐ KO`

**B9d · DDT in Word: il tipo lo capisce leggendo il testo** 🔑 💶
Carica `guida_utente/esempi/09-ddt-word.docx`.
**Atteso:** instradato su **carica-ddt**, non su carica-fattura. È la prova che il
classificatore ha letto il testo: su un `.docx` nessun modello che guarda le
pagine potrebbe farlo.
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
**Atteso:** una risposta in italiano sui **propri** cantieri. Non devono comparire
dettagli tecnici né dati di cantieri non assegnati.
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
Apri una bozza nata da un PDF o da una foto.
**Atteso:** a sinistra il **PDF originale** in anteprima (riquadro «Originale»), a
destra i campi estratti con un badge di confidenza per campo (verde ≥90%, giallo
≥75%, rosso sotto) e la tabella delle righe.
`☐ OK ☐ KO`

**D2b · Anteprima di un Word** 🔑
Apri la bozza nata da `03-fattura-word.docx` (B9c).
**Atteso:** il riquadro si intitola **«Lettura del documento»** e mostra il
contenuto — testo e tabella — **non** una richiesta di scaricare il file. Sotto,
la riga: «Word ed Excel non si possono mostrare così come sono: questa è la
lettura del documento, la stessa da cui sono stati estratti i campi.»
`☐ OK ☐ KO`

**D2c · Anteprima con il parser spento**
Con il sidecar spento, riapri la stessa bozza.
**Atteso:** si torna al comportamento di prima (il browser propone il download);
**nessun errore 500**. Non è un KO: è il ripiego previsto.
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

**D12 ⭐ · Trace del run**
In revisione, *Mostra trace*. (Si apre anche da **Run** e da **Segnalazioni**.)
**Atteso:** gli eventi in ordine — `run_start`, le chiamate al modello con **token,
costo e latenza**, le tool call, la validazione, `run_end` — e le tue note sui campi
(D5) in coda, come `field_feedback`.
`☐ OK ☐ KO`

**D13 ⭐ · Scarta una bozza sbagliata**
Su una bozza, *Scarta* → il motivo è **obbligatorio** (senza, il bottone resta
spento) → scrivi «fattura doppia» → *Sì, scarta*.
**Atteso:** si torna alla coda e la bozza non c'è più. In **Cruscotto** il conteggio
fatture scende di 1 e lo speso cala. In **Dati → Scartati** compare la riga con
motivo, autore e data.
`☐ OK ☐ KO`

**D14 ⭐ · L'operatore lo viene a sapere**
Con l'utente che aveva caricato quel documento, apri *I miei documenti*.
**Atteso:** semaforo **🔴** e «L'ufficio ha scartato questo documento. Se serve,
ricaricalo.» Non deve restare 🟢 «Tutto a posto» per una fattura che non esiste più.
`☐ OK ☐ KO`

**D15 ⭐ · Ripristina**
Dati → Scartati → *Ripristina*.
**Atteso:** l'inserimento torna dov'era — in coda di revisione se era bozza, validato
se era validato — senza il motivo di scarto, e il cruscotto torna ai numeri di prima.
`☐ OK ☐ KO`

**D16 · Scartare un validato toglie il caso golden**
Valida una bozza (annota il `GOLD-…` che compare), poi scartala. Guarda i **casi
golden** in Workflows.
**Atteso:** quel caso non c'è più. Altrimenti l'Improver misurerebbe ogni nuova
versione contro un dato che l'ufficio ha ripudiato.
`☐ OK ☐ KO`

**D17 · Lo scarto chiude la segnalazione**
Su un documento con una segnalazione aperta (B5), scarta.
**Atteso:** la segnalazione sparisce dalle aperte: non c'è più niente su cui
intervenire.
`☐ OK ☐ KO`

**D18 · L'id non si riusa**
Dopo D13, carica un altro documento dello stesso tipo.
**Atteso:** prende l'id **successivo**, non quello liberato dallo scarto — altrimenti
il ripristino andrebbe a sbattere contro il nuovo documento.
`☐ OK ☐ KO`

**D19 · Un'anagrafica non si scarta**
Via API: `POST /api/review/FRN-001/scarta`.
**Atteso:** `409`, «non è un documento in arrivo: le anagrafiche si correggono o si
eliminano da Dati». Lo scarto è per i documenti, non per il master data.
`☐ OK ☐ KO`

### D20–D24 · Il documento è intestato a noi?

Prima di questi casi: Admin → Sistema → **La nostra azienda** dev'essere
compilata (denominazione «Costruzioni Aitho S.r.l.»).

**D20 ⭐ · Fattura intestata a un'altra impresa** 🔑 💶
Carica `guida_utente/esempi/05-fattura-intestata-ad-altri.pdf`.
**Atteso:** la bozza **si salva lo stesso** (esito ok, non errore), parte **in
revisione**, e in Admin → Segnalazioni compare: «Il documento risulta intestato a
«Costruzioni Delta S.r.l.», non a «Costruzioni Aitho S.r.l.»: da controllare prima
di registrarlo.» Il campo `destinatario` della bozza contiene «Costruzioni Delta
S.r.l.».
`☐ OK ☐ KO`

**D21 ⭐ · Fattura intestata a noi: nessun rumore** 🔑 💶
Carica `guida_utente/esempi/01-fattura-digitale.pdf`.
**Atteso:** nessuna segnalazione sul destinatario, e — se le confidenze sono
alte — **non** finisce in revisione. Un controllo che si accende sempre non lo
guarda più nessuno.
`☐ OK ☐ KO`

**D22 · Varianti della stessa ragione sociale** ⌨
Non serve un documento: `pytest backend/tests/test_azienda.py -k varianti`.
**Atteso:** passano come «noi» le scritture `COSTRUZIONI AITHO SRL`, `Aitho
Costruzioni S.r.l.`, `Costruzioni Aiho S.r.l.` (refuso), e la riga intera
`Spett.le Costruzioni Aitho S.r.l. - Viale Africa 31, Catania`.
`☐ OK ☐ KO`

**D23 · Un'omonimia parziale non passa** ⌨
`pytest backend/tests/test_azienda.py -k altre_imprese`.
**Atteso:** «Costruzioni Etna S.r.l.» e «Costruzioni Delta S.r.l.» **non** sono
riconosciute come noi, benché condividano la parola «Costruzioni».
`☐ OK ☐ KO`

**D24 · Azienda non configurata = controllo spento**
Svuota la denominazione in **La nostra azienda** (o prova su un repo dati creato
prima che la sezione esistesse), poi ricarica il documento di D20.
**Atteso:** nessuna segnalazione sul destinatario; tutto il resto invariato. Poi
rimetti la denominazione.
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

**F10 ⭐ · La nostra azienda**
Admin → Sistema → **La nostra azienda**.
**Atteso:** dopo il seed la denominazione è già «Costruzioni Aitho S.r.l.» e la
partita IVA è **vuota** (il seed non inventa un identificativo fiscale). Modifica
un campo e salva: *Salvato*, e in `data/config/azienda.json` il valore è
cambiato, con un commit intestato a chi ha salvato.
`☐ OK ☐ KO`

**F11 · Denominazione obbligatoria**
Svuota la denominazione e salva.
**Atteso:** rifiutato con «la denominazione è obbligatoria», nessun traceback.
Finché è vuota, la pagina avvisa che il controllo del destinatario non viene
fatto.
`☐ OK ☐ KO`

**F12 · È riservata all'ufficio** ⌨
Con il token di un operatore: `GET /api/config/azienda`.
**Atteso:** `403`. È il riferimento con cui si giudicano i documenti: non lo
cambia chi carica le foto dal cantiere.
`☐ OK ☐ KO`

---

## 9 · G — Ufficio: interrogazione in linguaggio naturale

Tutti 🔑💶.

**G1 ⭐ 🔑 💶 · Domanda semplice**
Admin → **Interroga** → «Quanto abbiamo speso per ogni cantiere?».
**Atteso:** risposta leggibile, strumenti semantici e fonti usati, con trace
apribile. Non compare alcun dettaglio dell'implementazione interna.
`☐ OK ☐ KO`

**G2 ⭐ 🔑 💶 · La domanda della demo**
«Quali fatture hanno una ritenuta d'acconto?».
**Atteso:** sulla baseline, una riga: **FT-2026-0004**, ritenuta 800.
`☐ OK ☐ KO`

**G3 🔑 💶 · Domanda su ore e manodopera**
«Quante ore sono state fatte per cantiere questo mese?».
**Atteso:** risposta coerente con il Cruscotto (E1) e traccia di almeno uno strumento.
`☐ OK ☐ KO`

**G4 ⭐ · Follow-up conversazionale**
Dopo G2 chiedi «e qual è la prossima scadenza?».
**Atteso:** usa il contesto dello scambio precedente; la conversazione mostra due
scambi completi e il trace del secondo run è distinto.
`☐ OK ☐ KO`

**G5 · Nuova conversazione**
Premi *Nuova conversazione*, poi ripeti una domanda che richiedeva il contesto G4.
**Atteso:** la memoria è vuota e l'agente chiede un chiarimento o dichiara che non ha
abbastanza informazioni, senza usare lo scambio precedente.
`☐ OK ☐ KO`

**G6 · Limiti e risposta fuori catalogo**
Chiedi una domanda non coperta («prevedi il prezzo del rame il mese prossimo»).
**Atteso:** l'agente dichiara di non avere ancora lo strumento adatto; non inventa
dati, non esegue scritture e lascia un trace consultabile.
`☐ OK ☐ KO`

**G7 ⭐ · Perimetro cantiere**
Accedi come operatore e chiedi costi, fatture e avanzamento. Ripeti come ufficio.
**Atteso:** l'operatore vede solo i propri cantieri, anche nei totali; l'ufficio può
vedere il perimetro completo. Il trace operatore non include righe di altri cantieri.
`☐ OK ☐ KO`

**G8 · Contesto e limiti**
Configura la memoria a 6 messaggi, invia quattro domande e ricarica la pagina.
**Atteso:** restano solo gli ultimi tre scambi completi. Riprova con una risposta
molto ampia: lo strumento limita righe e dimensione, la chat resta utilizzabile.
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
Torna in **Revisione** e apri la bozza rielaborata.
**Atteso:** il documento porta la correzione che avevi chiesto (nel caso classico,
`ritenuta_acconto = 800`). È la *definition of done* del prodotto — e resta coperta dal
test end-to-end `test_improver_e2e.py::test_scenario_ritenuta`, che gira col modello
finto e quindi non dipende da quanto è bravo il T1 del momento.
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

**H12 ⭐ · I casi golden si vedono**
In **Workflows**, card «Casi golden — la rete di regressione».
**Atteso:** i **2** casi del seed con workflow, versione, documento, chi ha validato,
e il badge *originale mancante* assente (l'originale deve essere rieseguibile).
Validando in D3 ne compare uno in più.
`☐ OK ☐ KO`

**H13 · Rimuovi un caso golden**
*Rimuovi* → *Sì, rimuovi* su un caso.
**Atteso:** sparisce, e il conteggio «casi golden» del workflow scende. Il replay
della patch successiva ne userà uno in meno. Commit git, reversibile.
`☐ OK ☐ KO`

**H14 ⭐ · Elenco dei run**
Admin → **Run**.
**Atteso:** una riga per esecuzione con quando, workflow@versione, documento, esito,
**costo** e **durata**; i KPI in alto contano run mostrati, falliti, costo totale ed
escalation. Dal più recente.
`☐ OK ☐ KO`

**H15 ⭐ · Trace da Run**
Su una riga, *Trace*.
**Atteso:** il trace si apre in linea, con `run_id`, numero di chiamate al modello,
tool e token in testa, e gli eventi in ordine.
`☐ OK ☐ KO`

**H16 · Filtri dei run**
Filtra per workflow e per esito *Falliti*.
**Atteso:** i filtri si combinano e restano nell'URL (ricaricando la pagina tengono).
Con nessun risultato, una frase che lo spiega.
`☐ OK ☐ KO`

**H17 · Da Workflows ai run**
In **Workflows**, clicca il numero di run di un workflow (e, se >0, quello degli
errori).
**Atteso:** porta a **Run** già filtrato su quel workflow (e sui falliti).
`☐ OK ☐ KO`

**H18 · Un run fallito si vede**
Genera un errore (B9), poi Run → esito *Falliti*.
**Atteso:** il run c'è, con il motivo dell'errore in rosso sotto la riga. Prima di
questa pagina un run fallito senza segnalazione era invisibile.
`☐ OK ☐ KO`

**H11 ⭐ · L'operatore non approva mai**
Cerca, nell'interfaccia operatore, qualunque modo di approvare una patch.
**Atteso:** non esiste. L'operatore segnala, l'ufficio decide.
`☐ OK ☐ KO`

---

## 11 · I — Evoluzione controllata dell’agente dati

**I1 ⭐ · Lacuna e proposta**
Admin → **Evoluzione agente** → descrivi una domanda fuori catalogo.
**Atteso:** nasce una proposta con analisi, intenti coperti, esempi, ruoli, scope,
test mirato e replay; è associata a un trace.
`☐ OK ☐ KO`

**I2 ⭐ · DSL ispezionabile**
Apri il dettaglio della proposta.
**Atteso:** l'ufficio può leggere definizione dichiarativa, parametri, esempi,
risultato atteso e collaudo. Non compaiono dettagli del motore dati.
`☐ OK ☐ KO`

**I3 ⭐ · Collaudo del perimetro**
Per una proposta disponibile anche all'operatore, verifica il test di scope.
**Atteso:** il collaudo prova un cantiere assegnato e fallisce se una riga esce dal
perimetro; senza test verde la proposta non è approvabile.
`☐ OK ☐ KO`

**I4 ⭐ · Replay prima dell'approvazione**
Controlla il replay della proposta e prova ad approvarla dopo aver reso un golden
non verde.
**Atteso:** il replay copre il set agent-native corrente e l'approvazione è bloccata.
`☐ OK ☐ KO`

**I5 ⭐ · Approvazione atomica**
Approva una proposta verde.
**Atteso:** registry, eventuale skill, proposta e versione dell'agente cambiano in un
solo commit; il catalogo aggiornato è subito disponibile nella chat.
`☐ OK ☐ KO`

**I6 · Rifiuto**
Rifiuta una proposta.
**Atteso:** resta nello storico come rifiutata; catalogo, skill e versione non cambiano.
`☐ OK ☐ KO`

**I7 · Registry dei tool nativi**
Card «Tool nativi (Python)».
**Atteso:** elenco delle funzioni deterministiche di sistema con descrizione,
**contatore d'uso** e badge di ciclo di vita.
`☐ OK ☐ KO`

**I8 ⭐ · Toolsmith: i candidati**
Skills & Tools, card «Candidati Python — calcoli che l'ufficio corregge sempre».
**Atteso:** un campo per riga con quante volte è stato corretto, il tipo, il workflow
e qualche valore d'esempio. Con nessuna correzione ripetuta: la card lo dice e spiega
che il segnale nasce dal delta fra bozza e dato validato. Per generarne uno: correggi
lo **stesso** campo in due o tre documenti (in *Modifica dati*) e validali.
`☐ OK ☐ KO`

**I9 ⭐ 🔑 💶 · Toolsmith: genera la proposta**
Su un candidato, *Proponi un tool* → nome (minuscole/underscore) → seleziona i campi
da cui si **ricava** l'uscita → *Genera la proposta*.
**Atteso:** con meno di 3 esempi validati, un messaggio che lo **spiega** («servono
almeno 3 esempi validati, trovati N»), non un errore tecnico. Con abbastanza esempi,
nasce una proposta.
`☐ OK ☐ KO`

**I10 ⭐ · Toolsmith: ispeziona**
Sulla proposta, *Ispeziona*.
**Atteso:** il **codice Python**, lo **schema** e i **test coi casi già validati**, con
atteso, ottenuto e ✅/❌ per ognuno, eseguiti in **sandbox**. Il badge dice `test N/N`.
Se non passano tutti, un avviso in chiaro: approvare consoliderebbe un calcolo
sbagliato.
`☐ OK ☐ KO`

**I11 ⭐ · Toolsmith: approva**
*Approva*.
**Atteso:** il messaggio nomina il tool registrato **e** la patch di skill che ne è
nata, col replay sul golden set e il link ai Workflows dove si approva a parte. Nel
registry «Tool nativi» il tool compare col badge **Toolsmith** e un pulsante
*Rimuovi* (i nativi non ce l'hanno).
`☐ OK ☐ KO`

**I12 · Toolsmith: rifiuta**
Genera una seconda proposta e *Rifiuta*.
**Atteso:** stato `rifiutata`, nessun tool registrato, nessuna skill toccata.
`☐ OK ☐ KO`

**I13 · Rimuovi un tool consolidato**
Su un tool con badge Toolsmith, *Rimuovi* → *Sì, rimuovi*.
**Atteso:** sparisce dal registry; il candidato torna disponibile. È un commit git,
reversibile.
`☐ OK ☐ KO`

---

## 12 · J — Dataset, costi e tier locale

**J1 ⭐ · Costo per documento**
Admin → **Dataset**.
**Atteso:** costo LLM totale, costo per documento, totale documenti, tool call
registrate, esempi di fine-tuning. Con `LLM_T1/T2` a modelli veri i costi sono >0 e
credibili.
`☐ OK ☐ KO`

**J2 · Export delle tool call**
Controlla i trace dei run dell'agente dati.
**Atteso:** le chiamate agli strumenti, gli argomenti e gli esiti sono tracciati;
la conversazione conserva solo messaggi utente, risposta finale e identificativo run.
`☐ OK ☐ KO`

**J3 · Export per il fine-tuning**
Skills & Tools → verifica il conteggio degli esempi validati.
**Atteso:** gli esempi dei workflow documentali restano separati dalla conversazione
dati; nessun archivio di prodotto esporta dettagli tecnici dell'interrogazione.
`☐ OK ☐ KO`

**J4 · Golden agent-native**
In Dataset → *Misura adesso* (con modello T3 configurato) e in Evoluzione agente
controlla il replay.
**Atteso:** la misura e il replay usano golden con domanda, eventuale contesto,
strumento, argomenti normalizzati e risultato normalizzato; il conteggio è dinamico.
`☐ OK ☐ KO`

**J5 ⭐ · Idoneità T3: senza modello lo dice**
Dataset → card «Idoneità T3 — il modello locale» → *Misura adesso*, con
`LLM_T3_MODEL` **non** impostato.
**Atteso:** «Nessun modello T3 configurato: imposta `LLM_T3_MODEL`…» — non una
tabella di zeri che sembra un fallimento del modello.
`☐ OK ☐ KO`

**J5b 🔑 💶 · Idoneità T3: la misura**
Con `LLM_T3_MODEL` impostato su un modello locale, *Misura adesso*.
**Atteso:** per l'agente dati mostra precisione di scelta strumento, argomenti e
risultato normalizzato per T3 e T1, con verdetto — *pronto per T3* /
*regredirebbe* / *da migliorare*. **Non parte da sola**: rigioca il set agent-native
validato sui due tier.
`☐ OK ☐ KO ☐ N/A`

**J5c ⭐ · L'harness non cade mai**
Chiama `GET /api/dataset/eval-t3` su un ambiente appena seminato (nessun run).
**Atteso:** `200` con i contatori del set documentale e dell'agente presenti anche se
vuoti. **Mai un 500**: una misura che va in errore a metà non serve a nessuno.
`☐ OK ☐ KO`

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

**K15 ⭐ 🧾 · Scartare un documento già in contabilità è bloccato**
Valida una fattura con l'ERP collegato (K2), poi prova a scartarla da Revisione.
**Atteso:** **409** con il numero della Purchase Invoice e l'istruzione **giusta per
il suo stato**: se è *Draft* «eliminala in ERPNext», se è *confermata* «annullala in
ERPNext (Cancel)». Non deve dire «annullala» di una bozza: in Frappe una bozza non si
annulla, e cercheresti un pulsante che non c'è. Il documento resta validato.
`☐ OK ☐ KO` — istruzione ricevuta: ____________________

**K16 ⭐ 🧾 · Sistemato a valle, lo scarto passa**
Elimina (o annulla) quel documento in `/app/purchase-invoice`, poi riprova a
scartarlo.
**Atteso:** questa volta lo scarto riesce. Workflower ha **letto** lo stato a valle,
non ha scritto niente: l'ERP resta l'unico padrone dei suoi annullamenti.
`☐ OK ☐ KO`

**K17 🧾 · Con l'ERP giù, non indovina**
Con una fattura già sincronizzata, `make erp-down`, poi prova a scartarla.
**Atteso:** **409** «Non riesco a verificare la contabilità adesso… riprova quando
l'ERP risponde». Non sapere non è come sapere che va bene.
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
**Atteso:** un commit per ogni creazione, modifica, validazione, proposta,
approvazione o rimozione — con l'autore e il `run_id` nel messaggio. L'approvazione
dell'agente raggruppa catalogo, skill, proposta e versione in un solo commit.
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
Da due schede, invia messaggi alla stessa conversazione e modifica il limite mentre
una risposta è in corso.
**Atteso:** nessuno scambio si perde o resta spezzato; reset, append e configurazione
sono serializzati e il repo resta consistente.
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
**Atteso:** sessioni scadute (rilogin), ma **tutti** i dati, le conversazioni, le
proposte approvate, il livello di log e le sincronizzazioni ERP sono dove li avevi
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
| **Word ed Excel via parser su GPU** | B9b, B9c, B9d, D2b, D2c |
| Classificazione automatica del tipo | B2, B9d |
| Estrazione LLM + confidence per campo | B1, D2 |
| Riepilogo leggibile / lessico non tecnico | B1, B7, B15 |
| Conferma e segnalazione dell'operatore | B4, B5, B6 |
| Stato dei propri documenti (semaforo) | B7, B8 |
| Documenti d'esempio scaricabili | B0 |
| Consuntivo ore dell'operaio | C1–C5 |
| Domande in linguaggio naturale (operatore) | C6, C7 |
| Coda di revisione + originale a fianco | D1, D2 |
| Validazione umana → golden set | D3, D4, H6 |
| **Scarto di un inserimento** (motivo, effetti, ripristino) | D13–D19 |
| Scarto bloccato se il documento è in contabilità | K15–K17 |
| Golden set ispezionabile e correggibile | H12, H13 |
| Elenco dei run e trace da ogni punto | D12, H14–H18 |
| Feedback sui campi | D5 |
| Correzione manuale dei dati | D6 |
| Collegamento fattura ↔ computo | D7, E6 |
| Anagrafica mancante creata dal documento | D8, D9 |
| **Il documento è intestato a noi?** | D20–D24, F10–F12 |
| **Allineamento del repo dati all'applicazione** | §1.2 (`make data-sync`) |
| Trace per-run (costo, latenza, tool call) | D12, H10, H15 |
| Cruscotto costi, ritenute, ore, manodopera | E1–E4 |
| Registro di cantiere | E5 |
| Preventivo vs consuntivo (scostamenti) | E6, E7 |
| Report Excel (12 fogli) | E8, E9 |
| CRUD generico guidato dagli schemi | F1–F6, F8 |
| Integrità referenziale (no cancellazioni orfane) | F7, F7b |
| Registri automatici (pozzetti, cronoprogramma) | F9 |
| Agente dati conversazionale, limiti e perimetro | G1–G8 |
| Segnalazione → Improver → patch → replay | H1, H3, H4, H9 |
| Pubblicazione v1.1 + rielaborazione | H4, H5 |
| Regola dettata in italiano | H8 |
| Rifiuto di una patch | H7 |
| Proposta DSL → collaudo → replay → approvazione | I1–I6 |
| Registry dei tool nativi con contatori | I7 |
| Toolsmith Python (codice=dato, sandbox) | I8–I13, M6 |
| Costi LLM ed export dataset | J1–J4 |
| Tier locale T3 e idoneità | J5, J5b, J6 |
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

1. **Il tier T3 va configurato a parte** (`LLM_T3_MODEL`): senza, la card «Idoneità
   T3» lo dice e J5/J6 non sono eseguibili. Non è un guasto.
2. **Il Toolsmith ha bisogno di storia**: candidati e proposte nascono dal delta fra
   bozza e dato validato, quindi su un ambiente appena seminato le card sono vuote
   fino a che non hai corretto e validato qualche documento (vedi I8).
3. **La misura T3 lavora su prompt troncati.** Il trace sostituisce ogni stringa
   oltre 400 caratteri con un segnaposto (`<N caratteri, sha256:…>`) — comprese le
   **skill**. Le immagini si ricostruiscono rifacendo l'OCR dell'originale, le
   istruzioni no: i due tier vengono quindi misurati con un prompt di sistema
   svuotato. Il **confronto** T3 contro T1 resta valido (stessa penalità per
   entrambi), le **percentuali assolute** sono sottostimate. La card lo dichiara.
   Vale anche per `finetuning.jsonl`, che eredita gli stessi messaggi: prima di
   addestrare davvero un modello locale, questa è la cosa da sistemare.
4. **Il `.env` arriva all'app anche fuori da Docker**, ma solo per l'effetto
   collaterale di `litellm` (vedi nota ² in §1.1): gli script no. Non è una
   configurazione da cui dipendere.
5. **Emissione elettronica SdI e ciclo attivo**: fuori scope dichiarato.
6. **La sincronizzazione ERP è mono-direzionale** WF→ERP: l'unico ritorno è lo stato
   di pagamento. Modifiche fatte in ERPNext non tornano indietro — e infatti lo
   scarto di un documento già a valle è **bloccato** invece di essere propagato.
7. **Lo scarto non tocca l'ERP**: dice cosa fare (eliminare la bozza o annullare il
   documento confermato) e attende. È una scelta, non una mancanza.
8. **Un solo worker**: il DAL è single-writer per costruzione, non si scala
   orizzontalmente.
9. **PIN demo**: `1111`/`9999` sono dimostrativi e vanno cambiati prima di qualunque
   uso reale.
10. **La qualità dell'estrazione dipende dal modello** — in entrambe le direzioni. Un
    KO su B1/B12 può essere il modello, non il codice. E con un T1 forte lo scenario
    didattico della ritenuta (B3 → H3) **non si riproduce**: il modello la estrae già
    alla v1.0. Annota sempre **quale modello** stavi usando (T0.3).
11. **Il parser documenti è opzionale.** Senza sidecar, B9b–B9d e D2b non sono
    eseguibili e Word/Excel vengono rifiutati: è il comportamento previsto, non un
    KO. E l'OCR dentro il sidecar gira su CPU (solo layout e tabelle usano la GPU),
    quindi una scansione costa circa un secondo a pagina.
12. **Il controllo del destinatario guarda solo la ragione sociale** letta sul
    documento, e la partita IVA quando c'è su entrambi i lati. Non verifica
    l'indirizzo. Un documento intestato a una società del gruppo con nome diverso
    finisce in revisione: è voluto, ma va spiegato a chi revisiona.
13. **`destinatario` non è un campo obbligatorio** dello schema fattura, perché le
    fatture registrate prima che il controllo esistesse devono restare valide. Se
    un modello lo omette del tutto, il controllo diventa un no-op: lo si vede nel
    logbook («il workflow … verifica il destinatario ma l'estrazione non l'ha
    prodotto»), non in interfaccia.
14. **Il repo dati non si aggiorna da solo.** Manifest e schemi restano quelli
    dell'installazione finché non si lancia `make data-sync ARGS=--applica`. È la
    causa più probabile di un caso che fallisce «senza motivo» su un ambiente
    vecchio: vedi §1.2.

---

## 18 · Foglio esiti

| Sezione | Casi | OK | KO | N/A | Note |
|---|---|---|---|---|---|
| T0 Pre-flight | 5 | | | | |
| A Accesso e permessi | 9 | | | | |
| B Caricamento documenti | 19 | | | | |
| C Ore e domande | 7 | | | | |
| D Revisione, scarto e destinatario | 26 | | | | |
| E Costi e report | 10 | | | | |
| F Dati, anagrafiche e azienda | 13 | | | | |
| G Interrogazione | 8 | | | | |
| H Improver, golden e run | 18 | | | | |
| I Consolidamento e Toolsmith | 13 | | | | |
| J Dataset e T3 | 8 | | | | |
| K Contabilità ERP | 17 | | | | |
| L Log e diagnosi | 11 | | | | |
| M Robustezza e audit | 9 | | | | |
| **Totale** | **173** | | | | |

**Ambiente usato:** ☐ A locale ☐ B Docker
**Modello T1:** ______________ **T2:** ______________ **T3:** ______________
**Parser documenti (Docling):** ☐ acceso ☐ spento
**ERPNext:** ☐ collegato ☐ spento — versione: ______________
**Data:** ____ / ____ / ________ **Eseguito da:** ______________________

### KO da riportare

| Caso | Cosa hai visto | Riproducibile | Gravità |
|---|---|---|---|
| | | ☐ sì ☐ no | ☐ blocca ☐ grave ☐ minore |
| | | ☐ sì ☐ no | ☐ blocca ☐ grave ☐ minore |
| | | ☐ sì ☐ no | ☐ blocca ☐ grave ☐ minore |
| | | ☐ sì ☐ no | ☐ blocca ☐ grave ☐ minore |
