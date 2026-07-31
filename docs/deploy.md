# Mettere in piedi una versione di prova

Guida al deploy di Workflower come **singolo container** (il backend FastAPI
serve anche il frontend buildato), con `docker compose` sul `Dockerfile` del repo.
Il target è una **macchina che controlliamo noi** — il server aziendale o una VPS —
non una piattaforma managed: lo stato è un repo git su disco e l'infrastruttura di
riferimento è on-premise con GPU NVIDIA (vedi §B).

## Il vincolo da tenere presente

Lo stato del sistema è un **repo git su disco** (`DATA_DIR`, “ogni mutazione = un
commit”): l'app **non** è stateless. Serve un host con **volume persistente**.
Niente serverless/edge (Vercel, Netlify, Cloudflare Workers, Lambda): perderebbero
i dati a ogni riavvio. Tutti i target qui sotto montano un volume su `/data` e
usano `DATA_DIR=/data/repo` (una sottocartella, così eventuali `lost+found` del
volume non disturbano il seed).

Al **primo avvio** l'`entrypoint` fa il seed del repo dati (utenti demo, schemi,
workflow); ai successivi lo trova già presente e parte e basta.

## Prima di esporre l'app (vale per tutti)

- **`JWT_SECRET`**: metti una stringa lunga e casuale (la imposti tu in `.env`).
- **PIN demo**: `salvo/1111`, `giovanna/9999`… sono in `backend/app/seed_data.py`.
  Se l'URL è pubblico, cambiali **prima** del seed (il seed li legge da lì).
- **Modelli/costi LLM**: ogni documento elaborato è una chiamata al tier T1
  (SOTA). Per una prova puoi mettere un modello economico su **entrambi** i tier.
  Tieni `DIAGNOSTICA_AUTO=0` (l'analisi errori la lanci a mano dalla pagina
  *Diagnosi*), così non consuma da sola.
- **Un solo worker**: il DAL è single-writer sul repo dati. Non aumentare i
  worker di uvicorn né scalare a più macchine che condividono lo stesso volume.
- **Backup**: dato che `/data/repo` *è* un repo git, un `git push` periodico verso
  un remoto privato ti dà backup e storia.
- **Documenti di prova**: i PDF sintetici (fatture, DDT, SAL…) si generano in
  locale con `make fixtures` e si caricano dall'interfaccia Operatore. In
  alternativa carichi tue fatture reali.

Variabili d'ambiente (tutte le piattaforme):

| Variabile | Obbligo | Esempio |
|---|---|---|
| `JWT_SECRET` | sì | stringa casuale |
| `LLM_T1_MODEL` | sì | `openai/gpt-5.6-sol` |
| `LLM_T2_MODEL` | sì | `openai/gpt-5.6-terra` |
| `OPENAI_API_KEY` (o `ANTHROPIC_API_KEY`/`GEMINI_API_KEY`) | sì | … |
| `DATA_DIR` | sì | `/data/repo` |
| `FRONTEND_DIST` | sì (immagine) | `/app/frontend_dist` |
| `LOG_LEVEL` | no | `INFO` |
| `DIAGNOSTICA_AUTO` | no | `0` |

---

## A) Docker Compose su una macchina nostra (il target)

Su una macchina con Docker — il server aziendale, o una VPS:

```bash
git clone <repo> && cd workflower
cp deploy.env.example .env      # riempi JWT_SECRET, modelli, chiave LLM
# per HTTPS: in .env metti SITE_ADDRESS=tuo.dominio (il DNS deve puntare al server)
# per una prova veloce senza dominio: lascia SITE_ADDRESS=:80 e usa http://IP
docker compose up -d --build
```

- App dietro **Caddy** (`docker-compose.yml` + `Caddyfile`): con un dominio in
  `SITE_ADDRESS`, il certificato HTTPS è automatico; con `:80` resti in HTTP.
- Dati nel volume `workflower-data`. Log: `docker compose logs -f app`.
- Aggiornare: `git pull && docker compose up -d --build`, **seguito da**
  `docker compose exec app python -m app.sync_workflows` (mostra i manifest e le
  skill rimasti indietro) e `… --applica` per riallinearli. Il seed non tocca un
  repo dati che esiste già: senza questo passaggio una funzione nuova può restare
  inattiva senza dare errore. Dettagli e garanzie nel README, sezione
  «Aggiornare un'installazione esistente».

## B) Infrastruttura on-premise (il riferimento)

Il deploy di riferimento è **in azienda**, su hardware con GPU NVIDIA:

| Macchina | Ruolo | Note |
|---|---|---|
| **DGX Spark** (GB10, `arm64`) | server dei modelli locali: tier T3, parser documenti | memoria unificata: ci sta molto più di quanto sembri, ma è `aarch64` — **ogni immagine deve essere multi-arch** |
| **RTX 4090** (24 GB, `x86_64`) | secondo nodo GPU / staging | |
| **RTX 3080** (8 GB, `x86_64`) | PC di sviluppo | il banco di prova quotidiano |

Conseguenze pratiche sul deploy:

- Il container dell'app **non** ha bisogno di GPU: resta quello di §A. Ciò che va
  sulla GPU sono i **servizi affiancati** (parser documenti, endpoint T3), come
  container separati nello stesso compose o su un host dedicato.
- Per usare la GPU da Docker serve il **NVIDIA Container Toolkit** sull'host e,
  nel compose, la risorsa dichiarata:

  ```yaml
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
  ```

  In alternativa, per un `docker run` una tantum: `--gpus all`.
- **Multi-arch**: qualunque immagine di terze parti destinata allo Spark va
  verificata **prima** con `docker manifest inspect <img> | grep arm64`. Un'immagine
  solo `amd64` non gira sullo Spark, e l'emulazione non è un'opzione per la GPU.
- Niente HTTPS pubblico obbligatorio: in LAN aziendale `SITE_ADDRESS=:80` basta;
  con un dominio interno e DNS, Caddy fa il certificato come in §A.

### Il parser documenti (Docling) su GPU

Servizio **opzionale**: acceso, i PDF nati al computer, i Word e gli Excel vengono
letti come testo con le tabelle ricostruite (16–34 volte meno token delle stesse
pagine come immagini, e i `.docx`/`.xlsx` diventano caricabili). Spento, tutto
funziona come prima: le pagine vanno all'LLM come immagini.

```bash
make docling-up          # docker compose --profile docling up -d docling
make docling-check       # risponde? converte? sta usando la GPU?
```

Poi in `.env`: `DOCLING_URL=http://docling:5001` (dentro al compose l'host è il
**nome del servizio**). In sviluppo fuori da compose, `http://127.0.0.1:5001` —
e **non** `localhost`, che su Windows costa ~21 s di timeout IPv6 per chiamata.

Serve il **NVIDIA Container Toolkit** sull'host. Verifica in un colpo solo:

```bash
docker run --rm --gpus all quay.io/docling-project/docling-serve-cu130:v1.29.0 python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

> **DGX Spark**: l'immagine ufficiale `-cu130` (sia amd64 sia arm64) porta kernel
> CUDA fino a `sm_120`, mentre il GB10 è `sm_121`: sullo Spark **non parte sulla
> GPU** (`no kernel image is available for execution on the device`). Serve
> un'immagine ricostruita su base NGC `nvcr.io/nvidia/pytorch`, da mettere in
> `DOCLING_IMAGE`. Su RTX 4090 e 3080 l'immagine di serie va così com'è.
> Dettagli e misure in [`analisi-docling.md`](../analisi-docling.md).

---

## Verifica rapida (dopo il deploy)

1. Apri l'URL: deve comparire la landing (redirige a `/op` o `/admin`).
2. `GET /api/health` → `{"status":"ok"}`.
3. Accedi come `giovanna` / `9999` (admin) → **Cruscotto**.
4. Come `salvo` / `1111` (operatore) → **Carica** un PDF → compare il riepilogo.
5. Admin → **Log** (eventi di tutte le fasi) e **Diagnosi** (analisi errori).

## Build/prova in locale (senza piattaforma)

```bash
docker build -t workflower .
docker run --rm -p 8000:8000 \
  -e JWT_SECRET=dev -e LLM_T1_MODEL=openai/gpt-5.6-sol -e LLM_T2_MODEL=openai/gpt-5.6-terra -e OPENAI_API_KEY=... \
  -v workflower-data:/data workflower
# → http://localhost:8000
```
