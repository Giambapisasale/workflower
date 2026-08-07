#!/bin/sh
# Avvio del container: fa il seed del repo dati al primo giro, poi lancia l'app.
#
# DATA_DIR è una SOTTOcartella del volume (/data/repo): così eventuali file del
# filesystem del volume (es. lost+found) non disturbano il seed né il repo git.
# UN SOLO worker: il DAL è single-writer sul repo dati, non va parallelizzato.
set -e

DATA_DIR="${DATA_DIR:-/data/repo}"
mkdir -p "$DATA_DIR"

if [ ! -d "$DATA_DIR/.git" ]; then
  echo "→ primo avvio: seed del repo dati in $DATA_DIR"
  python -m app.seed
else
  echo "→ repo dati già presente in $DATA_DIR"
fi

# Il seed gira una volta sola, ma il volume sopravvive all'immagine: un'immagine
# nuova porta workflow e schemi nuovi che, senza questo passo, non arrivano mai
# al repo dati. Il difetto non dà errore — dà una funzione che manca (un tool
# che il manifest non dichiara, un campo che lo schema non estrae) finché
# qualcosa non prova a leggere un file che non c'è. Non tocca i file modificati
# a valle dall'Improver o a mano: per quelli serve `--forza`, che resta umano.
if [ "${SYNC_DATI_AVVIO:-1}" = "1" ]; then
  python -m app.sync_dati --applica --righe-diff 0
else
  echo "→ allineamento del repo dati disattivato (SYNC_DATI_AVVIO=0)"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
