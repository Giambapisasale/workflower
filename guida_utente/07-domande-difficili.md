# Le domande difficili

Quelle che arrivano davvero, e la risposta onesta. Dove il prodotto ha un limite,
è scritto: una demo che promette troppo si paga al collaudo.

---

### «E se sbaglia a leggere un numero?»

Succede, ed è previsto. Il sistema dichiara una **confidenza per campo**: sotto
la soglia del workflow (0,90 per le fatture) il documento va in revisione e
quel campo è evidenziato.

Poi ci sono le regole del workflow: su una fattura viene verificato che totale =
imponibile + IVA e che la data non sia nel futuro. Se non torna, il sistema
rilegge il documento prima di consegnare.

Mostra l'esempio `07`: il totale stampato è sbagliato, il sistema se ne accorge,
rilegge, e conclude dichiarando confidenza 0,6.

**Il limite, detto chiaro:** nessun documento entra nei costi senza che una
persona lo abbia validato. Il sistema toglie la digitazione, non il controllo.

---

### «I nostri dati escono dall'azienda?»

Oggi, nella configurazione standard, i documenti vengono letti da un modello di
un fornitore esterno. Va detto senza giri di parole.

Ma:

- **il parser dei documenti gira già dentro l'azienda**, su GPU vostra;
- l'architettura ha **tre livelli di modello** configurabili, e il terzo è
  pensato per un modello locale;
- in **Sistema → Dataset** c'è una misura di quanto un modello locale sarebbe già
  bravo, sui vostri casi validati. Non è una promessa: è un numero che potete
  guardare prima di decidere;
- nel registro delle esecuzioni i testi lunghi non sono conservati per intero, ma
  come lunghezza e impronta.

L'infrastruttura di riferimento è on-premise con GPU NVIDIA. Il percorso per non
far uscire niente è tracciato e misurato; la data la decidete voi.

---

### «Quanto costa farlo funzionare?»

Il costo si vede documento per documento, in Sistema → Run.

Misure reali sugli esempi di questa guida, con il modello di punta:

| Documento | Costo |
|---|---|
| Fattura normale (PDF o Word) | 2,5 centesimi |
| Fattura fotografata | 3,8 centesimi |
| DDT, SAL, rapportino | 1,3 – 2,6 centesimi |
| Fattura con i conti sbagliati (rilettura) | 10,5 centesimi |

Ordine di grandezza: **circa 3 centesimi a documento**. Mille documenti al mese
sono una trentina di euro di modello. Il conto vero è l'altro: quante ore di
digitazione spariscono.

Con il tier locale, questo costo tende a zero e resta l'energia.

---

### «Chi ci dice che l'AI non si inventa i numeri?»

Tre risposte, in ordine di forza.

1. **Le ricerche non le fa il modello.** Fornitore, cantiere, dipendenti: li
   cerca uno strumento deterministico in anagrafica, e restituisce candidati con
   un punteggio. Il modello sceglie fra quelli, e se nessuno è affidabile lascia
   il campo vuoto invece di indovinare.
2. **Ogni esecuzione è ispezionabile.** Nel trace c'è quale strumento ha
   chiamato, con che argomenti, cosa ha risposto. Non è una scatola nera:
   è un verbale.
3. **Le modifiche al comportamento passano da un esame.** Una nuova versione
   delle istruzioni viene rigiocata su tutti i documenti già validati, e i
   risultati si vedono prima di approvarla.

E l'esempio `06`: il fornitore non è in anagrafica, e il sistema **non se lo
inventa**. Lascia il collegamento vuoto e mette da parte quello che ha letto,
perché sia una persona a creare l'anagrafica.

---

### «Funziona con le nostre fatture, che sono fatte diversamente?»

Le fatture italiane si somigliano più di quanto sembri, e il sistema non cerca
posizioni fisse sulla pagina: legge. Nella guida ci sono cinque intestazioni
diverse, in PDF, Word e foto.

**Il modo onesto di rispondere è non rispondere:** *mandateci dieci vostre
fatture vere, ve le facciamo vedere lette.* È mezz'ora di lavoro e vale più di
qualunque affermazione. E se qualcosa non torna, si aggiusta scrivendo due righe
nelle istruzioni — non ricompilando il prodotto.

---

### «E se cambia il formato di un fornitore?»

Non succede niente di speciale: non c'è un modello addestrato su quel layout da
riaddestrare. Se la lettura peggiora, l'ufficio lascia una nota, il sistema
propone una modifica alle istruzioni, e si approva.

Questo è il motivo per cui le istruzioni sono un testo e non codice.

---

### «Cosa succede se il sistema è giù, o se il modello non risponde?»

L'operatore non vede mai un errore tecnico: il documento viene preso in carico e
lavorato dopo. Se proprio non si riesce, nasce una segnalazione per l'ufficio.

Se manca il parser su GPU, i PDF e le foto continuano a funzionare: si perdono
Word ed Excel, che vengono rifiutati con un messaggio chiaro invece di essere
accettati e poi falliti.

**Il limite:** senza il modello, i documenti si accumulano e non vengono letti.
Non c'è una modalità «digitazione manuale di emergenza» nella UI operatore —
l'ufficio può però inserire i dati a mano da Operatività → Dati.

---

### «Possiamo tenerlo insieme al nostro gestionale?»

Sì, ed è il modo previsto: Workflower fa il controllo di gestione di cantiere e
manda i documenti validati al gestionale. L'integrazione realizzata è verso
**ERPNext**; il punto di attacco è isolato, quindi un altro gestionale è lavoro,
non riprogettazione.

Regola ferma: **niente si sincronizza senza validazione umana**. Il dettaglio di
cosa passa il confine (fatture e DDT) e cosa resta di qua (computo, ore, mezzi,
SAL) è in [08-contabilita-erpnext.md](08-contabilita-erpnext.md).

---

### «Se domani vi lasciamo, i dati restano nostri?»

Sì, e in un formato che non richiede noi per essere letto.

Lo stato del sistema è **un repo git di file JSON** su un disco vostro. Nessun
database proprietario, nessun formato binario. Si può copiare, versionare,
`git push` altrove come backup, e leggere con un editor di testo.

In più c'è l'esportazione in Excel di tutto il controllo costi, e i dati grezzi
delle elaborazioni sono file `.jsonl` scaricabili.

---

### «Quanto ci mettiamo a partire?»

Le cose che servono davvero prima di caricare il primo documento sono tre:
l'anagrafica dei cantieri, quella dei fornitori principali, e i dipendenti con la
loro tariffa oraria.

Il computo metrico serve solo per gli scostamenti: senza, si parte lo stesso e si
vedono i consuntivi.

**Il limite onesto:** i primi documenti richiedono più revisione, perché
l'anagrafica è vuota e ogni fornitore è nuovo. Dopo qualche decina, la maggior
parte dei riferimenti si risolve da sola.

---

### «Chi ci garantisce che una modifica non peggiori le cose?»

Nessun cambiamento alle istruzioni entra in produzione senza:

1. essere rigiocato su **tutti** i casi già validati,
2. mostrare il risultato di quella rigiocata,
3. essere approvato da una persona con un clic.

E se dopo l'approvazione ci si accorge che era sbagliata, si annulla: è un commit
come gli altri.

---

### «Perché non usate semplicemente ChatGPT sulle fatture?»

Perché il problema non è leggere una fattura: è **collegarla ai vostri dati** —
questo fornitore, questo cantiere, questa voce di computo — e farlo in modo
verificabile e ripetibile.

Un modello generico non sa che «Calcestruzzi Etna» è il vostro FRN-002, non tiene
un registro di chi ha validato cosa, non si misura sui vostri casi, e non produce
uno scostamento rispetto al computo.

La parte di lettura è la più facile del problema. È il resto che è il prodotto.
