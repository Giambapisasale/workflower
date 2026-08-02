# L'ufficio: controllo costi

Quello per cui l'impresa compra il sistema. La lettura dei documenti è il mezzo;
questo è il fine.

---

## Caso 1 — Il cruscotto

**Operatività → Cruscotto.** La prima schermata dopo il login.

In alto i numeri d'insieme: **speso**, **imponibile**, **IVA**, **ritenute
d'acconto**, e quante fatture sono **da validare**.

Sotto, l'attività: **DDT**, **SAL**, **ore di manodopera** (dai rapportini),
**costo della manodopera**, **costo dei mezzi** (noli e costi letti dalle
fatture).

Poi le **scadenze** in arrivo, i **costi per cantiere** con la quota di budget
consumata, e i **fornitori principali**.

Da dire: tutti questi numeri vengono da documenti che qualcuno ha fotografato e
qualcun altro ha validato. Non c'è un solo dato digitato a mano.

**Scarica report Excel** produce un file con dodici fogli — Riepilogo, Fatture,
DDT, Ore, SAL, Scostamento computo, Cronoprogramma, Pozzetti, Mezzi, Costo mezzi,
Manutenzioni, Scadenze. Serve a chi vuole rigirarsi i dati per conto proprio, e
disinnesca l'obiezione «sì ma poi i dati restano dentro il vostro sistema».

---

## Caso 2 — Il singolo cantiere

Dal cruscotto, un clic sul nome del cantiere.

Si vede il quadro di quel cantiere solo: budget, speso, residuo, i documenti che
lo riguardano, le ore, i mezzi impiegati, l'avanzamento dichiarato dai SAL.

È la vista che usa il capocommessa. Nella demo è il momento di chiedere al
cliente **quale dei suoi cantieri sarebbe il primo**: sposta la conversazione da
«bel prodotto» a «come lo mettiamo dentro».

---

## Caso 3 — Scostamenti

**Operatività → Scostamenti.** Il confronto fra il computo metrico (quanto era
previsto) e quello che sta effettivamente arrivando dalle fatture.

Richiede che le righe siano state collegate alle voci di computo — si fa in
revisione con **Collega al computo**
([02-ufficio-revisione.md](02-ufficio-revisione.md), caso 6).

È qui che il prodotto smette di essere «archiviazione documenti intelligente» e
diventa controllo di gestione: non «quanto ho speso» ma **«dove sto sforando, e
di quanto»**.

---

## Caso 4 — Interrogare i dati a parole

**Operatività → Interroga.** Si scrive una domanda in italiano; il sistema
risponde con tre cose:

1. la risposta,
2. **la query SQL che ha scritto**,
3. **le righe** che ha trovato, in tabella.

I punti 2 e 3 sono la differenza fra un giocattolo e uno strumento. La query è
leggibile e verificabile: chi ha dubbi può controllarla. E gira in **sola
lettura**, su viste preparate — non può modificare niente.

### Domande da usare in demo

Facili, per rompere il ghiaccio:

- «Quanto abbiamo speso per cantiere?»
- «Quali fatture sono ancora da validare?»
- «Quanti metri cubi di calcestruzzo sono arrivati a Le Palme?»

Più interessanti, perché mostrano che incrocia le fonti:

- «Qual è il costo della manodopera per cantiere questo mese?»
- «Quanto ci costa il mezzo con più ore di impiego?»
- «Su quali voci di computo stiamo sforando?»
- «Quali scadenze scadono nei prossimi trenta giorni?»

Una domanda con una risposta onesta, da fare apposta:

- «Quanto guadagneremo su questo cantiere?» — il sistema non lo sa, perché nei
  dati ci sono i costi e non i ricavi. Mostrare che **non inventa** vale più di
  tre risposte giuste.

### Da sapere prima

Le interrogazioni sono state provate su un catalogo di **120 domande** di
famiglie diverse (anagrafiche, costi, scostamento, manodopera, mezzi,
avanzamento, forniture, scadenze, pagamenti, manufatti). Il catalogo è in
`scripts/testbook_domande.json` e si rilancia con `make testbook-ask`.

**Novanta** di quelle domande, con la risposta approvata dall'ufficio, sono
diventate casi di riferimento: ogni modifica alle istruzioni viene misurata anche
contro quelle.

Se il cliente chiede «e se sbaglia la query?», la risposta è: si vede, perché la
query è stampata; e c'è una misura di quanto spesso succede.

---

## Caso 5 — La contabilità

**Operatività → Contabilità.** Se l'integrazione con l'ERP è configurata, qui si
vede cosa è arrivato a destinazione e cosa no.

Il flusso normale è automatico: un documento validato parte da solo. Questa
pagina serve **quando qualcosa non è arrivato**: l'elenco dei documenti rimasti
indietro, col motivo, e il bottone «riprova».

Frase importante: **niente si sincronizza all'insaputa dell'ufficio**. Nessun
documento entra in contabilità senza essere passato da una validazione umana.

Se l'ERP non è configurato la pagina lo dice, e il resto del sistema funziona
uguale. In demo, se il cliente ha già un gestionale, è il momento di chiedere
quale — l'integrazione è modellata su ERPNext ma il punto di attacco è isolato.

Il capitolo intero — quando parte la sincronizzazione, cosa ci va e cosa resta
qui, come ritrovare ogni dato di là — è
[08-contabilita-erpnext.md](08-contabilita-erpnext.md).
