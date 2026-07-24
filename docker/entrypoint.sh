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

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
