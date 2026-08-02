# Preparare la demo

## 1. Accendere

Due modi, a seconda di dove sei.

**In locale, per lavorarci** (backend e frontend separati, ricaricamento a caldo):

```bash
make dev
```

**Per pulire variabili.**

```bash
Remove-Item Env:ERP_BASE_URL, Env:ERP_API_KEY, Env:ERP_API_SECRET, Env:ERP_COMPANY, Env:ERP_CONTO_IVA, Env:ERP_CONTO_RITENUTA, Env:ERP_ITEM_DDT -ErrorAction SilentlyContinue
```

Operatore su `http://localhost:5173/op`, ufficio su `http://localhost:5173/admin`.

**Con Docker, come in produzione** (un solo container che serve anche la UI,
dietro a Caddy):

```bash
docker compose up -d --build
```

Tutto su `http://localhost` — `/op` e `/admin`.

**Il parser documenti su GPU** (facoltativo ma consigliato per la demo: è quello
che permette di leggere Word ed Excel):

```bash
make docling-up && make docling-check
```
oppure specificando url docling
```bash
make docling-check ARGS="--url http://127.0.0.1:5001"
```

`make docling-check` deve stampare solo `PASS`, compresa la riga sulla GPU. Se
qualcosa è rosso, la demo funziona lo stesso ma senza i due esempi in Word.

**La contabilità** (facoltativo: serve solo se vuoi mostrare dove finiscono i
documenti validati):

```bash
make erp-up && make erp-dev-setup && make erp-smoke
```

Il secondo comando stampa le variabili `ERP_*` da mettere nel `.env` — senza
quelle l'integrazione parte **spenta senza dirlo**. Procedura completa e
copione in [08-contabilita-erpnext.md](08-contabilita-erpnext.md).

## 2. Credenziali

| Chi | Nome utente | Codice | Cosa vede |
|---|---|---|---|
| Salvo Torrisi | `salvo` | `1111` | Operatore, cantiere Residenza Le Palme |
| Giuseppe Leotta | `giuseppe` | `2222` | Operatore, Scuola Manzoni |
| Marco Finocchiaro | `marco` | `3333` | Operatore, Capannone Etna Sud |
| Giovanna Russo | `giovanna` | `9999` | **Ufficio** (vede tutto) |

Sono i codici del seed d'esempio. In un'installazione vera si cambiano al primo
avvio — se il cliente lo chiede, è una domanda giusta: vedi
[07-domande-difficili.md](07-domande-difficili.md).

## 3. Rimettere l'ambiente com'era

Dopo una demo il repo dati è pieno di prove. Per ricominciare pulito **senza
buttare via quello che il sistema ha imparato** (i casi golden, il dataset delle
domande, l'anagrafica dell'azienda):

```bash
make demo-reset                 # mostra cosa conserverebbe e cosa perderebbe
```

```bash
make demo-reset ARGS=--applica  # lo fa
```

Se invece vuoi proprio azzerare tutto, storia compresa, c'è `make reseed` — ma
perdi anche i golden, che sono la cosa più costosa da rifare.

Dopo un aggiornamento del codice, allinea il repo dati:

```bash
make data-sync ARGS=--applica
```

Serve perché il seed crea `data/` una volta sola: senza questo passaggio i
manifest e gli schemi restano quelli del giorno dell'installazione, e una
funzione nuova resta **inattiva senza dare errore**.

## 4. Configurare l'azienda

Ufficio → Sistema → **La nostra azienda**. Metti denominazione, indirizzo e
partita IVA dell'impresa. Serve al controllo che verifica che le fatture in
arrivo siano intestate a voi e non a qualcun altro (esempio `05`).

Nel seed la denominazione è già «Costruzioni Aitho S.r.l.», che è
l'intestatario dei documenti d'esempio. La partita IVA è vuota di proposito:
compilala se vuoi mostrare anche il riconoscimento per partita IVA.

## 5. I documenti di prova

Stanno in [`esempi/`](esempi/) e si rigenerano con:

```bash
python guida_utente/genera_esempi.py
```

Sono dodici, uno per ogni strada del sistema. Il catalogo con l'esito atteso di
ciascuno è in [esempi/README.md](esempi/README.md). **Leggilo prima della demo**:
sapere in anticipo quale documento finisce in revisione e perché è la differenza
fra una dimostrazione e una figuraccia.

## Checklist, cinque minuti prima

- [ ] `make docling-check` tutto verde (o hai deciso di saltare gli esempi Word)
- [ ] Login `giovanna` / `9999` funziona, il Cruscotto mostra numeri
- [ ] Login `salvo` / `1111` funziona e mostra i quattro bottoni
- [ ] Ufficio → La nostra azienda è compilata
- [ ] La coda di Revisione **non** è vuota (se lo è, carica prima l'esempio 05)
- [ ] Se mostri la contabilità: `make erp-smoke` verde e la pagina
      Operatività → Contabilità **non** dice «spenta»
- [ ] Hai i file di `esempi/` a portata di mano, sul desktop
- [ ] Sai già cosa risponderai su costi, privacy e «e se sbaglia?»
      ([07](07-domande-difficili.md))

## Se qualcosa va storto durante la demo

**Un documento resta «Lo sto ancora leggendo…»** — l'elaborazione gira in
background e la pagina non si aggiorna da sola: ricarica. Se dopo un minuto è
ancora lì, il modello non risponde: passa a un altro esempio e riprendi dopo.

**Un caricamento diventa rosso** — è previsto, per due dei dodici esempi. Non
scusarti: è il caso più interessante da mostrare. Vai in Revisione e fai vedere
*perché* il sistema si è fermato.

**Il parser Word dà errore** — `docker compose --profile docling up -d docling`
e riprova. Nel frattempo usa gli esempi in PDF: la sostanza non cambia.

**Non parte niente** — Ufficio → Sistema → **Log**: c'è il registro applicativo
con la ricerca per testo. È anche un pezzo di demo, non solo un attrezzo.
