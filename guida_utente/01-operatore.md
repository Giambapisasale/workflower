# L'operatore: chi sta in cantiere

Quattro bottoni, nessun modulo, una domanda alla volta. Chi usa questa parte non
riceve formazione: se serve spiegargliela, è progettata male.

Si entra da `/op` con nome utente e codice (`salvo` / `1111`).

---

## Caso 1 — Caricare un documento

**Cosa vuole ottenere:** consegnare una bolla o una fattura senza portarla in
ufficio.

1. Home → **Carica un documento**.
2. **Fotografa** (apre la fotocamera del telefono) oppure **Scegli dal telefono**.
3. Se l'operatore è assegnato a più cantieri, il sistema chiede *Di quale cantiere
   è?*. Se ne ha uno solo, non chiede niente: lo sa già.
4. Compare **Sto leggendo il documento…** e sotto: *Puoi anche uscire: lo trovi
   tra poco in «I miei documenti»*. È importante — l'operatore non deve restare
   fermo ad aspettare.
5. Finita la lettura: **Ho letto: fattura!** con il riepilogo di quello che ha
   capito (fornitore, cantiere, importi), e la domanda **È tutto giusto?**

**Da provare:** `esempi/01-fattura-digitale.pdf`.

### Se l'operatore dice «Sì»

Compare **Grazie! Ci pensiamo noi** — *L'ufficio controlla e ti avvisa qui. Non
devi fare altro.*

Attenzione a come lo si racconta: quel «Sì» **non valida niente**. È una nota
sull'elaborazione, che l'ufficio vedrà. La validazione è e resta un atto
dell'ufficio. È una distinzione che ai clienti piace sentire esplicitata.

### Se l'operatore dice «Non torna»

Compare **Dimmi cosa non torna** e un campo di testo con l'invito *Scrivi qui,
come lo diresti a voce*. Quello che scrive diventa una segnalazione per l'ufficio,
agganciata al documento e alla sua elaborazione.

**Da provare:** carica `01`, rispondi «Non torna», scrivi «manca la ritenuta».
Poi entra come `giovanna` e mostrala in Ufficio → Segnalazioni.

---

## Caso 2 — Caricare una foto storta

Stesso percorso, ma il file è una foto scattata al volo.

**Da provare:** `esempi/04-fattura-foto.jpg`.

Qui c'è una cosa che vale la pena mostrare **dopo**, dal lato ufficio: nel
dettaglio dell'elaborazione (Ufficio → Run) si vede che il sistema ha usato
`ocr_pdf`, cioè ha guardato la pagina come un'immagine, e **non** il parser
testuale. Su una foto inclinata è la scelta giusta, e non l'ha presa un
programmatore: è scritta nelle istruzioni del workflow, che sono un file di testo
in italiano.

---

## Caso 3 — Caricare un Word o un Excel

**Da provare:** `esempi/03-fattura-word.docx`.

Con il parser su GPU acceso: funziona come un PDF, e le tabelle vengono
ricostruite meglio.

Con il parser spento: **rifiutato subito**, con una frase comprensibile, e nasce
una segnalazione per l'ufficio. È voluto: accettare un file che poi nessuno sa
leggere significherebbe far vedere all'operatore un semaforo rosso mezz'ora
dopo, invece di un no chiaro adesso.

---

## Caso 4 — Caricare qualcosa che non si può leggere

**Da provare:** `esempi/12-file-non-leggibile.txt`.

Il file viene preso in carico, ma marcato come non leggibile, e se ne occupa
l'ufficio. L'operatore non vede mai un errore tecnico. È il contratto della
modalità operatore: **mai un errore bloccante**.

---

## Caso 5 — Segnare le ore

**Cosa vuole ottenere:** dire quante ore ha fatto, senza compilare un foglio.

Home → **Le mie ore**. Quattro passi, uno per schermata, con i pallini di
avanzamento in alto:

1. **Di che giorno sono le ore?** — con «Oggi» e «Ieri» come scorciatoie.
2. **In quale cantiere hai lavorato?** — solo i cantieri dove quel giorno
   risultava assegnato.
3. **Quante ore hai fatto?**
4. **Cosa hai fatto?** — attività da toccare, oppure scritte a mano. *Puoi anche
   saltare.*

Poi **Va bene così?** e **Invia le ore**. Alla fine: *Grazie! Ho segnato le tue
ore. L'ufficio controlla e conferma.*

Due casi in cui il sistema si ferma con garbo, e vale la pena mostrarli:

- se chi è entrato non è fra i dipendenti: *Non risulti tra i dipendenti.
  Parlane con l'ufficio.*
- se quel giorno non era assegnato da nessuna parte: *Per quel giorno non risulti
  in nessun cantiere.*

Nessuna delle due è un errore: sono frasi che dicono a chi legge cosa fare.

---

## Caso 6 — I miei documenti

Home → **I miei documenti**. L'elenco di quello che ha caricato *lui* (non i
documenti degli altri), ordinato dal più recente, con un semaforo:

| Semaforo | Cosa vuol dire |
|---|---|
| Giallo, «Lo sto ancora leggendo…» | Elaborazione in corso |
| Giallo, «In lavorazione: la controlla l'ufficio» | Letto, in attesa di validazione |
| Verde, «Tutto a posto» | L'ufficio ha validato |
| Rosso, «Serve una mano: se ne occupa l'ufficio, ti avvisiamo noi» | Qualcosa non è andato |
| Rosso, «L'ufficio ha scartato questo documento» | Ripudiato: se serve, ricaricalo |

Toccando una riga si apre il dettaglio, con il riepilogo di ciò che il sistema ha
letto e — se non l'ha ancora fatto — i bottoni **Sì** / **Non torna**.

Nota per la demo: le etichette del riepilogo (Fornitore, Importo, Data…) **non
sono scritte nel frontend**. Arrivano dal backend, dichiarate per tipo di
documento. Aggiungere un tipo nuovo non richiede di toccare l'app.

---

## Caso 7 — Chiedere qualcosa

Home → **Chiedi qualcosa**, un campo di testo, un bottone.

> Es. Quanto abbiamo speso questo mese?

La risposta arriva in italiano semplice. Niente tabelle, niente SQL, niente
grafici: una frase.

**Domande che funzionano bene in demo** (per un operatore, sui suoi cantieri):

- «Quanto abbiamo speso finora nel mio cantiere?»
- «Quante ore ho fatto questo mese?»
- «Chi ha lavorato ieri a Le Palme?»
- «Quali scadenze ci sono nei prossimi trenta giorni?»

Dietro le quinte il sistema scrive una query sui dati e la esegue in sola
lettura, ma questo l'operatore non lo vede e non gli interessa. Lo si mostra
dal lato ufficio, dove la query è visibile e verificabile.

**Da non promettere:** non è un assistente generico. Risponde su cantieri, costi,
ore, documenti e scadenze — cioè su quello che c'è nei dati. Fuori da lì dice che
non sa rispondere, e fa bene.
