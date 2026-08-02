# L'ufficio: revisione

È il cuore del prodotto. Qui una persona controlla quello che il sistema ha
letto, corregge se serve, e valida. Da queste correzioni il sistema impara.

Si entra da `/admin` con `giovanna` / `9999`.

---

## Caso 1 — La coda

**Operatività → Revisione.** L'elenco delle bozze che aspettano un controllo.

Non ci finisce tutto: ci finisce quello che il sistema **ha dichiarato di non
saper fare con sicurezza**. Un documento entra in coda quando

- la confidenza su almeno un campo è sotto la soglia del workflow (0,90 per le
  fatture), oppure
- una regola di validazione non è passata, oppure
- il destinatario non corrisponde alla nostra azienda, oppure
- un riferimento (fornitore, cantiere) non è stato risolto in anagrafica.

Questa è la frase da dire al cliente: *il sistema non chiede di controllare
tutto, chiede di controllare quello di cui non è sicuro — e sa dirlo campo per
campo*.

---

## Caso 2 — Il confronto: originale a sinistra, campi a destra

Aperta una riga, lo schermo è diviso in due.

**A sinistra il documento.** Per PDF e foto è l'originale così com'è. Per Word ed
Excel il riquadro si intitola **«Lettura del documento»**: il browser non sa
disegnare un `.docx`, quindi viene mostrata la lettura fatta dal parser, con una
riga che lo dice esplicitamente. È anche più utile dell'originale — è
letteralmente quello che il modello ha visto.

**A destra i campi estratti**, ognuno con la sua confidenza. I campi sotto soglia
sono evidenziati: sono quelli su cui il sistema chiede aiuto.

**Da provare:** `esempi/07-fattura-totale-sbagliato.pdf` — il campo `totale` ha
confidenza 0,6 mentre tutti gli altri sono a 1,0.

---

## Caso 3 — Lasciare una nota su un campo

Accanto a ogni campo c'è la possibilità di scrivere una **nota**. Non è un
commento: è la materia prima del miglioramento automatico.

Esempio: sul campo `ritenuta_acconto` scrivere «manca la ritenuta indicata in
calce». La nota finisce nella traccia dell'elaborazione, agganciata al campo.

### E il riquadro «Migliora il workflow»

In fondo alla pagina c'è la seconda metà della stessa idea. Le note sui campi
dicono *cosa* non torna su questo documento; qui invece si detta **una regola in
italiano**, valida da qui in avanti. Per esempio:

> Se la ritenuta d'acconto è indicata in calce e non nel riepilogo, leggila
> comunque.

Bottone **Proponi miglioramento**: il sistema riscrive le istruzioni del
workflow, le **prova sui casi già validati**, e presenta la nuova versione in
Sistema → Workflows perché un umano la approvi. Le note lasciate sui campi di
questo documento vengono incluse automaticamente.

Non si applica niente da solo. Questo è il pezzo che vende il prodotto: vale la
pena rallentare e mostrarlo bene — vedi
[05-sistema-e-qualita.md](05-sistema-e-qualita.md).

---

## Caso 4 — Correggere i dati a mano

Bottone **Modifica dati**: i campi diventano modificabili, si correggono, si
salva. Ogni correzione è un commit nel repo dati, con autore e data.

Da usare quando il sistema ha letto male e la correzione è puntuale. Se invece
l'errore è **sistematico** (lo farà anche sul prossimo documento uguale), la cosa
giusta è la nota del caso 3, non la correzione a mano.

---

## Caso 5 — Riferimenti da completare

Quando il fornitore o il cantiere non esistono in anagrafica, il sistema **non
sceglie a caso**: lascia il collegamento vuoto e mette da parte quello che ha
letto sul documento (ragione sociale, partita IVA, indirizzo).

In revisione compare un riquadro «Riferimenti da completare» con quei dati già
pronti: si crea l'anagrafica con un clic, senza ricopiare niente.

**Da provare:** `esempi/06-fattura-fornitore-nuovo.pdf` — «Impresa Verdi & Figli
S.n.c.» non è in anagrafica.

È un punto che nelle demo colpisce: la maggior parte dei sistemi o inventa un
collegamento sbagliato, o si blocca. Qui il dato incerto resta dichiarato tale
finché una persona non decide.

---

## Caso 6 — Collegare al computo

Per fatture e DDT c'è **Collega al computo**: abbina le righe del documento alle
voci del computo metrico, con un confronto approssimato sulle descrizioni.

È quello che rende possibile lo **scostamento**: quanto stiamo spendendo su una
voce rispetto a quanto era previsto. Senza questo collegamento il controllo costi
si ferma al totale di cantiere.

Il risultato si vede in Operatività → Scostamenti.

---

## Caso 7 — Validare

Bottone **Salva come validato**. Tre cose succedono insieme:

1. La bozza diventa un dato validato, con chi l'ha validata e quando.
2. Esce dalla coda ed entra nei costi, nel cruscotto, nei report.
3. **Il documento entra nel set di regressione**: da quel momento è un caso di
   riferimento contro cui vengono misurate le versioni future delle istruzioni.

Il terzo punto è quello da dire ad alta voce. *Ogni volta che l'ufficio valida un
documento, il sistema guadagna un esame che dovrà superare per sempre.*

Se l'integrazione con la contabilità è accesa, la validazione è anche il momento
in cui il documento parte verso l'ERP — vale per fatture e DDT, come bozze da
confermare a valle. Cosa parte e cosa no:
[08-contabilita-erpnext.md](08-contabilita-erpnext.md).

---

## Caso 8 — Scartare

Bottone **Scarta**, con un motivo obbligatorio. Serve per i documenti che non
vanno registrati: doppioni, documenti di un'altra impresa, prove.

Lo scarto **non cancella niente**. Il documento esce dai costi, dalla revisione e
dai report, ma resta in Dati → Scartati e si può ripristinare. È una scelta di
progetto: in un sistema che tiene la contabilità di cantiere, la cancellazione
vera non deve esistere.

**Da provare:** `esempi/05-fattura-intestata-ad-altri.pdf`, che è esattamente il
caso d'uso. Prima si mostra la segnalazione automatica, poi lo si scarta con
motivo «intestata ad altra impresa».

---

## Caso 9 — Guardare come ha ragionato

Bottone **Mostra trace**. Si apre l'elenco di quello che è successo davvero:

- quali strumenti ha chiamato e con quali argomenti,
- cosa gli hanno risposto,
- quante volte ha interrogato il modello, con quanti token e quanto è costato,
- quali regole di validazione sono passate e quali no.

**Da provare, sul documento 07:** si vede la prima estrazione con `totale: 9999`,
la regola `abs(totale - (imponibile + iva)) < 0.01` che fallisce, il secondo
tentativo, e la confidenza abbassata a 0,6.

Per un cliente che ha paura dell'«intelligenza artificiale scatola nera», questa
schermata vale più di mezz'ora di rassicurazioni.

---

## Caso 10 — Le segnalazioni

**Operatività → Segnalazioni.** Tre sorgenti confluiscono qui:

- quelle scritte dall'operatore («Non torna»),
- quelle aperte dal sistema quando qualcosa non è andato,
- quelle aperte dal controllo sul destinatario.

Ognuna porta con sé il documento e l'elaborazione da cui nasce, quindi da una
segnalazione si arriva sempre alla causa in due clic.
