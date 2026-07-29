# Runbook: fine-tuning del tier locale T3 (FunctionGemma)

Questo runbook chiude l'anello del **costo marginale** (§3.1, §3.7): distillare i
run già validati in un modello locale piccolo che gestisce i workflow maturi a
costo ~0, con T1 come rete di sicurezza (escalation). **Non è eseguito nel repo**:
non ci sono dipendenze GPU né pesi versionati. T3 si accende quando il modello è
pronto — prima si *misura*, poi si *instrada*.

> Regola d'oro: non si instrada un workflow su T3 finché l'harness di valutazione
> (`GET /api/dataset/eval-t3`, milestone M18) non lo dà "pronto" — accuratezza
> function-calling alta **e** nessuna regressione rispetto a T1.

## 0. Prerequisiti

- Esempi validati a sufficienza per i workflow candidati (li produce l'uso
  normale: ogni bozza validata diventa materia prima, §3.7).
- Una GPU per l'addestramento LoRA (fuori da questo repo/ambiente). Su una **RTX
  3080 Laptop da 8 GB** basta e avanza: picco misurato **1,87 GiB**, 3 epoche su
  216 esempi in **11 minuti**. Aspettati throttling termico su un portatile (88 °C
  e `clocks_throttle_reasons=0x20`): il tempo per step raddoppia, il run finisce.
- I pesi di FunctionGemma sono **gated**: accetta la licenza su
  <https://huggingface.co/google/functiongemma-270m-it> e autenticati una volta con
  `hf auth login`. L'id corretto è `google/functiongemma-270m-it` (270M, Gemma 3
  text-only, vocab 262.146).
- Un runtime di inferenza locale con API OpenAI-compatibile: Ollama, llama.cpp
  (`server`), o vLLM.

## 1. Esporta il dataset — e ricostruiscilo

Il dataset builder è già nel prodotto: solo le tool call dei run **validati**
(mai gli errori) diventano esempi.

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
     http://localhost:8000/api/dataset/finetuning.jsonl > finetuning.jsonl
```

Ogni riga è `{workflow, tools, messages, tool_call}`. **Ma non è addestrabile
così com'è**, e va saputo prima di perdere una giornata:

1. `tracer.sanitizza` sostituisce ogni stringa oltre 400 caratteri con
   `<N caratteri, sha256:…>`. Colpisce i due prompt di sistema **e** i messaggi
   `tool` (il risultato di `cerca_fornitore` serializzato supera la soglia): il
   prefisso non è ricostruibile da `toolcalls.jsonl`. Nei **trace**
   (`data/traces/AAAA/MM/<run_id>.jsonl`) i risultati sono strutture con valori
   corti e restano interi: ricostruisci da lì.
2. I prompt di sistema si **re-idratano** dal repo dati (la skill dichiarata dallo
   step + `CONTRATTO_OUTPUT` sullo schema) e la ricostruzione si **verifica**
   ricalcolando lo stesso sha256 del segnaposto. Se non combacia (skill cambiata
   dall'Improver dopo il run), scarta l'esempio: un prompt diverso è peggio di uno
   assente. È la stessa logica di `EvalT3._reidrata_prompt`.
3. Le pagine sono **immagini** PNG (`ocr_pdf`), e FunctionGemma 270M è solo testo:
   sostituiscile col testo della pagina (`ocr_pdf.testo_pagine`). Si perde il
   layout — su una fattura "Ritenuta d'acconto" in calce è un indizio *perché* è in
   calce — e sugli scansionati serve un OCR vero.
4. `salva_bozza` è loggato **senza `messages`** (`runtime._step_salva` chiama il
   tracer senza contesto). E comunque **non è un target valido**: quella chiamata
   la compone il runtime, aggiungendoci `stato`, `origine`, `workflow` e `run_id` —
   addestrare su quelli insegna al modello a inventarsi un run_id esadecimale. Per
   l'estrazione il target giusto è l'uscita vera del modello: il JSON del
   contratto `{dati, confidence}`, con `dati` preso dall'entità **validata**
   dall'ufficio (se l'ufficio ha corretto un campo, si addestra sulla correzione).
   Lo stesso principio è già in `eval_t3.esempi_valutabili`, che esclude
   `salva_bozza` perché "invocato dal runtime e non dal modello".

## 2. Addestra (LoRA) — fuori dal repo

```python
# trl 1.9.x / peft 0.19.x / transformers 5.14.x, verificato
from liger_kernel.transformers import apply_liger_kernel_to_gemma3_text
apply_liger_kernel_to_gemma3_text()          # PRIMA di costruire il trainer

trainer = SFTTrainer(
    model="google/functiongemma-270m-it",
    args=SFTConfig(
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        max_length=4096,
        completion_only_loss=True,           # loss solo sul target, non sulla skill
        gradient_checkpointing=True,
        bf16=True,
        model_init_kwargs={"attn_implementation": "sdpa"},
    ),
    train_dataset=ds,
    peft_config=LoraConfig(r=16, lora_alpha=32, task_type="CAUSAL_LM",
                           target_modules="all-linear"),
)
```

Due trappole che costano ore:

- **`SFTConfig(use_liger_kernel=True)` non fa niente.** In trl 1.9.1 il campo
  esiste, è documentato ("reduces memory by ~60%") e viene accettato senza
  avvisi, ma nel `SFTTrainer` di mainline nessuno lo legge — lo consumano solo i
  trainer sotto `trl/experimental/`. Applica la patch a mano.
- **Senza cross-entropy fusa non ci sta in 8 GB.** Il costo non è nei pesi
  (0,54 GB in bf16) ma nei logit: vocab 262.146 × 3.509 token × 4 byte = 3,7 GB
  per il solo tensore. Misurato su una sequenza da 3.509 token:

  | | picco |
  |---|---|
  | eager + CE standard | 12,66 GB → OOM |
  | sdpa + CE standard | 12,62 GB → OOM |
  | eager + liger | 1,45 GB |
  | **sdpa + liger** | **0,83 GB** |

- Il **chat template** di FunctionGemma vuole gli schemi dei tool **avvolti**
  (`{"type":"function","function":{…}}`: legge `tool.function`) e ogni messaggio
  `tool` con il campo `name`. Ricava il completion per differenza
  (`apply_chat_template` della conversazione intera meno il prompt) invece di
  scrivere a mano il formato delle tool call, e togli il `<start_function_response>`
  che il template appende in coda: non è roba che il modello deve generare.

Fondi l'adattatore ed esporta i pesi nel formato del tuo runtime (es. GGUF per
llama.cpp/Ollama).

### Non fidarti della loss

Su 216 esempi (72 documenti validati) il training riporta `eval_loss` 0,013 e
`mean_token_accuracy` 0,994: sembra risolto. In **generazione libera** sullo
held-out, invece:

| | base | adattato |
|---|---|---|
| routing (`ocr_pdf`) — tool / argomenti | 1/3 · 0/3 | **3/3 · 3/3** |
| lookup (`cerca_*`) — tool / argomenti | 0/6 · 0/6 | **6/6** · 2/6 |
| estrazione — campi esatti | 0/112 | 21/112 |

Quasi tutti i token sono impalcatura JSON prevedibile, quindi la token accuracy
resta altissima anche quando l'estrazione è sbagliata: basta una cifra. Misura
sempre per generazione, e per *campo*, non per token. La lettura: 216 esempi
insegnano **quale tool** chiamare, non **cosa estrarre**.

## 2-bis. L'interrogazione è un compito diverso (e più adatto)

I numeri qui sopra dicono che 216 esempi insegnano **quale tool** chiamare. Vale
la pena chiedersi *su quale compito* conviene spendere quel talento, e la risposta
non è l'estrazione:

- l'estrazione è legata alla **rappresentazione dell'input**. Passando da immagini
  a testo pymupdf a un OCR di qualità (docling o simili), il *prompt* di ogni
  esempio si invalida e va ricostruito: il target sopravvive, l'input no;
- l'interrogazione ha come input **una domanda in italiano**, che nessun
  miglioramento dell'OCR tocca. Gli esempi hanno una vita utile molto più lunga.

Attenzione però a *come* si instrada l'interrogazione su un modello piccolo.
``/ask`` oggi è **text-to-SQL**, non function calling: la skill porta in prompt il
catalogo di 27 viste con tutte le colonne e si aspetta SQL libero. Per un 270M
addestrato al function calling è il compito peggiore possibile. Il ciclo §3.6 lo
converte in quello giusto:

1. porre molte domande vere (``scripts/testbook_domande.json``, 120 domande su 11
   famiglie — `make testbook-ask ARGS="--token …"`, richiede il backend avviato);
2. raggrupparle per **insieme di viste attraversate** — *non* per fingerprint, che in
   un catalogo non ricorre mai (vedi sotto);
3. consolidare i concetti ricorrenti in viste ``v_*`` e tool parametrici ``t_*``
   (approvazione umana obbligatoria, `POST /api/dataset/consolida`, che accetta un
   `fingerprint`, un `golden_id` o direttamente il `sql` disegnato);
4. ripetere le domande: ora la risposta giusta è `SELECT * FROM t_nome('Manzoni')`
   — output corto, vocabolario chiuso, **function calling**.

Solo il dataset del passo 4 ha senso per FunctionGemma. Quello del passo 1 no.

### Misurare l'interrogazione: si giudica la risposta, non l'SQL

Due query diverse possono essere entrambe giuste. Il gate confronta i **risultati**:
un caso golden-domanda conserva la query **approvata dall'ufficio**
(`POST /api/golden/domande`), non le righe — le righe invecchiano alla prima
fattura in più. Alla misura si eseguono riferimento e candidato sugli stessi dati
e si confrontano le righe (alias e ordine delle righe non contano; l'ordine delle
colonne sì). Il report `GET /api/dataset/eval-t3` lo espone in `interrogazione`, e
`interroga` entra in `pronti`/`regressioni` come qualunque workflow.

Un caso il cui riferimento non gira più o **non restituisce righe** è dichiarato
`degenere` ed escluso: lo pareggerebbe qualunque modello muto.

### Cosa ha detto il testbook (T2, 120 domande, repo dati reale)

| | |
|---|---|
| query prodotte | 119/120 |
| rifiutate dai guardrail | 1 — **bug nostro**, ora corretto (vedi sotto) |
| con righe | 95 |
| senza righe | 24 |

I 24 vuoti non sono 24 errori. Classificati a mano, uno per uno:

| causa | n | esempio |
|---|---|---|
| correttamente vuote (il dato non c'è) | 14 | «fatture pagate»: `v_pagamenti` ha 0 righe |
| **valore inventato** | 4 | `provincia = 'catania'` (nei dati è `'CT'`) |
| **match esatto invece di parziale** | 2 | `ragione_sociale = 'Calcestruzzi Etna'` (è `'… S.p.A.'`) |
| **vista sbagliata** | 1 | avanzamento preso da `v_cronoprogramma` (copre 1 cantiere su 3) invece che da `v_sal` |
| catalogo sbagliato (cantiere inesistente) | 3 | corretto nel catalogo |

Quindi **7 errori veri su 119**, e 6 dei 7 sono colpa del **prompt**, non del modello:

- il catalogo in prompt dà **nomi e tipi** delle colonne, non i **valori ammessi**.
  Nessun fine-tuning su un centinaio di esempi insegna a un modello che la provincia
  è una sigla. La buona notizia: i domini sono **già dato dichiarato** negli schemi
  (`data/schemas/mezzo.schema.json` → `proprieta: [proprio, noleggio]`, che è
  esattamente il valore sbagliato dal modello). Iniettarli nella skill è lettura di
  file piccoli, nessuna query;
- niente nella skill dice che sui nomi liberi (ragioni sociali, nomi di cantiere)
  si usa il confronto parziale e non `=`.

Vanno tolti *prima* di misurare un tier, altrimenti si attribuisce al modello una
colpa del prompt — e si "corregge" col fine-tuning un problema che il fine-tuning
non tocca.

### Tolti: cosa è cambiato riponendo le domande

La skill ha ora una sezione «Valori ammessi» riempita da
`app/core/vocabolari.py`, che ricava gli elenchi chiusi e i formati dagli `enum` e
dai `pattern` degli schemi delle entità, più due regole: sui testi liberi si
confronta con `ILIKE` sulla **radice**, sugli elenchi chiusi con `=` e uno dei
valori elencati. Riposte le 30 domande delle due famiglie coinvolte:

| domanda | prima | dopo |
|---|---|---|
| «cantieri aperti?» | `stato = 'aperto'` → 0 righe | `stato = 'validato' AND data_fine_prevista >= today` → 3 |
| «in provincia di Catania?» | `provincia = 'catania'` → 0 | `provincia = 'CT'` → 3 |
| «fornitori di calcestruzzo» | `LIKE '%calcestruzzo%'` → 0 | `ILIKE '%calcestruzz%'` → 1 |
| «partita IVA di Calcestruzzi Etna» | `= 'Calcestruzzi Etna'` → 0 | `ILIKE '%calcestruzz%etn%'` → 1 |
| «costo orario dei mezzi di proprietà» | `proprieta = 'proprietà'` → 0 | `proprieta = 'proprio'` → 1 |

Cinque su cinque, e le altre 25 non peggiorano. Attenzione a come si legge un
confronto così: **27 query su 30 sono riscritte** anche dove l'esito è identico,
perché il modello campiona. Una domanda che cambia vista fra due esecuzioni (D015
oscilla fra `v_allocazioni` e `v_rapportini_righe`) non è una regressione del
prompt: verificato riponendola tre volte.

#### L'errore che non si vedeva: enum annidati

`tipo_costo` è dichiarato dentro `fattura.righe[].items`, non fra le proprietà di
primo livello, e la prima versione dell'estrattore lo saltava. Conseguenza sui
dati veri: il modello scriveva `tipo_costo = 'materiale'` — valore inesistente,
query legittima, **somma zero**. Nessun errore da nessuna parte, e uno zero sembra
un dato: «come si dividono i costi fra materiali, manodopera e noleggi» rispondeva
`materiali: 0`, cioè il 0% di 500 mila euro di fatture.

Questi non erano fra i 7 errori contati sopra, proprio perché avevano restituito
righe. **Il conto degli errori veri è quindi un minimo, non un totale**: una query
che torna numeri sbagliati non si distingue da una giusta senza rileggerla.

Con l'elenco iniettato il modello ha smesso di inventare il valore, ma il caso ha
mostrato un limite che il prompt non può colmare: nel modello dati **non esiste**
un modo di dire «questa riga di fattura è materiale» (`tipo_costo` classifica i
costi dei *mezzi*). La regola aggiunta — «se nessun valore dell'elenco corrisponde,
quella distinzione non esiste nei dati: non scrivere un filtro che darà zero» — lo
porta a usare `mezzo_id IS NULL` come proxy, e la voce materiali passa da 0 a
498 mila. È una definizione ragionevole scelta al volo dal modello: **è esattamente
il genere di cosa che va cristallizzata in una vista** (§3.6), non lasciata a un
campionamento.

### Il fingerprint non trova famiglie in un catalogo

Atteso: porre 120 domande e leggere i gruppi ricorrenti. Misurato: **119 query
testualmente distinte su 119**, zero fingerprint ripetuti. Ovvio a posteriori — il
fingerprint normalizza i *letterali*, quindi riconosce la **stessa domanda
ripetuta** (l'uso reale), non domande diverse della stessa famiglia.

Per decidere cosa consolidare da un catalogo serve un altro raggruppamento:
l'**insieme di viste** che la query attraversa. Su questi 119:

    9 domande  v_fatture
    5 domande  v_cantieri
    4 domande  v_cantiere_scostamento + v_cantieri
    3 domande  v_dipendenti + v_rapportini_righe
    2 domande  v_fatture + v_fornitori + v_pagamenti

e 17 domande incrociano 3 o più viste — quelle sono le costose da riscrivere ogni
volta, e i candidati migliori a diventare `t_*`.

### I 90 casi golden sull'interrogazione

Delle 120 domande, 90 sono state fissate come casi di regressione
(`POST /api/golden/domande`, `GOLD-0075`…`GOLD-0164`), con copertura su tutte le
11 famiglie. Le 30 escluse: 20 senza righe — il server le rifiuta comunque, un
riferimento vuoto lo pareggia qualunque candidato muto — e **10 scartate rileggendo
la query**, cioè girano e restituiscono numeri, ma non quelli che la domanda chiede:

| caso | perché |
|---|---|
| «su quanti cantieri lavora ogni dipendente» | conta da `v_rapportini_righe`, dove `dipendente_id` è sempre NULL |
| «quanta IVA abbiamo pagato» | `v_pagamenti` è vuota: la somma è NULL, e un NULL non discrimina |
| «come si dividono i costi» / «manodopera vs materiali» | `tipo_costo = 'materiale'`, valore inesistente |
| «ore di persone che non sono dipendenti» | `tipo NOT IN ('dipendente','interno')`: valori inventati, la condizione è vera per tutti e le 9 righe sembrano tutte di estranei |
| «conviene tenere o noleggiare l'escavatore» | deriva `'tenere'/'noleggiare'` da `proprieta`: risponde alla domanda con la domanda |
| «a che punto siamo col cantiere della scuola» | la scuola è CNT-002, `v_cronoprogramma` ha solo CNT-001 |
| «quanto resta da pagare» | `SUM(f.totale)` su una LEFT JOIN con i pagamenti: duplica il totale per ogni pagamento. Oggi torna giusto solo perché i pagamenti sono zero |
| «quale cantiere è il più redditizio» | ordina per budget: il budget è quanto vale il lavoro, non quanto ci si guadagna |

Il criterio non è «la query ha restituito righe» ma «la query risponde alla
domanda». Vale la pena dirlo perché il primo criterio è automatizzabile e il secondo
no: quelle 10 sono passate tutte dai guardrail e dall'esecuzione.

Un limite da tenere presente: la misura per equivalenza dei risultati penalizza un
candidato che sceglie un'interpretazione **diversa ma legittima** («cantieri aperti»
= validati con fine prevista futura, e non un'altra definizione). Una decina dei 90
casi ha questa natura. È un altro argomento per il consolidamento in `t_*`: quando
l'interpretazione è dentro una vista approvata, la risposta giusta è una sola.

### Passo 3: cosa è stato consolidato, e cosa ha insegnato

Quattro artefatti, disegnati leggendo i 90 casi golden raggruppati per insieme di
viste (56 query su 90 toccano una vista sola: lì non c'è niente da consolidare).

| artefatto | serve | perché non era una query qualunque |
|---|---|---|
| `v_cantiere_costi` | 7 domande | fissa **una** definizione di costo per natura: `mezzi` = righe imputate a un mezzo, `materiali_e_servizi` = tutto il resto. Il modello la reinventava a ogni domanda, e su «materiali» dava 0 |
| `v_cantiere_situazione` | 4 domande | budget, previsto, consuntivo, margine, % consumata. Quattro casi golden facevano la stessa join solo per arrivare al nome del cantiere |
| `v_fatture_saldo` | 3 domande | aggrega i pagamenti **prima** della join. Fatto dopo, duplica il totale della fattura per ogni pagamento |
| `t_costi_cantiere(nome_cantiere)` | «quanto è costato il cantiere X» | confronto parziale sul nome: chi chiede dice «la scuola», non «Ristrutturazione Scuola Manzoni» |

Riposte le 14 domande che questi quattro servono: **13 usano l'artefatto**. E la
forma della risposta è quella che serve al modello piccolo — da una join a tre vie a:

```sql
SELECT * FROM t_costi_cantiere('Manzoni')
```

#### L'ingresso del §3.6 andava cambiato

Gli endpoint di consolidamento accettavano solo un `fingerprint`, cioè presupponevano
che un candidato si scopra perché una query **si ripete**. Ma un catalogo di domande
diverse non ripete niente, e soprattutto: la vista giusta **non è** nessuna delle
query prodotte dal modello — va disegnata. Ora la sorgente può essere un
`fingerprint`, un `golden_id` (query già approvata) o il `sql` esplicito. Le garanzie
non cambiano: guardrail di `/ask` e compilazione+chiamata reali su DuckDB prima di
scrivere in `views.sql`.

#### Tre cose imparate misurando

**Un tool che c'è viene usato anche dove non serve.** `t_ore_periodo(dal, al)`
sembrava ovvio — quattro domande sono «ore in un periodo» — ma la grana era
sbagliata: restituiva il dettaglio per lavoratore, e alla domanda «quante ore abbiamo
fatto questo mese?» il modello ha preferito il tool a un `SUM`, peggiorando la
risposta (7 righe di dettaglio invece di un totale). **Rimosso**: `v_rapportini_righe`
già bastava, e la skill dice di preferire i tool. Un tool va disegnato sulla *forma*
della domanda, non solo sui dati che tocca.

**La vista toglie una trappola dallo spazio delle risposte possibili.** «Quanto
abbiamo ancora da pagare?» era `SUM(f.totale) - SUM(p.importo_pagato)` su una LEFT
JOIN: sbagliata, e invisibile perché oggi i pagamenti sono zero. Ora è
`SUM(residuo) FROM v_fatture_saldo` e l'errore non è più esprimibile.

**Il fan-out resta il pericolo peggiore quando la vista non viene usata.** «Costo
totale sommando fatture e manodopera» ha ignorato `v_cantiere_costi` (la domanda
nomina le fonti, e il modello le ha seguite) e ha scritto
`SUM(DISTINCT f.totale) + SUM(r.costo)` su una doppia LEFT JOIN: il `DISTINCT`
perde le fatture di pari importo, la join gonfia la manodopera, e il totale usciva
259 776 invece di 226 160. Il caso golden `GOLD-0162` — che conserva la versione con
le CTE — lo intercetta: è esattamente il lavoro per cui esiste.

#### Una scelta di definizione da confermare

`v_cantiere_costi` somma le **righe** di fattura, che riconciliano all'euro con
l'`imponibile` (verificato: scarto 0,00 su tutti e tre i cantieri, nessuna fattura
senza righe). Quindi i costi sono **al netto dell'IVA**, mentre `v_fatture.totale` è
lordo: due domande formulate quasi uguali possono dare numeri diversi del 22%.
Per il controllo costi il netto è la base giusta, ed è anche l'unica che permette lo
spacco per natura (solo le righe hanno `mezzo_id`) — ma `v_cantiere_situazione`
calcola `margine_residuo = budget - costo_totale`, quindi assume che anche il budget
sia netto. Va confermato.

### Passo 4: le 120 domande sul catalogo consolidato

La misura che decide se conviene addestrare un 270M. 120 domande riposte, 116 query
prodotte, **$0,38**.

**Com'è cambiata la forma della risposta** — è questo che distingue function calling
da text-to-SQL:

| forma | prima | dopo |
|---|---|---|
| chiamata a un tool `t_*` | 0 | **2** |
| lettura da una sola vista (nessun join, nessuna CTE) | 61 | **81** |
| SQL articolato (join o CTE) | 59 | **33** |

Lunghezza media della query: 249 → 193 caratteri; sulle sole 26 domande che usano un
artefatto consolidato, **384 → 184**. Le 33 articolate restano concentrate in
`avanzamento` (7) e `costi` (5): sono i prossimi candidati.

**Verdetto.** La direzione funziona e si misura, ma quattro artefatti non bastano:
solo 2 risposte su 116 sono una chiamata a tool. Le 81 letture da vista sola sono
ancora text-to-SQL, solo molto più corto. Per arrivare a «scegli un tool e riempi i
parametri» servono un tool per famiglia di domanda — dell'ordine di 15-20, non 4 — e
ognuno va misurato, perché un tool sbagliato peggiora le risposte (vedi
`t_ore_periodo` sopra).

**Confronto coi 90 riferimenti approvati** (eseguiti sugli stessi dati, senza
chiamate al modello):

| esito | n |
|---|---|
| risposta identica | 42 |
| stesse righe, proiezione diversa | 31 |
| davvero diversa | 9 |
| non confrontabile (nessuna colonna in comune) | 4 |
| rifiutata dai guardrail | 4 |

Quelle 31 hanno cambiato il prodotto: l'equivalenza confronta i valori **per
posizione**, quindi una query che filtra e raggruppa identicamente ma seleziona sei
colonne invece di nove risultava «diversa». `eval_interroga` ora riporta anche
`risposta_compatibile` — stesse righe sulle colonne che le due query chiamano allo
stesso modo — ed è su quella che si decide `pronto_per_t3`. Con la sola metrica
stretta il gate avrebbe letto 49% dove la risposta giusta era 85%.

Delle 9 differenze vere, la maggior parte è interpretazione: «quante voci ha il
computo di Misterbianco» dà 0 righe perché quel cantiere **non ha** un computo (il
riferimento usava una `LEFT JOIN` e mostrava 0), e «su quali cantieri stiamo perdendo
soldi» dà 0 perché nessuno sfora il budget (il riferimento guardava lo scostamento
sul computo, dove due sforano). Tre erano difetti veri, tutti corretti nella skill:

- **valore di più parole troncato**: `t_costi_cantiere('scuol Manzon')` → zero righe,
  perché fra due radici accorciate il testo vero non c'è più. La regola ora dice di
  mettere `%` fra le parole, o di passare a un tool **una sola** parola distintiva;
- **colonna dedotta da un'altra vista**: `FROM v_ddt GROUP BY cantiere_id, cantiere`.
  Le viste consolidate espongono `cantiere_id` e `cantiere` in coppia, e il modello
  ha generalizzato la coppia alle viste di registro, che hanno solo l'id. La regola
  ora dice che le colonne di una vista sono solo quelle elencate;
- **filtro sul periodo perso**: «quanto abbiamo speso quest'anno» risposto da
  `v_cantiere_situazione`, che non ha una colonna di data. Una vista che aggrega per
  cantiere fa sparire il tempo senza che si veda.

L'ultimo è il rischio generale delle viste aggregate: rendono facile la domanda
tipica e invisibile la dimensione che hanno collassato.

### Il collegamento che non c'era: rapportini → dipendenti

Misurando le domande sulla manodopera è venuto fuori un buco che non era
dell'interrogazione: `v_rapportini_righe.dipendente_id` era **null su tutte le 33
righe** del repo. Lo schema del rapportino prevedeva il campo dal primo giorno e la
vista lo usa già (`COALESCE(d.tariffa_oraria, r.costo_orario, 0)`), ma la skill di
estrazione non ne parlava e il tool per risolverlo non esisteva. Un campo dichiarato,
usato a valle, e mai riempito: il tipo di buco che nessun test coglie, perché tutto
gira e i totali sembrano plausibili.

Conseguenze, entrambe silenziose:

- la manodopera costava quanto dice il **foglio** invece che quanto dice l'anagrafica
  — su 13 righe collegabili, 2810 € contro 2690 €;
- ogni join `rapportini → dipendenti` cadeva nel vuoto, quindi «quante ore ha fatto
  Torrisi?» tornava zero righe. Non un errore: un vuoto, che sembra una risposta.

Cosa è stato fatto: un tool nativo `cerca_dipendente` (le anagrafiche hanno `nome` e
`cognome` in due colonne mentre il rapportino scrive un solo testo, quindi il
confronto vede anche `"nome cognome"` e `"cognome nome"` — col solo cognome dà 0.40,
col nome intero 1.0), la skill che lo chiama **per riga** con la soglia 0.75 delle
altre anagrafiche, e il workflow a v1.1.

Verificato su un modello vero (`gpt-5.5`, un rapportino da 4 righe: 2 dipendenti, 1
lavoratore di terzi, 1 squadra): collega i due, lascia `null` gli altri due, e
tiene `nominativo` e `costo_orario` come li ha letti. Le 4 ricerche stanno **nello
stesso giro** della ricerca del cantiere, quindi il collegamento non costa un round
trip in più: 3 chiamate LLM prima, 3 dopo.

Due cose valgono oltre il caso specifico:

- **la separazione conta più della soglia**. I tre dipendenti veri danno 1.00, tutti
  gli estranei stanno sotto 0.50 (`"Rossi M."` contro Giovanna Russo: 0.46). Il test
  verifica il margine, non l'esito: un collegamento sbagliato non dà errore, sposta
  ore e costi su un'altra persona e il totale del cantiere resta credibile.
- **il golden set va migrato con i dati**. I 9 casi golden dei rapportini avevano
  `dipendente_id: null` nell'`atteso`: lasciarli così avrebbe conservato come
  «giusto» ciò che si stava correggendo, e al primo replay l'Improver avrebbe letto
  la correzione come uno scostamento dal golden. La rete di sicurezza avrebbe
  suonato contro la correzione. `scripts/collega_dipendenti.py` fa entrambe le cose,
  in sola lettura per default.

Nota per il dataset: i 33 esempi di function calling in più (una `cerca_dipendente`
per riga) **non** esistono ancora. Il dataset nasce dai trace, e i trace dei
rapportini già caricati non contengono chiamate che al tempo non c'erano: arriveranno
coi documenti nuovi.

## 3. Servi il modello in locale

```bash
# Ollama
ollama create functiongemma-workflower -f Modelfile
ollama serve            # espone http://localhost:11434 (OpenAI-compatibile)
```

## 4. Misura PRIMA di accendere

Punta temporaneamente `LLM_T3_MODEL` al modello locale e chiedi il report:

```bash
export LLM_T3_MODEL=ollama/functiongemma-workflower
export LLM_T3_API_BASE=http://localhost:11434
export LLM_T3_SOLO_TESTO=1
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
     "http://localhost:8000/api/dataset/eval-t3" | jq .
```

`LLM_T3_SOLO_TESTO=1` serve quando il candidato **non è multimodale**: l'harness
offre le pagine come testo invece che come immagini, e lo fa per **entrambi** i
tier — altrimenti il verdetto misurerebbe la modalità e non il modello. Il report
lo dichiara in `modalita_documento`.

Guarda `pronti` e `regressioni`. Instrada su T3 **solo** i workflow in `pronti`.
Leggi anche i tre contatori che dicono quanto vale la misura: `non_rigiocabili`
(esempi persi), `prompt_troncati` (prompt arrivati a impronta) e
`prompt_reidratati` (prompt rimessi interi e verificati). Se `prompt_reidratati`
è 0 su un set non vuoto, la skill nel repo non è più quella con cui i run sono
girati: il confronto vale meno di quanto sembra.

## 5. Accendi T3

- Imposta `LLM_T3_MODEL` (e `LLM_T3_API_BASE`) nell'ambiente del backend.
- Nel manifest del workflow maturo, dichiara `tier: T3` (è dato: nessun codice).
- Da quel momento gli step girano su T3 e, su errore/bassa confidence/output
  fuori contratto, **escalano a T1** in automatico. Il costo del tier locale è ~0.

## 6. Sorveglia e ri-addestra

`GET /api/dataset/stats` riporta la **% di escalation per workflow**: è il
termometro del modello locale. Se sale, il modello sta faticando su casi nuovi:
riesporta il dataset (ora più ricco), ripeti dal passo 1. Se un workflow regredisce,
riportalo su T1 (togli `tier: T3` dal manifest) finché il modello non recupera.

La rete di sicurezza è sempre attiva: T3 è un'ottimizzazione, mai un
single-point-of-failure.
