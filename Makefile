# Workflower — comandi di sviluppo (vedi CLAUDE.md)
.PHONY: setup dev dev-api dev-web test seed fixtures samples demo lint

ifeq ($(OS),Windows_NT)
SHELL := cmd.exe
.SHELLFLAGS := /C
PY := backend\.venv\Scripts\python.exe
PYBOOT := py -3.12
else
PY := backend/.venv/bin/python
PYBOOT := python3.12
endif

setup: ## Prima installazione: venv backend + dipendenze frontend
	$(PYBOOT) -m venv backend/.venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e "backend[dev]"
	npm --prefix frontend install

dev: ## Avvia backend (:8000) e frontend (:5173)
	$(MAKE) -j 2 dev-api dev-web

dev-api:
	$(PY) -m uvicorn app.main:app --reload --reload-dir backend --app-dir backend --port 8000

dev-web:
	npm --prefix frontend run dev

test: ## Test backend (pytest)
	$(PY) -m pytest backend/tests

seed: ## Crea il repo dati d'esempio in ./data (repo git separato)
	$(PY) -m app.seed

fixtures: ## Genera i PDF sintetici in ./fixtures (3 fatture + DDT/SAL/rapportino)
	$(PY) -m app.fixtures
	$(PY) -m app.fixtures_docs

samples: ## Rigenera i PDF di esempio committati (backend/app/seed_assets/samples)
	$(PY) -c "from pathlib import Path; from app.fixtures import genera; from app.fixtures_docs import genera as g2; d=Path('backend/app/seed_assets/samples'); genera(d); g2(d)"

demo: ## Prepara la demo: seed (se serve) + fixtures + giro guidato
	-$(PY) -m app.seed
	$(PY) -m app.fixtures
	$(PY) -m app.fixtures_docs
	@$(PY) -c "print('\n== Demo pronta ==\n- Utenti: salvo/1111 (operatore, cantiere Le Palme), giovanna/9999 (ufficio/admin)\n- Avvia tutto con:  make dev\n- Operatore: http://localhost:5173/op   Admin: http://localhost:5173/admin\n- Carica fixtures/fattura-studio-bianchi.pdf (ha la ritenuta): la v1.0 non la estrae.\n- Il giro completo (segnala -> Improver -> approva v1.1 -> ritenuta estratta) e in README.md\n')"

lint: ## Ruff (backend) + ESLint (frontend)
	$(PY) -m ruff check backend
	npm --prefix frontend run lint
