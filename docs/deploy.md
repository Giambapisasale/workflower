# Mettere in piedi una versione di prova

Guida al deploy di Workflower come **singolo container** (il backend FastAPI
serve anche il frontend buildato). Tre target pronti: **VPS con Docker Compose**,
**Render**, **Fly.io**. Tutti usano lo stesso `Dockerfile`.

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

- **`JWT_SECRET`**: metti una stringa lunga e casuale (su Render è
  `generateValue`, altrove la imposti tu).
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
| `LLM_T1_MODEL` | sì | `anthropic/claude-sonnet-5` |
| `LLM_T2_MODEL` | sì | `anthropic/claude-haiku-4-5` |
| `ANTHROPIC_API_KEY` (o `OPENAI_API_KEY`/`GEMINI_API_KEY`) | sì | … |
| `DATA_DIR` | sì | `/data/repo` |
| `FRONTEND_DIST` | sì (immagine) | `/app/frontend_dist` |
| `LOG_LEVEL` | no | `INFO` |
| `DIAGNOSTICA_AUTO` | no | `0` |

---

## A) VPS con Docker Compose (il più prevedibile)

Su una macchina con Docker (Hetzner ~€4/mese, DigitalOcean, o la tua):

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
- Aggiornare: `git pull && docker compose up -d --build`.

## B) Render (managed, veloce)

1. Serve il **piano a pagamento** per il disco persistente (il free è effimero).
2. Su Render: **New → Blueprint**, punta al repo: legge `render.yaml`
   (servizio Docker + disco da 1 GB su `/data` + variabili).
3. Dopo il primo deploy, in **Environment** inserisci `ANTHROPIC_API_KEY` (e
   se vuoi cambia i modelli). `JWT_SECRET` è generato in automatico.
4. Health check già su `/api/health`. URL pubblico fornito da Render.

## C) Fly.io (VM leggera con volume)

```bash
fly launch --no-deploy --copy-config           # crea l'app da fly.toml
fly volumes create workflower_data --size 1 --region fra
fly secrets set JWT_SECRET=$(openssl rand -hex 32) \
                ANTHROPIC_API_KEY=... \
                LLM_T1_MODEL=anthropic/claude-sonnet-5 \
                LLM_T2_MODEL=anthropic/claude-haiku-4-5
fly deploy
fly scale count 1                              # una sola macchina (un volume)
```

Fly gestisce HTTPS in automatico sul dominio `*.fly.dev`.

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
  -e JWT_SECRET=dev -e LLM_T1_MODEL=... -e LLM_T2_MODEL=... -e ANTHROPIC_API_KEY=... \
  -v workflower-data:/data workflower
# → http://localhost:8000
```
