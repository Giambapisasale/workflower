# L'ufficio: anagrafiche e dati

Tutto quello che il sistema usa per riconoscere e collegare: cantieri,
fornitori, dipendenti, computi, mezzi. Si gestisce da **Operatività → Dati**.

---

## Caso 1 — Vedere e correggere qualsiasi cosa

**Operatività → Dati** elenca i tipi gestibili: cantieri, fornitori, dipendenti,
computi, materiali, mezzi, manutenzioni, lavorazioni, scadenze, pozzetti,
cronoprogrammi — e i documenti prodotti dai workflow (fatture, DDT, SAL,
rapportini, pagamenti).

Da lì si entra in una lista, e da una lista in una scheda che si può modificare.
Le schede **non sono programmate una per una**: sono generate dallo schema del
tipo. È il motivo per cui aggiungere un tipo di dato nuovo non richiede di
riscrivere il frontend.

Ogni salvataggio è un commit nel repo dati, con autore e data.

---

## Caso 2 — Creare un fornitore da una fattura

Il modo giusto di creare un'anagrafica **non** è compilare un modulo vuoto: è
farlo dalla revisione, dove il sistema ha già letto ragione sociale, partita IVA
e indirizzo dal documento.

Vedi [02-ufficio-revisione.md](02-ufficio-revisione.md), caso 5.

**Da provare:** `esempi/06-fattura-fornitore-nuovo.pdf`.

---

## Caso 3 — Il computo metrico

Il computo è l'unico dato che di solito **si carica una volta all'inizio**, ed è
quello che rende possibile il controllo vero: senza previsione non c'è
scostamento, c'è solo consuntivo.

Ogni voce ha descrizione, unità di misura, quantità prevista e prezzo unitario.
Le righe delle fatture ci si agganciano in revisione.

---

## Caso 4 — Dipendenti e tariffe

I rapportini nominano persone; il sistema le riconosce in anagrafica con una
ricerca approssimata che regge nome invertito, solo cognome e piccoli refusi.

La tariffa oraria del dipendente è quello che trasforma «8 ore» in un costo. Se
manca, le ore restano contate ma non costano niente: un'assenza silenziosa da
controllare prima di una demo sui costi di manodopera.

**Da provare:** `esempi/11-rapportino.pdf` nomina Salvo Torrisi, Mario Rossi e
Giuseppe Leotta, che nel seed esistono tutti e tre.

---

## Caso 5 — Mezzi e costo pieno

I mezzi hanno un costo che si compone di più voci: noleggio, carburante,
manutenzione, assicurazione, bollo. Quando una riga di fattura riguarda un mezzo,
il sistema può attribuirgliela e classificarne la natura.

Il risultato è il **costo pieno del mezzo**, che nel cruscotto compare come
«Costo mezzi» e nel report Excel ha due fogli dedicati.

Nota da dire con onestà: il sistema attribuisce una riga a un mezzo **solo se sul
documento c'è un riferimento esplicito** — targa, codice, matricola, o una
descrizione chiaramente riferita a un noleggio. Se non c'è, lascia il campo
vuoto invece di indovinare. Questa regola è nata da una correzione dell'ufficio
ed è stata scritta nelle istruzioni: è un esempio concreto di sistema che impara.

---

## Caso 6 — Gli scartati

**Operatività → Dati → Scartati.** I documenti che l'ufficio ha ripudiato.

Non sono cancellati: sono messi da parte, fuori dai costi e dai report, e si
possono ripristinare. In un sistema che tiene la contabilità di cantiere la
cancellazione vera non deve esistere — e questa pagina è la prova che non esiste.

---

## Caso 7 — La nostra azienda

**Sistema → La nostra azienda.** Denominazione, indirizzo e partita IVA
dell'impresa che usa il sistema.

Serve a una domanda che nessun altro pone: **questa fattura è davvero intestata a
noi?** Quando il destinatario letto sul documento non corrisponde, la bozza si
salva lo stesso — capita che un fornitore sbagli intestazione, e bloccare farebbe
più danni — ma parte in revisione con una segnalazione che dice esattamente cosa
non torna.

Il confronto regge le varianti che i fornitori scrivono davvero: sigla diversa
(`S.r.l.` / `SRL`), maiuscole, parole invertite, refusi dell'OCR, e il nome
annegato nella riga d'intestazione. Non regge — di proposito — un nome che
condivide con noi solo la parola generica: «Costruzioni Etna» non è «Costruzioni
Aitho», ed è esattamente il caso che il controllo esiste per prendere.

Se la partita IVA è compilata e compare sul documento, decide da sola: è
l'identificativo, e batte qualunque somiglianza di nome.

Finché la denominazione è vuota il controllo è spento, e il sistema non sospetta
di nessuno. È voluto: un controllo che non si può fare non deve trasformarsi in
un allarme sempre acceso, che poi nessuno guarda più.

**Da provare:** `esempi/05-fattura-intestata-ad-altri.pdf`.
