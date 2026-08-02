# Il copione — trenta minuti

Ordine studiato: prima il dolore che il cliente conosce, poi la soluzione, poi la
prova che ci si può fidare. Le parti in *corsivo* sono cose da dire, non da
leggere.

Prima di cominciare: la checklist in
[00-preparare-la-demo.md](00-preparare-la-demo.md).

---

## 0. Prima di accendere lo schermo — 2 minuti

Una domanda sola, e poi si ascolta:

> *Oggi, una fattura che arriva in cantiere, come finisce nei costi della
> commessa? Chi la digita, e quanto tempo dopo?*

La risposta serve per tutto il resto: userai le loro parole, non le nostre. Se
dicono «la porta il capocantiere in ufficio il venerdì», hai già il problema da
attaccare.

---

## 1. Il cantiere — 5 minuti

Login come **`salvo` / `1111`**. Schermo del telefono se puoi, o finestra stretta.

> *Questo è quello che vede chi sta in cantiere. Quattro bottoni. Non c'è
> formazione da fare.*

**Carica un documento** → `esempi/01-fattura-digitale.pdf`.

Mentre elabora, far notare la frase *«Puoi anche uscire: lo trovi tra poco in I
miei documenti»*.

> *Non lo obblighiamo a stare fermo ad aspettare. Ha altro da fare.*

Quando compare **Ho letto: fattura!** con fornitore, cantiere e importi:

> *Nessuno ha digitato niente. E badate: non gli stiamo chiedendo di validare.
> Gli chiediamo solo se gli sembra giusto. La responsabilità resta all'ufficio.*

**Poi la foto storta** → `esempi/04-fattura-foto.jpg`.

> *Questa è una foto fatta col telefono, storta. Nessuno scanner.*

**E il Word** → `esempi/03-fattura-word.docx`.

> *E questo è un file Word. Nessun modello che «guarda» le pagine sa aprirlo: qui
> gira un parser su scheda grafica, in azienda, che ricostruisce anche le
> tabelle.*

**Le mie ore**, due passi e si torna indietro:

> *Stessa filosofia: una domanda alla volta, mai un modulo.*

---

## 2. L'ufficio — 8 minuti

Login come **`giovanna` / `9999`**.

**Cruscotto**:

> *Questi numeri arrivano tutti da documenti fotografati e validati. Non c'è un
> dato digitato a mano.*

**Revisione** → aprire `07-fattura-totale-sbagliato`.

> *Guardate il campo totale: confidenza 0,6, tutti gli altri 1,0. Il sistema
> dichiara dove non è sicuro, campo per campo.*

**Mostra trace**:

> *E qui c'è cosa ha fatto davvero: ha letto il documento, si è accorto che il
> totale stampato non corrisponde a imponibile più IVA, ha riletto, e alla fine
> ha detto «non sono sicuro». Non ha buttato il documento, e non ha nemmeno
> deciso da solo.*

**Poi `05-fattura-intestata-ad-altri`**:

> *Questa è perfetta: numeri giusti, fornitore giusto, cantiere giusto. Solo che
> è intestata a un'altra impresa.*

Aprire la segnalazione e leggerla:

> *Il documento risulta intestato a Costruzioni Delta, non a Costruzioni Aitho.*

> *Registrata comunque — perché capita che un fornitore sbagli intestazione e
> bloccare farebbe più danni — ma segnalata.*

**Chiudere con la validazione** di un documento pulito:

> *E quando l'ufficio valida, succede una terza cosa oltre a far entrare il dato
> nei costi: quel documento diventa un caso di prova permanente. Ci torniamo.*

---

## 3. Il controllo costi — 5 minuti

**Cantiere** (dal cruscotto) → **Scostamenti**:

> *Qui non c'è più «quanto ho speso»: c'è «dove sto sforando rispetto al
> computo, e di quanto». È la differenza fra archiviare documenti e controllare
> una commessa.*

**Interroga**, una domanda facile e una difficile:

- «Quanto abbiamo speso per cantiere?»
- «Su quali voci di computo stiamo sforando?»

Indicare la query stampata:

> *Questa è la domanda tradotta in interrogazione. È scritta, è leggibile, ed è
> in sola lettura. Se non vi fidate della risposta, potete controllare come ci è
> arrivata.*

Poi la domanda che non ha risposta:

- «Quanto guadagneremo su questo cantiere?»

> *Non lo sa, e ve lo dice. Nei dati ci sono i costi, non i ricavi. Preferiamo
> un «non lo so» a un numero inventato.*

**Scarica report Excel**:

> *E se volete rigirarvi i dati per conto vostro, sono vostri.*

---

## 4. Perché fidarsi — 7 minuti

È la parte che chiude la vendita. **Sistema → Workflows.**

Aprire la skill di `carica-fattura` e leggere due righe ad alta voce:

> *Questo è quello che il sistema sa fare, e non è codice: è un testo in
> italiano. Il vostro capocommessa può leggerlo. E se sbaglia, si corregge qui.*

Poi il ciclo completo:

> *La ritenuta d'acconto: all'inizio il sistema la ignorava. L'ufficio ha
> lasciato una nota su quel campo. Il sistema ha proposto una modifica alle
> proprie istruzioni — questa qui, con il confronto riga per riga. Prima di
> proporla se l'è misurata da sola su tutti i documenti già validati, per
> verificare di non romperne nessuno. E poi ha aspettato che un umano cliccasse
> Approva.*

Indicare il numero dei casi golden:

> *Centosessantaquattro casi di prova, che non abbiamo scritto noi: li ha
> prodotti l'uso. Ogni documento che validate diventa un esame che il sistema
> dovrà superare per sempre.*

**Sistema → Dataset**, il riquadro dell'idoneità del modello locale:

> *E questa è la risposta alla domanda che state per farmi. Misuriamo se un
> modello che gira dentro la vostra azienda, senza mandare fuori niente, è già
> abbastanza bravo per questo lavoro. Non è una promessa: è un numero.*

---

## 5. Chiudere — 3 minuti

Non chiudere sulla tecnologia. Chiudere su di loro:

> *Se doveste partire, con quale cantiere partireste?*

> *Chi, da voi, farebbe il lavoro dell'ufficio in questo sistema?*

> *Quante fatture di cantiere vi passano in un mese?*

L'ultima serve anche a te: moltiplicata per tre centesimi dà il costo di
esercizio, e conviene dirlo prima che lo chiedano.

---

## Se hai solo dieci minuti

1. `01-fattura-digitale.pdf` dal lato operatore — 2 minuti
2. `05-fattura-intestata-ad-altri.pdf` e la sua segnalazione — 3 minuti
3. Il diff di una patch in Sistema → Workflows — 3 minuti
4. Le due domande in Interroga, quella che funziona e quella che non sa — 2 minuti

## Se hai un'ora

Aggiungi, in quest'ordine: il parser Word spento e poi acceso; il collegamento al
computo e lo scostamento che ne esce; la creazione di un fornitore dai dati letti
sulla fattura; il trace completo di un documento; la pagina Log; e la
sincronizzazione verso la contabilità — quest'ultima ha il suo pezzo di copione
in [08-contabilita-erpnext.md](08-contabilita-erpnext.md), caso 10.
