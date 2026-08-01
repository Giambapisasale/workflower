# La contabilità: cosa va in ERPNext e cosa resta qui

La domanda che arriva sempre, prima o poi: *«e alla fine, dove ritrovo i miei
dati?»*. Questo capitolo risponde per intero — quando parte la sincronizzazione,
cosa parte, cosa **non** parte e perché, e dove si va a guardare.

La regola che tiene insieme tutto, da dire subito:

> **Niente arriva in contabilità senza essere passato da una validazione umana.**
> E niente torna indietro dall'ERP tranne lo stato di pagamento, in sola lettura.

---

## Il confine: chi possiede cosa

Non sono due copie dello stesso archivio. Sono due sistemi con due mestieri.

| | Workflower | ERPNext |
|---|---|---|
| Possiede | il **documento**: com'era, cosa c'era scritto, chi l'ha letto, con che confidenza, chi l'ha validato | la **contabilità**: partita doppia, IVA, ritenute, scadenzario, pagamenti |
| Possiede anche | il **controllo di cantiere**: computo, scostamenti, ore, costo pieno dei mezzi | il bilancio dell'impresa |
| Non fa | la registrazione contabile | non sa niente di computo metrico, rapportini, targhe |

Workflower è il sistema di partenza dei documenti; ERPNext è quello di arrivo dei
**costi del ciclo passivo**. Il flusso è **mono-direzionale**: WF → ERP.

---

## Caso 1 — Quando avviene la sincronizzazione

**Al momento della validazione**, in Revisione, quando l'ufficio preme *Salva
come validato*. Non c'è un orario notturno, non c'è un bottone «sincronizza
adesso» da ricordarsi: il documento parte da solo, subito, come effetto del sì
dell'ufficio.

Attorno a quel momento ci sono quattro garanzie che vale la pena conoscere:

- **Solo fatture e DDT.** Gli altri tipi di documento non vanno a valle (sotto
  c'è la mappa completa: [Caso 3](#caso-3--la-mappa-completa-dove-finisce-ogni-cosa)).
- **Best-effort.** Se l'ERP è spento, irraggiungibile o rifiuta il documento, la
  **validazione resta valida**: si apre una segnalazione, si scrive la riga
  d'errore nel registro, e il documento finisce nella lista dei «rimasti
  indietro». Non si perde niente e non si blocca l'ufficio.
- **Idempotente.** Un documento già arrivato a valle non viene reinviato mai
  più, nemmeno se si preme *Riprova*: se ne accorge dal riferimento che si è
  tenuto.
- **Il modello non scrive nell'ERP.** La sincronizzazione è codice, non una
  facoltà dell'intelligenza artificiale. Nessun prompt può decidere di creare
  una fattura in contabilità: è una scelta di progetto, ed è la risposta giusta
  quando in demo qualcuno alza il sopracciglio.

Se l'integrazione è **spenta** (credenziali non configurate) tutto questo
semplicemente non accade, in silenzio: Workflower funziona esattamente come
prima e i documenti validati restano qui.

---

## Caso 2 — In che stato arrivano i documenti

Questa è la cosa che sorprende il commercialista, quindi meglio dirla prima:
**i documenti arrivano in ERPNext come bozze**, non confermati.

In Frappe/ERPNext una bozza (`docstatus 0`) non ha ancora toccato i conti: è un
documento compilato che aspetta il *Submit*. Workflower si ferma lì di proposito.
La lettura del documento e il controllo di cantiere li fa lui; la scrittura in
partita doppia resta un gesto della contabilità, che apre la bozza, la guarda e
la conferma.

Chi si aspettava di trovare le fatture già registrate deve saperlo in anticipo:
il passaggio in più esiste, ed è voluto.

---

## Caso 3 — La mappa completa: dove finisce ogni cosa

Questa tabella è la risposta letterale a «dove ritrovo tutti i miei dati».

### Va in ERPNext

| In Workflower | Diventa in ERPNext | Quando | Come lo ritrovi |
|---|---|---|---|
| **Fattura** | **Purchase Invoice** (bozza) | alla validazione | `/app/purchase-invoice` |
| **DDT** | **Purchase Receipt** (bozza) | alla validazione | `/app/purchase-receipt` |
| **Fornitore** | **Supplier** | quando serve a una fattura o a un DDT | `/app/supplier` |
| **Cantiere** | **Cost Center** | quando serve a una fattura o a un DDT | `/app/cost-center` |

Fornitori e cantieri non partono da soli: vengono creati **a traino** del primo
documento che li nomina. Un cantiere in anagrafica che non ha ancora ricevuto
una fattura non esiste a valle, ed è corretto così.

I documenti si guardano nella **scrivania** di ERPNext, cioè sotto `/app`. La
radice del sito (`http://…:8080/`) è il portale per fornitori e clienti e
risponde 403 sui documenti: è la prima cosa su cui ci si sbaglia.

### Resta in Workflower, e non ci va mai

| Dato | Perché resta qui |
|---|---|
| **SAL** | è avanzamento lavori, non un documento contabile passivo |
| **Rapportini e ore** | il costo manodopera è controllo di gestione; a valle andrebbe come paghe, che è un altro ciclo |
| **Computo metrico** e voci | la previsione non esiste nel piano dei conti |
| **Mezzi**, manutenzioni, costo pieno | l'ERP non ha il concetto di «costo pieno della macchina operatrice» |
| **Materiali, lavorazioni, scadenze, pozzetti, cronoprogrammi** | entità di cantiere, nate per il controllo, non per la contabilità |
| **Dipendenti** | anagrafica interna al controllo ore |
| **Documenti generici** | archivio |
| **Scartati** | per definizione non devono entrare nei conti |

### Torna dall'ERP

| Cosa | Come | Dove lo vedi |
|---|---|---|
| **Stato di pagamento** delle fatture sincronizzate | rilettura manuale, sola lettura | entità `pagamento`, vista `v_pagamenti`, Operatività → Dati → Pagamenti |

### Cosa non attraversa il confine, dentro un documento che parte

Anche di una fattura che va a valle, non tutto passa. Restano di qua:

- il collegamento **riga → voce di computo** e **riga → mezzo**, e la
  classificazione del tipo di costo: sono l'analisi di cantiere, non servono al
  libro giornale;
- le **confidenze per campo** e la provenienza (da quale documento, quale run,
  quale pagina viene ogni valore);
- l'**indirizzo del fornitore**: in ERPNext è un documento separato (Address) e
  non viene creato.

Nessuna di queste è una perdita: è il confine tenuto pulito. Se domani si cambia
gestionale, quello che si rifà è la traduzione, non l'archivio.

---

## Caso 4 — Come viene tradotta una fattura

Utile saperlo prima di aprire la Purchase Invoice davanti a un cliente, perché
qualche campo si chiama diversamente da come ce lo si aspetta.

| Sulla fattura | Nella Purchase Invoice |
|---|---|
| numero | `bill_no` (numero del fornitore, non il numero ERPNext) |
| data | `bill_date` |
| fornitore | `supplier`, cercato **per partita IVA** e creato se non c'è |
| cantiere | `cost_center` su ogni riga |
| righe (descrizione, quantità, importo) | righe con `qty` e `rate` ricavato, così che quantità × prezzo faccia esattamente l'importo letto |
| IVA | riga di imposta **in aggiunta**, con l'importo esatto letto sul documento |
| **ritenuta d'acconto** | riga di imposta **in detrazione**, con l'importo esatto letto sul documento |

La ritenuta è il caso che vale la pena mostrare: è lo stesso scenario che nella
demo dimostra che il sistema impara (`esempi/02-fattura-con-ritenuta.pdf`), e
arriva a valle come detrazione con la cifra estratta dal documento — non
ricalcolata. Se non è stato configurato il conto della ritenuta, Workflower
lascia che sia ERPNext a calcolarla dalla categoria del fornitore.

Il **DDT** diventa una Purchase Receipt **senza importi**: descrizione, quantità,
cantiere. La merce si valorizza in fattura, non in bolla — è la logica di
ERPNext, e Workflower la rispetta.

Una nota onesta sui fornitori: l'aggancio è la **partita IVA**. Un fornitore che
in anagrafica non ce l'ha viene creato a valle come nuovo ogni volta. Compilare
la partita IVA in Operatività → Dati → Fornitori è quello che rende il
collegamento stabile.

---

## Caso 5 — Il pannello: cosa è arrivato e cosa no

**Operatività → Contabilità** (`/admin/erp`). Il flusso normale è automatico,
quindi questa pagina si apre soprattutto quando qualcosa **non** è arrivato.

- **I contatori**, uno per tipo: `sincronizzate / validate`, con «tutti a
  destinazione» oppure «N da re-inviare».
- **Rimasti indietro**: l'elenco dei documenti validati che non sono passati,
  ognuno con il suo **Riprova**. E **Re-invia gli arretrati** per farli tutti in
  blocco — quando l'ERP torna su dopo un fermo, è il bottone giusto.
- **Registro dei tentativi**: ogni invio, riuscito o fallito, con quando, quale
  documento, e in caso di errore **il motivo per esteso**. È l'audit trail, e
  vive anche come file (`data/dataset/erp_sync.jsonl`), versionato in git come
  ogni altra mutazione.
- **Rileggi i pagamenti**, per il ritorno dall'ERP (Caso 6).

Il re-invio in blocco **si ferma da solo** dopo cinque fallimenti di fila: se
l'ERP è giù, non ha senso martellarlo con trecento documenti. Lo dice in chiaro:
«Interrotto: l'ERP sembra non raggiungibile, riprova più tardi».

Con l'integrazione spenta la pagina lo dichiara e non mostra azioni — resta
visibile lo storico.

Gli stessi esiti finiscono anche in **Sistema → Log** (fase `erp`): successi come
informazione, fallimenti come errore con il dettaglio tecnico. Serve quando il
motivo scritto nel registro non basta.

---

## Caso 6 — I pagamenti che tornano indietro

L'unico flusso ERP → Workflower, ed è **in sola lettura**.

Il bottone **Rileggi i pagamenti** interroga a valle ogni fattura sincronizzata,
guarda quanto è ancora scoperto, e ne ricava lo stato: `pagato`, `parziale`,
`non_pagato`, con l'importo pagato. Il risultato diventa un'entità `pagamento`
per fattura, aggiornata se già esiste.

Da lì è un dato come gli altri: si vede in Operatività → Dati → Pagamenti, si
interroga a parole in **Interroga** («quali fatture non abbiamo ancora pagato?»),
entra nelle viste `v_pagamenti` e `v_fatture_saldo`.

Da dire con onestà in demo: **la rilettura è manuale**. Non c'è ancora un giro
notturno che la faccia da sé; è un clic, e chi vuole automatizzarlo lo fa con
una chiamata pianificata a `POST /api/erp/rileggi-pagamenti`.

---

## Caso 7 — Scartare un documento già arrivato a valle

Se l'ufficio scarta un documento che è **già** in contabilità, Workflower si
rifiuta e spiega perché: scartarlo qui e lasciarlo vivo là lascerebbe due verità
in disaccordo, e il disaccordo lo scoprirebbe il commercialista.

Prima si sistema a valle, poi si scarta qui. Cosa fare dipende dallo stato del
documento in ERPNext, e Workflower lo **verifica leggendolo**:

| Stato in ERPNext | Cosa fare là | Scarto qui |
|---|---|---|
| Bozza (è come nasce da qui) | **eliminala** — una bozza non si annulla | bloccato |
| Confermata (è nei conti) | **annullala** (*Cancel*) | bloccato |
| Già annullata | niente | permesso |
| Non c'è più | niente | permesso |
| ERP irraggiungibile o spento | riprovare quando risponde | bloccato |

Workflower **non scrive annullamenti** nell'ERP, nemmeno per comodità: la
scrittura verso valle resta l'effetto della sola validazione. Bloccare è la
scelta prudente, ed è deliberata.

---

## Caso 8 — Dove ritrovo i miei dati, in generale

Riassunto per chi fa la domanda in senso largo, non solo sull'ERP. I dati stanno
in **quattro posti**, e tutti e quattro sono leggibili senza di noi:

1. **Il repo dati** (`data/`): un archivio di file JSON in git. Ogni documento
   con la sua storia, ogni modifica con autore e data. Si legge con un editor di
   testo, si annulla con git.
2. **Le viste** (`v_fatture`, `v_cantiere_costi`, `v_scostamento_voci`,
   `v_mezzi_tco`, `v_pagamenti`, …): trenta viste in sola lettura su cui girano
   cruscotto, scostamenti e Interroga. Sono SQL, e sono nel repo.
3. **I report Excel**: scaricabili dal cantiere, con i fogli su costi, mezzi e
   scostamenti. È la via per «rigirarseli per conto proprio».
4. **ERPNext**, per la parte contabile: fatture, bolle, fornitori, centri di
   costo, e da lì tutto quello che l'ERP sa fare (registro IVA, scadenzario,
   bilancio).

---

## Caso 9 — Accendere l'integrazione per una demo

Serve solo se vuoi **mostrare** la contabilità: senza, il resto della demo
funziona identico.

```bash
make erp-up
```

Alza un ERPNext di sviluppo in Docker. La prima volta scarica le immagini e crea
il sito: qualche minuto. Poi sta su `http://localhost:8080/app`, utente
`Administrator`, password `admin`.

```bash
make erp-dev-setup
```

Prepara azienda, conti, articolo generico per i DDT e chiavi API, e **stampa due
blocchi di variabili**: uno da incollare nel `.env` (lo legge l'applicazione),
uno da esportare nella shell (lo usano lo smoke test e i test). Servono
entrambi. Senza il primo, l'integrazione parte **spenta senza dirlo** — è
l'errore più frequente.

```bash
make erp-smoke
```

Verifica il collegamento senza scrivere codice: connettività, creazione di un
fornitore, di un centro di costo. Con `ARGS=--full` prova anche una fattura con
ritenuta. Da fare **prima** della demo, non davanti al cliente.

Due trappole note:

- Se l'applicazione gira in container e ERPNext è sullo stesso computer,
  `ERP_BASE_URL` deve puntare a `host.docker.internal:8080`: dentro al container
  `localhost` è il container stesso.
- Una variabile `ERP_*` già presente nella shell **vince** su quella del `.env`.
  Per spegnere davvero l'integrazione, il comando di pulizia è in
  [00-preparare-la-demo.md](00-preparare-la-demo.md).

Dettagli, alternative e triage: `docs/erp-integrazione.md`, `docs/erp-poc.md`,
`docs/erp-test-plan.md`.

---

## Caso 10 — Un pezzo di demo, in tre minuti

Da inserire dopo la validazione (parte 2 del [copione](06-copione-demo.md)), se
l'ERP è acceso:

1. Valida `esempi/02-fattura-con-ritenuta.pdf`.
2. **Operatività → Contabilità**: il contatore è salito, e nel registro c'è la
   riga «arrivato» con il codice del documento a valle.

   > *Non ho premuto nessun bottone di invio. È partito perché l'ufficio ha detto
   > sì, e solo per quello.*

3. Apri ERPNext su `/app/purchase-invoice` e mostra la fattura, con la ritenuta
   in detrazione e il centro di costo del cantiere.

   > *È una bozza. Il vostro commercialista la apre, la guarda, e la conferma
   > lui. Noi non registriamo niente al posto suo.*

4. Se hai un minuto in più: spegni l'ERP (`make erp-down`), valida un altro
   documento, torna sul pannello.

   > *La validazione è passata lo stesso. Il documento è qui, nella lista dei
   > rimasti indietro, con scritto perché. Quando l'ERP torna, un clic e recupera
   > gli arretrati.*

   È la dimostrazione più convincente di tutta la parte contabile: un sistema a
   valle che cade non deve fermare l'ufficio.

---

## I limiti, detti prima che li scoprano

- **Solo ciclo passivo.** Fatture e bolle in entrata. L'emissione elettronica
  verso SdI e il ciclo attivo sono fuori scope.
- **Documenti come bozze**, da confermare in ERPNext (Caso 2).
- **Rilettura pagamenti manuale** (Caso 6).
- **I DDT hanno bisogno di un articolo generico** configurato: ERPNext pretende
  un codice articolo sulle righe di magazzino, e i DDT di cantiere descrivono a
  parole. Se manca, il singolo DDT non passa e il messaggio dice esattamente
  cosa impostare — la validazione regge lo stesso.
- **Senza azienda configurata** a valle non si creano centri di costo: le righe
  arrivano senza cantiere invece di far fallire l'invio.
- **Un solo gestionale integrato**, ERPNext. La traduzione documento → gestionale
  è isolata in un punto solo: un altro ERP è lavoro, non riprogettazione.
