# Analisi: Docling come parser dei documenti in Workflower

> Analisi ad ampio raggio (**solo analisi, nessun codice**). Oggetto: se e come introdurre
> [Docling](https://github.com/docling-project/docling) nella catena di lettura dei documenti,
> oggi affidata a `pymupdf` + LLM multimodale.

---

## 1. Contesto — come si leggono i documenti oggi

Tutta la lettura passa da un solo file, `backend/app/core/tools/ocr_pdf.py`, che espone **due
funzioni con due destini diversi**:

| Funzione | Chi la usa | Cosa produce |
|---|---|---|
| `esegui(data_dir, path)` | il tool `ocr_pdf` (dichiarato nei manifest), il `Classificatore`, `eval_t3._reidrata` | pagine → **PNG a 150 DPI, base64** → messaggio `user` multimodale |
| `testo_pagine(data_dir, path)` | **solo** `eval_t3._pagine_testuali` (harness T3 senza torre visiva) | pagine → `page.get_text()`, una stringa per pagina |

Il flusso completo di un upload:

```
POST /api/documents  (documents.py)
  └─ blob in data/blobs/caricati/AAAA/…  + entità `documento` + commit git
     └─ background: Classificatore.workflow_per(blob)      ← ocr_pdf.esegui → immagini → T2
        └─ WorkflowRuntime.esegui(workflow, blob)
           └─ step `estrai`: giro agentico LLM↔tool (max 12)
              └─ l'LLM chiama `ocr_pdf` → runtime._risultato_per_llm riconosce la chiave
                 `immagini_png_base64` e allega le pagine come `image_url`
           └─ step `valida` (regole del manifest) → step `salva` (salva_bozza)
```

Il nome mente: **`ocr_pdf` non fa alcun OCR**. Rasterizza e delega il riconoscimento al modello
multimodale (T1/T2). È una scelta che ha funzionato — è multimodale, quindi legge anche le foto
scattate col telefono, e non porta in casa nessun modello — ma ha tre conseguenze che si toccano
già oggi nel repo:

1. **Il layer testuale è piatto.** `testo_pagine` è documentato nel codice stesso con la sua
   perdita: «si perde il **layout** […] e le tabelle, che arrivano appiattite». Su una fattura la
   dicitura *"Ritenuta d'acconto"* è riconoscibile **perché è in calce**, e le righe di computo
   sono una tabella. È lo scenario che `CLAUDE.md` dichiara non negoziabile (M5).
2. **Sulle scansioni il testo non esiste.** `eval_t3._pagine_testuali` ritorna `None` quando
   nessuna pagina ha strato testuale, con il commento «servirebbe un OCR vero», e l'esempio
   finisce fra i `non_rigiocabili` del report. Cioè: **il set di valutazione di T3 si assottiglia
   proprio sui documenti più difficili**, quelli su cui vorremmo misurare.
3. **Le pagine costano.** Una A4 a 150 DPI è ~1240×1754 px; ridimensionata dai provider a ~1109×1568
   px sono **~2.300–2.900 token per pagina** (stima di ordine di grandezza, da misurare). Una
   fattura di 2 pagine costa ~5.000 token di input **a ogni giro dell'agente in cui è in
   contesto**, e il classificatore T2 li spende una seconda volta *prima* del run.

C'è poi un effetto collaterale già registrato: le immagini in base64 superano i 400 caratteri di
`tracer.MAX_STRINGA_LOG` e vengono ridotte a impronta `<N caratteri, sha256:…>`. Da lì nascono
`eval_t3._reidrata` (rifà la conversione per rigiocare l'esempio) e le note del runbook di
fine-tuning: **il trace non è un dataset finché qualcuno non ricostruisce l'input**.

---

## 2. Cosa è Docling e cosa aggiunge davvero

Docling (IBM Research, `docling-project/docling`, licenza MIT — **da verificare a versione fissata**)
converte PDF, DOCX, PPTX, XLSX, HTML, EPUB e immagini in un oggetto tipizzato `DoclingDocument`,
serializzabile in **Markdown, HTML o JSON**. La pipeline PDF classica è lineare:

1. **parsing** del PDF (backend `pypdfium` o nativo): token di testo con coordinate + bitmap;
2. **modelli**: *layout analysis* (RT-DETR addestrato su DocLayNet: bounding box e classe di ogni
   elemento) e **TableFormer** (vision transformer per la struttura logica di righe/colonne, gestisce
   span e bordi parziali);
3. **assembly**: ordine di lettura, tabelle ricostruite, metadati.

In alternativa esiste la **`VlmPipeline`**, che affida l'intera pagina a un modello vision-language
(preset `granite-docling-258M`, Apache 2.0) che emette **DocTags** — un markup unico per tabelle,
formule, didascalie, note — in un solo passaggio.

OCR è **opzionale e a innesto**: `easyocr`, `tesserocr`, `rapidocr`, `ocrmac`, engine NVIDIA. Serve
solo per i documenti senza strato testuale (scansioni, foto).

**In una riga**: Docling non sostituisce il modello che *capisce* il documento; sostituisce il modo
in cui il documento gli viene *presentato* — da pixel a testo strutturato con tabelle e ordine di
lettura.

---

## 3. Sintesi / Raccomandazione

**Introdurre Docling come capacità nativa *aggiuntiva e opzionale* — un nuovo tool
`leggi_documento` accanto a `ocr_pdf`, mai al posto suo — attivabile per workflow tramite il
manifest (dato) e spegnibile da variabile d'ambiente. Non sostituire il percorso multimodale: le
foto scattate in cantiere restano meglio servite dall'LLM vision. Prima di scrivere una riga di
codice applicativo, misurare su un banco di prova già esistente (i 6 fixture + i golden) quanto
Docling migliora davvero l'estrazione e quanto costa in RAM e latenza.**

I tre motivi per cui *aggiungere* e non *sostituire*:

| Motivo | Conseguenza |
|---|---|
| **Il trace è il dataset.** Cambiare modalità di lettura cambia la forma di ogni esempio futuro e rende non confrontabili quelli passati (`eval_t3` rigioca esempi vecchi; il T3 fine-tuned è addestrato a chiamare `ocr_pdf`, routing 3/3 nel runbook). | Sostituire = buttare il ground truth accumulato e rifare il fine-tuning. Aggiungere = i due percorsi convivono e si misurano l'uno contro l'altro. |
| **Docling non è sempre meglio.** Su una foto storta di un DDT, la pipeline OCR su CPU costa ~30 s/pagina (EasyOCR) per produrre un testo peggiore di quello che un modello vision legge direttamente dal pixel. | Il percorso immagine deve restare, non come fallback ma come **scelta giusta per quella classe di documenti**. |
| **Il peso è reale.** Docling porta PyTorch e modelli scaricati a runtime; il report tecnico misura picchi di **2,4–6,2 GB** e **0,6–2,4 pagine/s su CPU**. Fly.io è configurato `shared-cpu-1x`/**1 GB**, Render free ha 512 MB. | Docling *obbligatorio* renderebbe il deploy demo impossibile. Docling *opzionale* lo lascia identico a oggi quando è spento. |

---

## 4. Cosa risolverebbe, concretamente

Non "migliore accuratezza" in astratto: quattro problemi già presenti nel repo.

### 4.1 Il tier T3 diventa valutabile sul serio

`eval_t3` con `LLM_T3_SOLO_TESTO=1` oggi offre al modello locale un testo **appiattito**, e scarta
del tutto i documenti scansionati. Con un testo Markdown che conserva tabelle e ordine di lettura:

- gli esempi `non_rigiocabili` per assenza di strato testuale **scendono verso zero** (OCR di Docling);
- la misura smette di penalizzare T3 per la modalità invece che per il modello — il report già
  dichiara `modalita_documento`, e qui se ne aggiungerebbe una terza (`markdown`).

Questo è, a mio giudizio, **il beneficio più grosso e il meno ovvio**: sblocca la distillazione
verso un modello piccolo *solo testo*, che è la direzione dichiarata della Fase 3.

### 4.2 Il dataset di fine-tuning smette di richiedere ricostruzione

La memoria di progetto e `docs/finetuning-runbook.md` registrano che `finetuning.jsonl` non è
addestrabile senza ricostruire le pagine. Un risultato Markdown è **testo**: il trace lo digerisce
comunque a impronta oltre i 400 caratteri, ma la ricostruzione è **deterministica e verificabile**
esattamente come già fa `_reidrata_prompt` (ricalcola lo sha256 e sostituisce solo se combacia).
Il problema non sparisce, ma cambia natura: da "reidrata immagini" a "reidrata testo", con lo
stesso meccanismo di verifica già scritto e testato.

### 4.3 Il classificatore costa 10 volte meno

`Classificatore._chiedi` manda **tutte** le pagine come immagini a T2 per rispondere a una domanda
che si decide sulla prima riga («Fattura», «DDT», la partita IVA in testa). Con il Markdown della
sola prima pagina: da ~2.500 token/pagina a ~300–800 token totali. È il caso d'uso con il miglior
rapporto beneficio/rischio, perché **una classificazione sbagliata non è un errore bloccante** —
`workflow_per` non solleva mai e ricade sul fallback del manifest.

### 4.4 Le tabelle arrivano come tabelle

Le righe di una fattura, il computo di un SAL, le ore di un rapportino sono tabelle. TableFormer le
restituisce con struttura logica (span inclusi); il modello vision le ricostruisce dal pixel ogni
volta. Su documenti nativi digitali — che sono la maggioranza di quelli che arrivano via PEC —
è la differenza fra leggere e interpretare.

---

## 5. Opzioni architetturali

### Opzione A — Nuovo tool nativo `leggi_documento`, accanto a `ocr_pdf` ✅ **consigliata**

Un nuovo modulo `backend/app/core/tools/leggi_documento.py` con `SCHEMA` + `esegui(data_dir, path)`
che ritorna `{"pagine": N, "markdown": "...", "tabelle": [...]}`, registrato in `Toolset.__init__`
accanto agli altri.

**Perché funziona senza toccare la cornice**: `runtime._risultato_per_llm` si ramifica **solo** sulla
chiave `immagini_png_base64`; qualunque altro risultato viene serializzato in JSON e messo nel
messaggio `tool`. Un tool che ritorna Markdown attraversa il runtime **senza una riga di modifica**
a `runtime.py`. Quale workflow lo usa è dichiarato nel manifest (`tools: [leggi_documento, …]`) e
*come* usarlo è scritto nella skill: **dato, non codice**, come impone `CLAUDE.md`.

*Costo*: la dipendenza pesa (§6). *Rischio*: due tool di lettura offerti insieme confondono il
modello (§7.4).

### Opzione B — Sostituire `ocr_pdf`

Scartata. Rompe le skill di 4 workflow, invalida il confronto storico di `eval_t3`, rende il T3
fine-tuned disallineato sul routing, e toglie il percorso migliore per le foto. Nessun beneficio
che l'Opzione A non dia.

### Opzione C — Ibrido: Markdown **e** immagini nello stesso contesto

Massima accuratezza attesa (il testo strutturato ancora il modello, l'immagine risolve le
ambiguità), massimo costo: si pagano entrambi. Da tenere come **modalità di verifica** — utile per
generare ground truth di alta qualità sui casi difficili — non come modalità di produzione.

### Opzione D — Docling come **sidecar HTTP**

Un secondo container (`docling-serve` o un servizio minimale) e un tool nativo che fa una POST.
Il container dell'app resta leggero come oggi; il peso è isolato e scalabile separatamente.

*Pro*: `docker-compose.yml` già ospita più servizi, e il precedente c'è — l'integrazione ERPNext è
un adattatore outbound con `httpx`, esattamente questa forma. Il deploy demo su Fly/Render resta
possibile spegnendo il sidecar. *Contro*: due immagini da mantenere, latenza di rete, e la stessa
domanda di sempre su chi lo tiene acceso in produzione PMI.

**Giudizio**: se il deploy target è VPS/compose, D è più pulita di A. Se il target è "un solo
container" (che è l'impostazione dichiarata nel `Dockerfile`), A con dipendenza opzionale è più
coerente. La scelta dipende da una decisione di prodotto, non tecnica → §9.

### Opzione E — Docling come tool consolidato del Toolsmith ❌ **impossibile**

Da escludere esplicitamente perché è la strada che la Fase 3 suggerirebbe per istinto. `sandbox.py`
ha `WHITELIST_PREDEFINITA = {math, datetime, decimal, re}`, vieta `open`/`__import__` per AST e
azzera `RLIMIT_FSIZE`: un tool sandboxato **non può leggere un file, importare torch, né uscire in
rete**. Il commento nel sorgente lo dice già: «il Toolsmith di F3 consolida calcoli, non l'OCR».
Docling è una **capacità nativa della cornice**, come `pymupdf`: sta accanto a `dal.py` e
`gateway.py`, non in `data/tools/`.

---

## 6. Impatto tecnico, file per file

| Punto | Impatto | Nota |
|---|---|---|
| `backend/pyproject.toml` | +`docling` (+`docling[easyocr]` o `rapidocr` se serve OCR). Trascina **PyTorch**. | Da mettere in `[project.optional-dependencies]` come extra (`documenti`), non nelle dipendenze base, per non rompere `make dev` su macchine leggere. Attenzione al precedente `litellm<1.92`: **questo repo ha già pagato il prezzo di una wheel mancante su Windows**. |
| `Dockerfile` | Immagine da ~0,5 GB a **~2–4 GB**. Torch CPU-only con `--extra-index-url https://download.pytorch.org/whl/cpu` risparmia ~1 GB di pacchetti CUDA. | I modelli (layout + TableFormer) si scaricano **al primo uso** da HuggingFace: vanno **prefetchati in build**, altrimenti il primo upload in produzione si blocca o fallisce dietro un firewall. |
| `fly.toml` / `render.yaml` | `shared-cpu-1x`/1 GB e Render free/512 MB **non bastano**. | Confermare che con Docling spento il comportamento sia bit-identico a oggi, o i due deploy demo vanno rifatti. |
| `core/tools/__init__.py` | +1 riga nel registro, +1 in `_ciclo`/`_origine`. | Il `Toolset` è già progettato per questo. |
| `core/runtime.py` | **Nessuna modifica.** | Vedi §5.A. Va però verificato che un Markdown lungo nel messaggio `tool` non faccia esplodere i 12 giri di contesto. |
| `core/classificatore.py` | Modifica *puntuale*: usa `ocr_pdf.esegui` direttamente, non via `Toolset`. | Qui la scelta di modalità è **codice**, non manifest: se si vuole renderla dato serve un campo nel manifest di `classifica-documento`. |
| `core/eval_t3.py` | `_pagine_testuali` guadagna una terza modalità; `modalita_documento` nel report diventa ternario. | Il valore va **dichiarato nel report**, come già si fa: la stessa misura su testo/immagini/markdown non dà lo stesso numero. |
| `data/workflows/*/manifest.yaml` + `skills/*.md` | Dato: `tools:` + la procedura al punto 1 della skill. | Passa dall'Improver + approvazione admin (bump di `version`), come da manifest. |
| `training/build_sft_dataset.py`, `docs/finetuning-runbook.md` | Il ramo `if chiamata["name"] == "ocr_pdf"` va esteso; `tipo_esempio: "routing"` cambia semantica se i tool di lettura sono due. | |
| Test | `test_tools.py`, `test_runtime.py`, `test_skills_tools.py`, `test_pytools.py`, `test_eval_t3*.py` elencano i nomi dei tool in asserzioni esatte (`attesi = {...}`). | Aggiungere un tool **rompe questi test per costruzione**: sono asserzioni di insieme chiuso. Va messo in conto. |
| `backend/tests/fake_llm.py` | Il finto sceglie i tool per nome (`if "ocr_pdf" in offerti`). | Regola di progetto già appresa: *il finto deve rifiutare come il reale*. Se il fake accetta entrambi i percorsi con la stessa disinvoltura, i test non provano nulla. |

---

## 7. Rischi

### 7.1 Peso e ambiente — il rischio principale
Non è la dimensione dell'immagine: è la **RAM**. Il picco misurato dal report tecnico (2,4 GB con
backend pypdfium, 6,2 GB con quello nativo, su batch di 225 pagine) va confrontato con 1 GB di Fly.
Un OOM in un `BackgroundTask` di FastAPI **uccide il worker**, e con esso ogni altro upload in
corso: peggio di un errore, perché il documento resta `in_corso` per sempre. Serve un tetto e un
fallback esplicito al percorso immagine.

### 7.2 Latenza
0,6–2,4 pagine/s **senza OCR**; con EasyOCR su CPU **fino a 30 s/pagina**. L'upload è già
asincrono (`BackgroundTasks`) e l'operatore vede il semaforo giallo *"Lo sto ancora leggendo…"*,
quindi l'UX regge — ma un rapportino di 6 pagine scansionate diventa 3 minuti.

### 7.3 Determinismo e riproducibilità
`/data` è la fonte di verità e ogni mutazione è un commit. Docling introduce **modelli con versione**
nella catena: aggiornare `docling` cambia il Markdown prodotto a parità di PDF, quindi cambia il
contesto degli esempi rigiocati da `eval_t3` e il confronto con i golden. Va **pinnata la versione
esatta** e registrata nel trace (come si registra il modello LLM), altrimenti si perde la
confrontabilità che tutta la Fase 3 presuppone.

### 7.4 Due tool di lettura confondono il modello
`runtime._estrai_su_tier` offre allo step i tool del manifest **più tutti i consolidati**. Con due
tool che a occhio fanno la stessa cosa, il modello può chiamarne uno, l'altro, o entrambi —
raddoppiando il costo. Mitigazione: descrizioni nettamente disgiunte nello `SCHEMA`
(«documento nato digitale, testo e tabelle» vs «foto o scansione, pagine come immagini») e la
procedura esplicita nella skill. Da **misurare**, non da assumere: è esattamente ciò che
`eval_t3` sa contare.

### 7.5 Privacy — un rischio che **diminuisce**
Docling gira in locale: le pagine dei documenti non escono più verso il provider LLM per essere
lette, solo il testo estratto. Su fatture con dati di fornitori e dipendenti è un miglioramento
sostanziale, e diventa un argomento commerciale con un cliente PMI. Con la `VlmPipeline` +
`granite-docling-258M` la lettura sarebbe **interamente on-premise** — ma quel modello richiede GPU
per essere pratico, quindi è uno scenario diverso dal deploy attuale.

### 7.6 Formati oltre il PDF
Docling legge DOCX/XLSX/PPTX/HTML, che oggi `ESTENSIONI_LEGGIBILI` in `documents.py` rifiuta con
una issue automatica («formato che non so leggere»). È un **beneficio collaterale** non richiesto:
apre i preventivi in Excel e i computi in Word senza toccare l'architettura. Vale la pena
segnalarlo come opzione, non aprirlo in questa analisi.

---

## 8. Percorso proposto (a milestone, dopo M21)

Solo indirizzo: nessuna di queste fasi è aperta da questa analisi.

**M22 — Banco di misura (nessuna integrazione).**
Uno script in `scripts/` che, sui 6 fixture di `fixtures/_manifest.json` più eventuali documenti
reali, produce per ciascuno: PNG (oggi), `testo_pagine` (oggi), Markdown Docling. Misura
**token di input, secondi, RAM di picco**. Nessuna dipendenza aggiunta al backend: `pip install`
in un venv separato. *Criterio d'uscita*: sappiamo con dei numeri se vale la pena.

**M23 — Estrazione a confronto sui golden.**
Rigiocare l'estrazione delle stesse fatture con i due input e confrontare i campi con il ground
truth già presente (`fixtures/_manifest.json` ha `ritenuta_acconto: 800.0` sul caso M5 — lo
scenario che `CLAUDE.md` dichiara non può rompersi). *Criterio d'uscita*: Docling **non peggiora**
nessun campo e migliora tabelle e ritenuta, oppure si chiude qui.

**M24 — Tool `leggi_documento` come capacità opzionale.**
Dipendenza in extra, spegnimento da env (assente ⇒ il tool non è registrato e il sistema è
identico a oggi), tetto di pagine e di RAM, fallback esplicito a `ocr_pdf` su qualunque
fallimento. Nessuna modifica a `runtime.py`/`gateway.py`/`dal.py`.

**M25 — Adozione per workflow (dato) + classificatore.**
Manifest e skill dei workflow che leggono PDF nativi; classificatore sul Markdown della prima
pagina. Bump di `version` via Improver + approvazione admin.

**M26 — Riallineare l'harness T3 e il dataset.**
Terza modalità in `eval_t3`, `modalita_documento` ternario, `build_sft_dataset.py` esteso, runbook
aggiornato. *Criterio d'uscita*: i `non_rigiocabili` scendono e il confronto T3/T1 resta onesto.

---

## 9. Domande aperte — servono decisioni, non altra analisi

1. **Qual è il deploy target vero?** "Un container su Fly/Render" e "Docling in-process" sono
   incompatibili (§7.1). Se il target resta quello, l'unica forma sensata è **D (sidecar)** oppure
   A con Docling spento di default in demo.
2. **Che mix di documenti arriva davvero?** Se prevalgono le foto da cantiere, il beneficio è molto
   minore di quello descritto qui — Docling brilla sui PDF nativi. Il repo non ha ancora questo
   dato: si ricava dai `blobs/caricati/` di un'installazione reale.
3. **Serve l'OCR o basta il parsing?** È la differenza fra `pip install docling` e portarsi dietro
   EasyOCR con i suoi 30 s/pagina. Sui PDF nativi l'OCR non serve mai.
4. **La `VlmPipeline` è nello scope?** Una lettura interamente on-premise è coerente con la
   direzione T3, ma cambia il profilo hardware (GPU) e va decisa come strategia, non come dettaglio
   di implementazione.

---

## 10. Conclusione

Docling risolve problemi **veri e già scritti nel repo** — il testo appiattito di `testo_pagine`, gli
esempi scartati da `eval_t3`, il costo del classificatore, le tabelle — e ne introduce uno nuovo di
natura diversa: **peso**. La forma che rispetta l'identità del sistema è quella di sempre in questo
progetto: una **capacità nativa in più**, opzionale e spegnibile, offerta ai workflow come **dato**
(manifest + skill), con `runtime.py`, `gateway.py` e `dal.py` che non cambiano di una riga.

Non va sostituito nulla. Il percorso multimodale non è un debito da estinguere: è la strada giusta
per la foto storta scattata in cantiere, ed è anche il ground truth su cui è misurato tutto quello
che c'è oggi.

---

### Fonti esterne consultate

- [Docling — documentazione ufficiale, installazione ed extra](https://docling-project.github.io/docling/getting_started/installation/)
- [Docling Technical Report (arXiv 2408.09869v5) — pipeline, TableFormer, tabella di performance](https://arxiv.org/html/2408.09869v5)
- [granite-docling-258M su Hugging Face](https://huggingface.co/ibm-granite/granite-docling-258M)
- [Discussione "Docling lightweight version (CPU only)" — peso delle dipendenze](https://github.com/docling-project/docling/discussions/1349)
