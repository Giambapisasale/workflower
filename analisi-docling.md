# Analisi: Docling come parser dei documenti in Workflower

> **Analisi, prove di fattibilità, e integrazione realizzata.** Il §11 racconta cosa è stato
> effettivamente messo a bordo il 31/07/2026 e cosa resta aperto.
>
> **Contesto infrastrutturale**: deploy **on-premise su GPU NVIDIA** — DGX Spark (GB10, `arm64`),
> RTX 4090 (24 GB), RTX 3080 sul PC di sviluppo. I target managed (Render, Fly.io) sono stati
> rimossi dal progetto. Vincolo dichiarato: **Docling deve usare la GPU**.
>
> Le misure del §3 sono state prese su questa macchina (RTX 3080 Laptop 8 GB, Docker 29.6 +
> NVIDIA Container Toolkit) il 31/07/2026, con
> `quay.io/docling-project/docling-serve-cu130:v1.29.0`. **Non sono stime.**

---

## 1. Sintesi / Raccomandazione

**Docling è fattibile, veloce e utile: su RTX 3080 converte 24 pagine di PDF in 1,8 s
(≈13 pagine/s), legge un DOCX in 0,08 s ricostruendo le tabelle in modo esatto, e — questo è il
punto — legge una fattura *scansionata senza strato testuale* ritrovandone la ritenuta d'acconto
in 1,1 s. La forma giusta è un container affiancato (sidecar) con la GPU, non una dipendenza nel
container dell'app.**

**Un blocco operativo, però, va risolto prima di parlare di produzione sullo Spark**: le immagini
ufficiali di Docling — sia `amd64` che `arm64` — contengono kernel CUDA fino a **sm_120**, mentre
il GB10 del DGX Spark è **sm_121**. Verificato direttamente (§3.6). Sulla 4090 e sulla 3080
funziona tutto oggi; **sullo Spark no**, e serve un'immagine ricostruita sulla base NGC PyTorch.

Tre conseguenze rispetto alla versione precedente di questa analisi:

| Timore precedente | Cosa dicono le prove |
|---|---|
| «I modelli si scaricano al primo uso: vanno prefetchati in build» | **Falso per il container**: i pesi sono già dentro l'immagine (`artifacts_path is set to a valid directory. No model weights will be downloaded at runtime`). Avvio a freddo ~4 s, nessuna rete. |
| «L'OCR costa ~30 s/pagina (EasyOCR)» | **Superato**: l'immagine seleziona da sola **RapidOCR su onnxruntime**, e una pagina scansionata costa **1,14 s**. |
| «0,6–2,4 pagine/s, 2,4–6,2 GB di RAM» (report tecnico, CPU) | Su GPU: **13,3 pagine/s** e **~2,3 GB di VRAM** di picco. Il collo di bottiglia non è più il parser. |

---

## 2. Contesto — come si leggono i documenti oggi

Tutta la lettura passa da `backend/app/core/tools/ocr_pdf.py`, che espone **due funzioni con due
destini diversi**:

| Funzione | Chi la usa | Cosa produce |
|---|---|---|
| `esegui(data_dir, path)` | il tool `ocr_pdf` (dichiarato nei manifest), il `Classificatore`, `eval_t3._reidrata` | pagine → **PNG a 150 DPI, base64** → messaggio `user` multimodale |
| `testo_pagine(data_dir, path)` | **solo** `eval_t3._pagine_testuali` (harness T3 senza torre visiva) | pagine → `page.get_text()`, una stringa per pagina |

Il nome mente: **`ocr_pdf` non fa alcun OCR**. Rasterizza e delega il riconoscimento al modello
multimodale. Ha funzionato — legge anche le foto scattate col telefono — ma ha tre conseguenze già
scritte nel repo:

1. **Il layer testuale è piatto.** Il codice stesso lo documenta: «si perde il **layout** […] e le
   tabelle, che arrivano appiattite». Su una fattura la dicitura *"Ritenuta d'acconto"* è
   riconoscibile **perché è in calce** — lo scenario che `CLAUDE.md` dichiara non negoziabile (M5).
2. **Sulle scansioni il testo non esiste.** `eval_t3._pagine_testuali` ritorna `None` quando nessuna
   pagina ha strato testuale («servirebbe un OCR vero») e l'esempio finisce fra i
   `non_rigiocabili`: **il set di valutazione di T3 si assottiglia proprio sui documenti difficili**.
3. **Le pagine costano.** Una A4 a 150 DPI ridimensionata a 1109×1568 px vale **~2.320 token** per
   pagina, e il `Classificatore` li spende una seconda volta *prima* del run.

E un quarto, di formato: `ESTENSIONI_LEGGIBILI` in `documents.py` è `{.pdf, .png, .jpg, .jpeg}`.
**Un preventivo in Word oggi viene rifiutato** con una issue automatica.

---

## 3. Le prove eseguite

Ambiente: Windows 11, Docker 29.6.2 con runtime `nvidia` registrato, RTX 3080 Laptop 8 GB, driver
610.47 (CUDA UMD 13.3). Immagine `quay.io/docling-project/docling-serve-cu130:v1.29.0`, **9,12 GB**,
avviata con `--gpus all`. Script e output completi restano nello scratchpad di sessione.

### 3.1 La GPU la usa davvero

```
arch      : x86_64
torch     : 2.13.0+cu130
cuda avail: True
device    : NVIDIA GeForce RTX 3080 Laptop GPU
capability: (8, 6)
```

E nei log di avvio del server, tre volte: `docling.utils.accelerator_utils - Accelerator device: 'cuda:0'`.

Non è solo dichiarato: campionando `nvidia-smi` durante la conversione del PDF da 24 pagine,
**utilizzo GPU al 64% di picco** e VRAM da 5.741 a 6.393 MiB. Il modello di layout e TableFormer
girano su GPU.

### 3.2 Velocità (lato server, dal log del convertitore)

| Documento | Pagine | Tempo di conversione |
|---|---:|---:|
| `fattura-studio-bianchi.pdf` | 1 | **0,13 s** |
| `ddt-edil-sud.pdf` | 1 | 0,14 s |
| `sal-capannone-etna.pdf` | 1 | 0,26 s |
| `fattura-edil-sud.pdf` | 1 | 0,30 s |
| **PDF concatenato (carico)** | **24** | **1,34 – 1,80 s → 13,3–17,9 pagine/s** |
| `computo-capannone-etna.docx` | — | **0,07 s** |
| **PDF scansionato, solo immagini (OCR)** | 1 | **1,14 s** |

Riferimento: il report tecnico di Docling misura **0,6–2,4 pagine/s su CPU**. La GPU vale qui un
fattore **~10x**, e porta il costo di lettura sotto la soglia in cui smette di essere un problema.

### 3.3 DOCX: funziona, ed è la sorpresa migliore

Ho generato un **computo metrico** in Word — intestazione, tabella a 6 colonne con celle unite,
riepilogo economico, ritenuta d'acconto in calce — cioè un documento che oggi Workflower **rifiuta
per estensione**. Docling lo converte in 0,07 s e restituisce:

```markdown
| **Codice**             | **Descrizione lavorazione**                               | **U.M.** | **Quantità** | **Prezzo unit. €** | **Importo €** |
|------------------------|-----------------------------------------------------------|----------|--------------|--------------------|---------------|
| 01.A02.001             | Scavo a sezione obbligata in terreno di qualsiasi natura  | mc       | 145,00       | 28,50              | 4.132,50      |
| 01.A04.012             | Calcestruzzo per fondazioni Rck 30 N/mmq gettato in opera | mc       | 62,50        | 142,00             | 8.875,00      |
…
### Riepilogo economico
| Ritenuta d'acconto 0,50% (art. 30-bis)       | 250,06    |
| TOTALE DOCUMENTO                             | 55.012,82 |
```

Struttura, gerarchia dei titoli e **entrambe** le tabelle ricostruite. Due imperfezioni da conoscere:

- la **cella unita** della riga di totale viene **replicata** su tutte le colonne che copre
  (`TOTALE LAVORI A MISURA` ripetuto 5 volte): non è un errore di lettura, è come il Markdown
  rappresenta uno span — ma un LLM che conta le colonne va istruito;
- nella tabella a due colonne senza intestazione, la **prima riga diventa header**.

Nessuna delle due è un ostacolo per un LLM che estrae campi. Entrambe lo sarebbero per un parser
rigido — motivo in più perché Docling **prepari** il testo e sia l'LLM a interpretarlo.

### 3.4 Scansione senza strato testuale: il buco di `eval_t3` si chiude

Ho rasterizzato `fattura-studio-bianchi.pdf` a 200 DPI in un PDF di sole immagini. Verifica prima
della prova: `strato testuale = 0 caratteri`. È esattamente il documento su cui oggi
`eval_t3._pagine_testuali` si arrende.

Docling lo converte in **1,14 s** e nel Markdown ci sono tutti e quattro i controlli:

```
trovato: Bianchi      trovato: 4.880      trovato: 800      trovato: Ritenuta
```

Cioè: **la ritenuta d'acconto — lo scenario M5 — è stata letta da un'immagine pura**, senza LLM.

### 3.5 Costo in token: fra 16x e 34x meno

Confronto fra il Markdown prodotto e il costo delle stesse pagine come PNG (formula dei provider
vision: lato lungo ridimensionato a 1568 px, `w·h/750`; testo stimato a 3,6 caratteri/token):

| Documento | Token Markdown | Token come PNG | Rapporto |
|---|---:|---:|---:|
| `fattura-calcestruzzi-etna.pdf` | ~121 | ~2.319 | **19,2x** |
| `ddt-edil-sud.pdf` | ~144 | ~2.319 | **16,1x** |
| `sal-capannone-etna.pdf` | ~88 | ~2.319 | **26,4x** |
| `rapportino-le-palme.pdf` | ~69 | ~2.319 | **33,6x** |

I fixture sono documenti scarni: su una fattura reale con venti righe il rapporto scenderà, ma
resta un ordine di grandezza. Sul `Classificatore`, che oggi manda **tutte** le pagine a T2 per
decidere una parola, il risparmio è immediato e senza contropartite.

> **Attenzione a non concludere troppo.** I PDF fixture sono generati da `reportlab` e **non hanno
> vera struttura tabellare**: le pipe che si vedono nel Markdown (`## Descrizione | Quantita |
> Importo`) sono testo letterale del sorgente, non una tabella ricostruita. La prova che
> TableFormer funziona viene dal **DOCX** (§3.3), non da questi PDF. Per giudicare la resa sulle
> tabelle dei PDF servono **fatture vere**.

### 3.6 Il blocco DGX Spark: sm_121

Entrambe le varianti dell'immagine sono multi-arch (`docker manifest inspect` → `linux/amd64`,
`linux/arm64`), il che sembrerebbe risolvere il problema dello Spark. **Non lo risolve.** Eseguendo
`torch.cuda.get_arch_list()` dentro le due immagini:

| Immagine | Architetture CUDA compilate | `sm_121`? |
|---|---|---|
| `docling-serve-cu130:v1.29.0` **amd64** | `sm_75, sm_80, sm_86, sm_90, sm_100, sm_120` | **no** |
| `docling-serve-cu130:v1.29.0` **arm64** | `sm_80, sm_90, sm_100, sm_110, sm_120` | **no** |

Il GB10 del DGX Spark è **sm_121**. Il risultato atteso è `CUDA error: no kernel image is available
for execution on the device`, ed è esattamente quanto riportato da chi ha già provato Docling sul
GB10 sul forum NVIDIA, con in più `nvrtc: error: invalid value for --gpu-architecture` quando il
JIT tenta di ripiegare. **La soluzione riportata e verificata da quell'utente**: ricostruire
l'immagine sulla base **NGC `nvcr.io/nvidia/pytorch:26.01-py3`** (CUDA 13.1, PyTorch 2.10 con
kernel sm_121), installandoci sopra `docling-serve` via pip.

Conseguenza pratica per l'infrastruttura:

- **RTX 4090 (sm_89) e RTX 3080 (sm_86)**: immagine ufficiale, funziona oggi, zero lavoro.
- **DGX Spark (sm_121)**: serve un `Dockerfile` nostro su base NGC. È lavoro noto e circoscritto,
  ma **è lavoro**, e va messo a piano prima di considerare lo Spark il nodo di produzione.

### 3.7 Due dettagli operativi che costano tempo se non si sanno

**L'OCR non gira su GPU.** `onnxruntime` nell'immagine espone solo
`['AzureExecutionProvider', 'CPUExecutionProvider']`: nessun `CUDAExecutionProvider`. Layout e
tabelle sono su GPU (torch), **l'OCR è su CPU**. Va bene — 1,14 s/pagina è accettabile — ma la
richiesta «deve usare la GPU» è soddisfatta **solo in parte**, e sui documenti scansionati in massa
la CPU torna a essere il collo di bottiglia.

**La latenza HTTP ha un pavimento.** L'endpoint sincrono `/v1/convert/file` interroga la coda
interna ogni `sync_poll_interval` secondi (default **2**, tipo `int`: `0.1` fa crashare il
container all'avvio con un errore di validazione pydantic). Con una conversione da 0,13 s la
risposta arriva comunque dopo ~2 s. Portandolo a `1`, la stessa fattura torna in **1,01 s**. Per
l'integrazione vera esiste `/v1/convert/file/async` + `/v1/status/poll/{task_id}`, che si sposa
esattamente con il `BackgroundTasks` già usato in `documents.py`.

*(Terzo dettaglio, gratuito: da Python su Windows, `http://localhost:5001` costa **+21 s** di
timeout IPv6 prima di ripiegare su IPv4. Con `127.0.0.1` sparisce. In compose, chiamando il
servizio per nome, non si presenta — ma in sviluppo fa perdere un pomeriggio.)*

---

## 4. Cosa risolverebbe, concretamente

Non "migliore accuratezza" in astratto: cinque problemi già presenti nel repo, ora con un numero
accanto.

1. **Il tier T3 diventa valutabile sul serio.** Gli esempi `non_rigiocabili` per assenza di strato
   testuale scendono verso zero (§3.4), e il testo offerto al modello locale conserva tabelle e
   ordine di lettura invece di essere appiattito. È il beneficio più grosso e il meno ovvio:
   sblocca la distillazione verso un modello piccolo *solo testo*, che è la direzione della Fase 3.
2. **Il dataset di fine-tuning cambia natura.** Il trace digerisce comunque le stringhe oltre 400
   caratteri, ma un Markdown è **ricostruibile in modo deterministico e verificabile** con lo stesso
   meccanismo già scritto in `_reidrata_prompt` (ricalcolo dello sha256, sostituzione solo se
   combacia). Da "reidrata immagini" a "reidrata testo".
3. **Il classificatore costa 16–34 volte meno** (§3.5), e una classificazione sbagliata non è
   bloccante: `workflow_per` non solleva mai e ricade sul fallback del manifest.
4. **Le tabelle arrivano come tabelle** (§3.3): righe di fattura, computo di un SAL, ore di un
   rapportino.
5. **DOCX e XLSX diventano leggibili**, e oggi sono un rifiuto secco. Per un'impresa edile,
   preventivi e computi in Word/Excel non sono un caso di nicchia: sono la norma.

E un beneficio non funzionale che vale come argomento commerciale: con Docling in casa, **le pagine
dei documenti non escono più verso il provider LLM**. Su fatture con dati di fornitori e dipendenti
è un miglioramento sostanziale della postura privacy.

---

## 5. Opzioni architetturali

### Opzione A — Sidecar con GPU + tool nativo che lo chiama ✅ **consigliata**

Un secondo container nello stesso `docker-compose.yml`, con la GPU riservata, e in
`backend/app/core/tools/leggi_documento.py` un tool nativo che fa una POST con `httpx` (già
dipendenza del progetto, usata per l'integrazione ERP).

```yaml
  docling:
    image: quay.io/docling-project/docling-serve-cu130:v1.29.0   # su Spark: immagine nostra su base NGC
    environment:
      DOCLING_DEVICE: cuda
      DOCLING_SERVE_SYNC_POLL_INTERVAL: "1"
    deploy:
      resources:
        reservations:
          devices: [{driver: nvidia, count: 1, capabilities: [gpu]}]
```

**Perché è la forma giusta, ora che l'infrastruttura è on-premise:**

- Il container dell'app **non cambia**: niente torch, niente 9 GB di immagine, `make dev` resta
  quello di oggi. Il peso sta dove c'è la GPU.
- `runtime.py` **non cambia di una riga**: `_risultato_per_llm` si ramifica *solo* sulla chiave
  `immagini_png_base64`; un risultato Markdown attraversa il runtime come un normale JSON.
- Quale workflow usa il nuovo tool è dichiarato **nel manifest**, e *come* usarlo è scritto nella
  **skill**: dato, non codice, come impone `CLAUDE.md`.
- Il precedente esiste già ed è dello stesso progetto: l'integrazione ERPNext è un adattatore
  outbound `httpx` verso un servizio esterno.
- Se il sidecar è spento, il tool non si registra e il sistema si comporta **esattamente** come
  oggi.

### Opzione B — Docling in-process nel container dell'app ❌

Porterebbe PyTorch e 9 GB di immagine dentro l'app, che è single-writer e monolitica, e
legherebbe il ciclo di vita del parser a quello dell'API. Con la GPU in azienda non c'è alcuna
ragione per farlo.

### Opzione C — Sostituire `ocr_pdf` ❌

Rompe le skill di 4 workflow, invalida il confronto storico di `eval_t3`, disallinea il T3
fine-tuned sul routing (`docs/finetuning-runbook.md`: routing `ocr_pdf` 3/3) e **toglie la strada
migliore per le foto**: su una foto storta scattata in cantiere, un modello vision legge meglio di
OCR + layout. I due percorsi devono convivere.

### Opzione D — Docling come tool consolidato del Toolsmith ❌ **impossibile**

Da escludere esplicitamente perché è la strada che la Fase 3 suggerirebbe per istinto.
`sandbox.py` ha `WHITELIST_PREDEFINITA = {math, datetime, decimal, re}`, vieta `open`/`__import__`
per AST e azzera `RLIMIT_FSIZE`: un tool sandboxato **non può leggere un file, importare torch, né
uscire in rete**. Il commento nel sorgente lo dice già: «il Toolsmith di F3 consolida calcoli, non
l'OCR». Docling è una **capacità nativa della cornice**, come `pymupdf`.

---

## 6. Impatto tecnico, file per file

| Punto | Impatto | Nota |
|---|---|---|
| `backend/pyproject.toml` | **Nessuna dipendenza nuova**: il tool parla HTTP con `httpx`, già presente. | È il vantaggio principale del sidecar. |
| `Dockerfile` dell'app | **Nessuna modifica.** | |
| `docker-compose.yml` | +1 servizio con `devices: [gpu]` e +2 variabili (`DOCLING_URL`, timeout). | |
| `core/tools/leggi_documento.py` | **Nuovo**: `SCHEMA` + `esegui(...)` → `{"pagine": N, "markdown": "…"}`. Deve fallire come `ocr_pdf` (`ToolError`), mai propagare un errore HTTP. | |
| `core/tools/__init__.py` | +1 riga nel registro, +1 in `_ciclo`/`_origine`; registrazione **condizionata** alla presenza di `DOCLING_URL`. | Il `Toolset` è già progettato per questo. |
| `core/runtime.py` | ~~Nessuna modifica.~~ **Servivano ~10 righe** — vedi §11.2: un manifest che dichiara un tool non disponibile faceva fallire ogni run. | Il Markdown lungo viene troncato dal client (`DOCLING_MAX_CARATTERI`), così non gonfia il contesto dei 12 giri. |
| `core/classificatore.py` | Modifica *puntuale*: usa `ocr_pdf.esegui` direttamente, non via `Toolset`. | Qui la scelta di modalità è **codice**, non manifest: renderla dato richiede un campo nel manifest di `classifica-documento`. |
| `api/documents.py` | `ESTENSIONI_LEGGIBILI` si allarga a `.docx`/`.xlsx` **solo se** il sidecar è attivo. | Altrimenti si accetta un file che poi nessuno sa leggere. |
| `data/workflows/*/manifest.yaml` + `skills/*.md` | Dato: `tools:` + la procedura al punto 1 della skill. | Passa dall'Improver + approvazione admin (bump di `version`). |
| `core/eval_t3.py` | `_pagine_testuali` guadagna una terza modalità; `modalita_documento` diventa ternario. | Il valore va **dichiarato nel report**: la stessa misura su testo/immagini/markdown non dà lo stesso numero. |
| `training/build_sft_dataset.py`, `docs/finetuning-runbook.md` | Il ramo `if chiamata["name"] == "ocr_pdf"` va esteso; `tipo_esempio: "routing"` cambia semantica con due tool di lettura. | |
| Test | `test_tools.py`, `test_runtime.py`, `test_skills_tools.py`, `test_pytools.py`, `test_eval_t3*.py` asseriscono **insiemi chiusi** di nomi di tool (`attesi = {...}`). | Aggiungere un tool li rompe per costruzione: va messo in conto. |
| `backend/tests/fake_llm.py` | Il finto sceglie i tool per nome (`if "ocr_pdf" in offerti`). | *Il finto deve rifiutare come il reale*: se accetta entrambi i percorsi con la stessa disinvoltura, i test non provano nulla. |

---

## 7. Rischi

### 7.1 sm_121 sul DGX Spark — **il rischio numero uno** (§3.6)
Non è un dettaglio di tuning: sullo Spark l'immagine ufficiale **non parte sulla GPU**. Va
pianificata un'immagine nostra su base NGC `pytorch:26.01-py3`, con il costo di manutenzione che
comporta (seguire le release di `docling-serve` invece di consumarle). Finché non è pronta,
**il nodo GPU per Docling è la 4090**, non lo Spark.

### 7.2 Due tool di lettura confondono il modello
`runtime._estrai_su_tier` offre allo step i tool del manifest **più tutti i consolidati**. Con due
tool che a occhio fanno la stessa cosa, il modello può chiamarne uno, l'altro o entrambi,
raddoppiando il costo. Mitigazione: descrizioni nettamente disgiunte nello `SCHEMA` («documento
nato digitale, testo e tabelle» vs «foto o scansione, pagine come immagini») e procedura esplicita
nella skill. Da **misurare** con `eval_t3`, non da assumere.

### 7.3 Determinismo e riproducibilità
`/data` è la fonte di verità e ogni mutazione è un commit. Docling introduce **modelli con
versione** nella catena: aggiornare l'immagine cambia il Markdown a parità di PDF, quindi cambia il
contesto degli esempi rigiocati da `eval_t3` e il confronto con i golden. Va **pinnata la versione
esatta dell'immagine** (mai `latest` — che per le varianti CUDA non esiste nemmeno) e registrata
nel trace, come si registra il modello LLM.

### 7.4 Un servizio in più da tenere in piedi
Il sidecar può essere giù mentre l'app è su. Il tool deve degradare in `ToolError` e la skill deve
poter proseguire con `ocr_pdf`: **mai un single-point-of-failure** sull'ingestione, che è il
contratto dichiarato in `documents.py` («MAI un errore bloccante»).

### 7.5 OCR su CPU (§3.7)
Layout e tabelle sono su GPU, l'OCR no. Su un arretrato di documenti scansionati la CPU torna
centrale. Se diventasse un problema: `onnxruntime-gpu` nell'immagine, o l'engine OCR NVIDIA
(Nemotron, che però vincola CUDA e Python), o la `VlmPipeline` con `granite-docling-258M`
interamente su GPU — quest'ultima è anche l'opzione più coerente con la direzione T3, ma cambia
profilo di risorse e va decisa a parte.

---

## 8. Percorso proposto (a milestone, dopo M21)

Nessuna di queste fasi è aperta da questa analisi. §3 copre già, di fatto, la vecchia M22.

**M22 — Confronto sui golden (la prova che manca).**
Rigiocare l'estrazione delle fatture con i due input — PNG di oggi contro Markdown Docling — e
confrontare i campi con il ground truth di `fixtures/_manifest.json` (`ritenuta_acconto: 800.0`,
lo scenario che `CLAUDE.md` dichiara non può rompersi). **Su fatture vere**, non sui fixture
sintetici (§3.5, riquadro). *Criterio d'uscita*: Docling non peggiora nessun campo.

**M23 — Immagine Docling per DGX Spark.**
`Dockerfile` su base NGC `pytorch:26.01-py3` con `docling-serve` via pip; verifica che
`torch.cuda.get_arch_list()` contenga `sm_121` e che il banco del §3 dia gli stessi risultati.
*Criterio d'uscita*: le stesse misure girano sullo Spark. Può procedere in parallelo a M22.

**M24 — Sidecar + tool `leggi_documento`.**
Servizio nel compose, tool nativo `httpx` registrato solo se `DOCLING_URL` è valorizzata, endpoint
**async** (non il sincrono), fallback esplicito a `ocr_pdf` su qualunque fallimento. Nessuna
modifica a `runtime.py`/`gateway.py`/`dal.py`.

**M25 — Adozione per workflow (dato) + classificatore + DOCX.**
Manifest e skill dei workflow che leggono PDF nativi; classificatore sul Markdown della prima
pagina; `ESTENSIONI_LEGGIBILI` allargata a Word/Excel quando il sidecar è attivo. Bump di
`version` via Improver + approvazione admin.

**M26 — Riallineare l'harness T3 e il dataset.**
Terza modalità in `eval_t3`, `modalita_documento` ternario, `build_sft_dataset.py` esteso, runbook
aggiornato. *Criterio d'uscita*: i `non_rigiocabili` scendono e il confronto T3/T1 resta onesto.

---

## 9. Domande aperte — servono decisioni, non altra analisi

1. **Chi ospita il sidecar in produzione: Spark o 4090?** Dalla risposta dipende se M23 è
   bloccante o rimandabile. Sulla 4090 si parte domani.
2. **Che mix di documenti arriva davvero?** Se prevalgono le foto da cantiere, il beneficio è
   minore di quanto suggerisca il §3: Docling brilla sui PDF nativi e sui file d'ufficio. Il dato
   si ricava dai `blobs/caricati/` di un'installazione reale.
3. **DOCX/XLSX entrano nello scope funzionale?** Tecnicamente è gratis (§3.3). Ma un preventivo in
   Word è un *tipo documento* nuovo: vuole uno schema entità, un manifest e una skill — cioè M20/M21,
   non questa analisi.
4. **La `VlmPipeline` è nello scope?** Una lettura interamente on-premise su GPU è coerente con la
   direzione T3 e con l'hardware disponibile, ma è una strategia, non un dettaglio implementativo.

---

## 10. Conclusione

Le prove dicono che la parte difficile non è la parte difficile. Docling gira su GPU con una riga
di `docker run`, i modelli sono già nell'immagine, converte più veloce di quanto il resto della
catena possa consumare, legge il Word che oggi rifiutiamo e ritrova la ritenuta d'acconto **su una
scansione senza testo** — che è precisamente il punto dove il sistema attuale si arrende.

Il lavoro vero è altrove, ed è in due punti: **l'immagine per lo Spark** (sm_121, §3.6) e la
**convivenza dei due percorsi di lettura** senza rompere il ground truth accumulato (§7.2, §7.3).

La forma resta quella di sempre in questo progetto: una **capacità in più**, isolata in un servizio
che parla HTTP, offerta ai workflow come **dato** (manifest + skill), con `runtime.py`,
`gateway.py` e `dal.py` che non cambiano di una riga. Il percorso multimodale non è un debito da
estinguere: è la strada giusta per la foto storta scattata in cantiere, ed è il ground truth su cui
è misurato tutto quello che c'è oggi.

---

### Riferimenti

- [Docling — documentazione ufficiale](https://docling-project.github.io/docling/getting_started/installation/)
- [docling-serve — immagini container e API](https://github.com/docling-project/docling-serve)
- [Docling Technical Report (arXiv 2408.09869) — pipeline, TableFormer, misure su CPU](https://arxiv.org/html/2408.09869v5)
- [granite-docling-258M (VlmPipeline)](https://huggingface.co/ibm-granite/granite-docling-258M)
- [Forum NVIDIA — «GB10 and Docling»: l'errore sm_121 e la soluzione con NGC `pytorch:26.01-py3`](https://forums.developer.nvidia.com/t/gb10-and-docling/360665)

---

## 11. Cosa è stato realizzato (31/07/2026)

L'integrazione è **a bordo e funzionante su questa macchina**. Quanto segue non è progetto: è
stato eseguito e verificato.

### 11.1 La prova che conta

Una **fattura in Word** — formato che il sistema prima rifiutava per estensione — caricata
dall'interfaccia sul backend vero, con LLM reale (`gpt-5.5`) e sidecar acceso:

```
tool_call  leggi_documento    ok=True   blobs/caricati/2026/…-fattura-bianchi-22-2026.docx
tool_call  cerca_fornitore    ok=True   "Studio Tecnico Ing. Bianchi 02644330877"
tool_call  cerca_cantiere     ok=True   "Residenza Le Palme"
tool_call  salva_bozza        ok=True   FT-2026-0049
```

Estratto: `imponibile 5500.0`, `iva 1210.0`, `totale 6710.0`, **`ritenuta_acconto 1100.0`**,
tre righe con quantità e unità di misura, `fornitore_id FRN-007`, `cantiere_id CNT-001`.
Tre chiamate LLM, nessun `ocr_pdf`: il documento è stato letto **una volta sola**, come testo.

Un secondo caricamento, un **DDT in Word**, è stato instradato dal classificatore su
`carica-ddt` — e non sul fallback `carica-fattura`: prova che il classificatore ha letto il
*testo* del documento, cosa che su un `.docx` nessun modello vision può fare.

*(In quel DDT `fornitore_id` è rimasto `null` con `riferimenti_estratti` compilato: la partita
IVA inventata nel documento di prova ha abbassato il punteggio della ricerca a 0.737, sotto la
soglia di 0.75. Il sistema si è comportato come la skill impone — non collegare a caso — ed è la
conferma che il margine misurato in [[collegare-anagrafica-soglia-e-margine]] regge anche sulla
strada nuova.)*

### 11.2 Le scelte prese, e dove si discostano dall'analisi

| Scelta | Perché |
|---|---|
| **Sidecar HTTP**, non dipendenza in-process (Opzione A del §5) | Il container dell'app resta identico: zero dipendenze nuove, `httpx` c'era già per l'ERP. |
| Endpoint **sincrono**, non asincrono | Il §5 proponeva l'async per via del pavimento di latenza; con `DOCLING_SERVE_SYNC_POLL_INTERVAL=1` il pavimento è 1 s, la chiamata è già dentro un `BackgroundTask` e il codice è molto più semplice. Rivedibile se i documenti diventassero lunghi. |
| **`runtime.py` è cambiato** (≈10 righe) | L'analisi diceva "zero righe". Era sbagliato: un manifest che dichiara `leggi_documento` con il sidecar spento fa sollevare `schemi()` e **ogni** run fallisce. Ora il runtime separa i tool dichiarati in *disponibili* e *mancanti*, usa i primi e dichiara i secondi nel log — che vale anche da rete per un refuso nel manifest. |
| Le **foto restano a `ocr_pdf`** | `leggi_documento` rifiuta `.jpg`/`.png` di proposito: su una foto storta il modello vision legge meglio. Il rifiuto è una scelta, ed è coperto da un test. |
| `.docx`/`.xlsx` accettati **solo col sidecar** | Accettare un file che poi nessuno sa leggere darebbe all'operatore un semaforo rosso invece di un rifiuto immediato e comprensibile. |

### 11.3 File toccati

**Nuovi**: `backend/app/core/docling.py` (client, config da env, trasporto iniettabile),
`backend/app/core/tools/leggi_documento.py` (il tool), `backend/tests/fake_docling.py`,
`backend/tests/test_docling.py` (27 test), `scripts/docling_check.py` (diagnostica).

**Modificati**: `tools/base.py` (perimetro del repo dati condiviso fra i due tool di lettura),
`tools/__init__.py` (registrazione condizionata + `disponibili()`), `runtime.py`,
`classificatore.py` (preferisce il testo, ricade sulle immagini), `api/documents.py`
(estensioni d'ufficio), `api/deps.py`, `api/dataset.py`, `api/workflows.py`, `main.py`,
`tests/conftest.py` (pulizia `DOCLING_*`, come già per `ERP_*`), `tests/fake_llm.py` (il finto
sceglie lo strumento di lettura e sa ripiegare), `docker-compose.yml` (servizio con GPU dietro
il profilo `docling`), `Makefile`, `.env.example`, `deploy.env.example`, `README.md`,
`docs/deploy.md`.

**Dato** (`backend/app/seed_assets/workflows/` e `data/workflows/`): i 4 manifest d'ingresso
dichiarano `leggi_documento`, e le 4 skill spiegano quando usare l'uno e quando l'altro.

### 11.4 Verifiche

- **552 test verdi** (erano 525): i 27 nuovi coprono client, tool, registrazione condizionata,
  perimetro, troncamento, qualità bassa, il giro completo su `.docx`, il ripiego su `ocr_pdf`
  con sidecar giù, il classificatore, e l'ingestione con e senza sidecar.
- La suite passa **identica con il sidecar spento**: è l'invariante difeso più di ogni altro —
  una capacità in più non deve poter diventare una capacità in meno.
- `ruff` pulito. `make docling-check` verde su questa macchina (GPU al 52%, DOCX con tabella).

### 11.5 Cosa resta aperto

1. **DGX Spark (§3.6)**: immagine su base NGC `pytorch`. Finché non c'è, il nodo per Docling è
   la 4090. È il primo lavoro da fare se lo Spark deve essere il nodo di produzione.
2. **M22 — confronto sui golden**: l'estrazione con i due input a confronto su **fatture vere**.
   I fixture sintetici non hanno vera struttura tabellare e non possono decidere la questione.
3. **M26 — harness T3**: `eval_t3` non conosce ancora la modalità `markdown`; è il beneficio
   più grosso di tutta l'operazione (§4.1) e non è stato ancora incassato.
4. **Il classificatore legge il testo per codice, non per manifest**: se lo si vuole
   configurabile serve un campo nel manifest di `classifica-documento`.
5. **DOCX/XLSX come *tipo documento***: oggi un preventivo in Word viene letto e instradato sui
   workflow esistenti. Un "preventivo" come entità di prima classe è M20/M21, non questo lavoro.
