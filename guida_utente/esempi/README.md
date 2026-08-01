# I documenti d'esempio

Dodici file, uno per ogni strada che il sistema può prendere. Non sono
decorazione: quasi tutti servono a far vedere **una cosa che altrimenti non si
vedrebbe**.

Si rigenerano con `python guida_utente/genera_esempi.py` e sono deterministici:
la demo si ripete identica.

## Cosa aspettarsi da ciascuno

Gli esiti qui sotto sono **misurati**, non previsti: ogni documento è stato
passato dal sistema vero (modello T1 `gpt-5.5`, parser su GPU acceso) e questi
sono i risultati che ne sono usciti.

| # | File | Cosa dimostra | Esito | Costo |
|---|---|---|---|---|
| 01 | `01-fattura-digitale.pdf` | La strada normale, tutto risolto | Bozza pronta, nessuna revisione | $0,025 |
| 02 | `02-fattura-con-ritenuta.pdf` | **Ritenuta d'acconto**: il caso che il sistema sbagliava e ha imparato | Bozza con `ritenuta_acconto` valorizzata | $0,028 |
| 03 | `03-fattura-word.docx` | Un **Word**, che nessun modello vede come immagine | Bozza; fornitore da creare | $0,029 |
| 04 | `04-fattura-foto.jpg` | La **foto storta** dal cantiere: qui vince l'occhio, non il parser | Bozza pronta, letta come immagine | $0,038 |
| 05 | `05-fattura-intestata-ad-altri.pdf` | **Non è intestata a noi** | Bozza + **segnalazione** + revisione | $0,024 |
| 06 | `06-fattura-fornitore-nuovo.pdf` | Fornitore **assente in anagrafica** | Bozza con riferimento da risolvere | $0,027 |
| 07 | `07-fattura-totale-sbagliato.pdf` | **I conti non tornano** | Riprova, corregge, confidenza bassa → revisione | $0,105 |
| 08 | `08-ddt.pdf` | Un tipo diverso: **DDT**, merce senza importi | Bozza DDT | $0,020 |
| 09 | `09-ddt-word.docx` | DDT **in Word**: il tipo lo capisce leggendo il testo | Bozza DDT (non una fattura) | $0,020 |
| 10 | `10-sal.pdf` | **SAL**: avanzamento lavori in percentuale | Bozza SAL | $0,013 |
| 11 | `11-rapportino.pdf` | **Rapportino**: persone e ore, il costo della manodopera | Bozza con 3 dipendenti riconosciuti | $0,026 |
| 12 | `12-file-non-leggibile.txt` | Un file che **non si può leggere** | Rifiutato al caricamento, mai un errore in faccia | — |

Costo totale del giro completo: circa **35 centesimi**.

## I quattro da mostrare per forza

Se hai tempo per quattro documenti soli, questi:

**02 — la ritenuta d'acconto.** È la storia del prodotto in un documento solo.
La prima versione del sistema la ignorava; l'ufficio l'ha segnalato; il sistema
ha proposto una modifica alle proprie istruzioni; un umano l'ha approvata; ora la
legge. Lo si vede tutto in Sistema → Workflows.

**04 — la foto storta.** Dimostra che non serve uno scanner. E dimostra la scelta
dello strumento: qui il sistema **non** usa il parser, usa il modello che guarda
la pagina, perché su una foto inclinata legge meglio. Nel trace si vede la
chiamata a `ocr_pdf` e non a `leggi_documento`.

**05 — la fattura intestata a un altro.** Il documento è perfetto: numeri giusti,
fornitore giusto, cantiere giusto. Solo che è di un'altra impresa. Il sistema lo
registra lo stesso — perché bloccare farebbe più danni — ma apre una segnalazione
con scritto:

> Il documento risulta intestato a «Costruzioni Delta S.r.l.», non a «Costruzioni
> Aitho S.r.l.»: da controllare prima di registrarlo.

**07 — i conti che non tornano.** Il totale stampato è 9.999,00 su un imponibile
di 2.000 più 440 di IVA. Il sistema se ne accorge da solo (è una regola del
workflow), rilegge il documento, e conclude che il totale è 2.440 — ma dichiara
confidenza **0,6** su quel campo, sotto la soglia di 0,90, e lo manda in
revisione. È il comportamento giusto e va raccontato per intero: il sistema non
ha *creduto* al documento, ma non ha nemmeno *deciso da solo*.

> Nota onesta da dire ad alta voce: il valore che finisce nella bozza è quello
> ricalcolato, non quello stampato. Chi revisiona deve guardare l'originale — che
> infatti gli viene mostrato a fianco. Il campo è marcato in giallo apposta.

## I due che parlano del parser su GPU

**03 e 09** sono file Word. Senza il parser acceso vengono **rifiutati al
caricamento** con un messaggio chiaro, perché accettare un file che poi nessuno
sa leggere è peggio che dire subito di no. Con il parser acceso vengono letti
come testo, con le tabelle ricostruite.

È una buona coppia da mostrare due volte: prima con il parser spento (`make
docling-down`), poi acceso. La differenza è netta e si spiega in una frase.

## Il dodicesimo

`12-file-non-leggibile.txt` non è un documento di cantiere. Serve a mostrare il
contratto con l'operatore: **mai un errore bloccante**. Il file viene rifiutato
subito, con una frase comprensibile, e ne nasce una segnalazione per l'ufficio.
L'operatore non vede stack trace, codici, né la parola «formato».
