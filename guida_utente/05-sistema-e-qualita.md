# L'ufficio: sistema e qualità

Il menu **Sistema** è quello che nessun concorrente ha. Non serve a far
funzionare il prodotto: serve a **dimostrare che funziona**, e a farlo migliorare
sotto controllo umano.

In una demo commerciale è la seconda metà. La prima metà (documenti, costi)
convince che il prodotto è utile; questa convince che ci si può fidare.

---

## Caso 1 — I workflow, cioè le istruzioni

**Sistema → Workflows.** Ogni tipo di documento ha un workflow, e ogni workflow è
fatto di due cose leggibili da un umano:

- un **manifest**, che dice quali passi fare, quali strumenti mettere a
  disposizione, quali regole di validazione applicare e sotto quale confidenza
  chiedere aiuto;
- una **skill**, cioè le istruzioni vere e proprie, scritte in italiano.

La frase da dire: *questo non è codice. È un testo in italiano che un
capocommessa può leggere, e se serve correggere.*

Aprire la skill di `carica-fattura` e leggerne un pezzo ad alta voce — per
esempio la regola sui riferimenti non risolti, o quella sui mezzi — di solito
cambia il tono della riunione.

---

## Caso 2 — Il ciclo di miglioramento

È la storia migliore che il prodotto abbia, e va raccontata per intero.

1. **L'ufficio corregge.** Su un campo sbagliato lascia una nota in revisione:
   «manca la ritenuta d'acconto indicata in calce». Oppure, dal riquadro
   «Migliora il workflow» in fondo alla stessa pagina, detta direttamente la
   regola che vorrebbe: *«se la ritenuta è in calce e non nel riepilogo, leggila
   comunque»*.
2. **Il sistema propone.** Dal bottone **Proponi miglioramento** — o quando le
   note raccolte bastano — nasce una **patch**: una nuova versione delle
   istruzioni, con il confronto riga per riga rispetto a quella attuale.
3. **Il sistema si misura da solo.** Prima di proporla, rigioca la versione
   candidata su **tutti i casi già validati** e dice quanti continuano a venire
   uguali. Una modifica che sistema un caso ma ne rompe altri tre si vede subito.
4. **Un umano decide.** Bottoni **Approva** e **Rifiuta**. Niente si applica da
   solo. Se approvata, la versione del workflow passa da 1.0 a 1.1, e la modifica
   è un commit che si può annullare.

**Da mostrare in demo:** il pannello «Patch in attesa» col diff. Se non ce n'è
una pronta, si genera prima lasciando due o tre note su un campo.

Questo è il punto in cui rispondere all'obiezione «l'AI allucina»: qui una
modifica al comportamento del sistema **non può entrare** senza aver superato i
casi già validati e senza che un umano abbia cliccato Approva.

---

## Caso 3 — La rete di regressione

Sempre in **Sistema → Workflows**, il riquadro «Casi golden — la rete di
regressione».

Ogni documento validato dall'ufficio diventa un caso: documento di partenza più
risultato atteso. Sono la misura contro cui si giudica ogni cambiamento.

Numeri attuali dell'ambiente d'esempio: **164 casi**, di cui 74 estrazioni di
documenti e 90 interrogazioni.

Da dire: *questi non li abbiamo scritti noi. Li ha prodotti l'uso normale del
sistema: ogni volta che l'ufficio valida un documento, il sistema guadagna un
esame che dovrà superare per sempre.*

---

## Caso 4 — Le esecuzioni

**Sistema → Run.** L'elenco delle elaborazioni, ognuna apribile.

Dentro c'è tutto: gli strumenti chiamati con argomenti e risposte, le chiamate al
modello con token e costo, le regole di validazione con esito, le note lasciate
dall'operatore e dall'ufficio.

Due cose da far notare:

- **il costo per documento è visibile**, voce per voce. Sugli esempi di questa
  guida va da 1,3 a 10,5 centesimi. Un cliente che chiede «quanto mi costa» ha
  una risposta misurata, non un listino;
- **i testi lunghi non sono conservati per intero** ma sostituiti da lunghezza e
  impronta. Serve a non trasformare il registro in un archivio parallelo di dati
  personali.

---

## Caso 5 — Strumenti

**Sistema → Skills & Tools.** Cosa il modello può fare, su *questa* macchina.

Gli strumenti sono funzioni deterministiche: cercare un fornitore, cercare un
cantiere, leggere un documento, calcolare una ritenuta. Il modello sceglie quale
usare; il risultato non se lo inventa lui.

L'elenco è onesto rispetto alla configurazione: se il parser su GPU è spento,
`leggi_documento` **non compare**, perché su questa macchina non esiste.

C'è anche il **Toolsmith**: quando una lavorazione si ripete sempre uguale, il
sistema può proporre di trasformarla in uno strumento vero e proprio — codice,
che un umano approva e che gira isolato. È il percorso «prima lo fa il modello,
poi lo fa una funzione»: più veloce, più economico, sempre uguale.

---

## Caso 6 — Dataset e idoneità del modello locale

**Sistema → Dataset.** Due cose, entrambe vendibili.

**«Idoneità T3 — il modello locale».** Misura se un modello che gira in azienda,
senza mandare niente fuori, sarebbe già abbastanza bravo per fare il lavoro. Il
bottone lancia la misura sui casi golden e dice quali workflow sono **pronti** e
quali darebbero **regressioni**.

È la risposta pronta alla domanda «i nostri dati escono dall'azienda?»: la strada
per non farli uscire è tracciata e **misurata**, non promessa.

**«Query di Interroga per fingerprint».** Le domande fatte al sistema,
raggruppate per struttura. I gruppi che si ripetono sono i candidati a diventare
una vista o uno strumento: il sistema osserva cosa gli viene chiesto davvero e
suggerisce dove conviene cristallizzare.

---

## Caso 7 — Diagnosi automatica

**Sistema → Diagnosi.** Quando un errore si ripete, il sistema lo raggruppa per
impronta e apre una **diagnosi**: cosa sta succedendo, quante volte, e — leggendo
il proprio codice — dove sta probabilmente il problema.

Non corregge niente da solo. Scrive una proposta che un umano legge.

Da mostrare solo se ce n'è una aperta: se la lista è vuota, dirlo e passare oltre
è meglio che fabbricarne una.

---

## Caso 8 — Log

**Sistema → Log.** Il registro applicativo, filtrabile per livello, per periodo e
per testo, con il livello di dettaglio regolabile dalla pagina stessa.

Serve durante l'installazione e quando qualcosa non va. In demo si mostra in
trenta secondi, per dire una cosa sola: *quando qualcosa non funziona, si vede
dov'è, senza chiamarci.*

---

## Cosa c'è sotto (per il cliente tecnico)

Se in sala c'è un informatico, questi quattro punti gli interessano:

- **Nessun database.** Lo stato del sistema è un repo git di file JSON. Ogni
  modifica è un commit con autore e data; il backup è un `git push`; il ripristino
  è un `git checkout`. Le interrogazioni girano in sola lettura su viste.
- **I modelli non sono cablati.** Sono variabili d'ambiente, su tre livelli. Si
  cambia fornitore senza toccare il codice, e il livello T3 è pensato per un
  modello locale.
- **Aggiungere un tipo di documento è dato, non codice.** Uno schema, una riga di
  registro, una vista, un manifest e una skill. Il motore non si tocca.
- **Il codice generato non viene mai importato nel processo.** Gli strumenti
  costruiti dal Toolsmith sono file versionati, approvati da un umano, eseguiti in
  un ambiente isolato.
