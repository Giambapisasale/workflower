# Workflower — comandi di sviluppo (vedi CLAUDE.md)
.PHONY: setup dev dev-api dev-web test seed lint

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

lint: ## Ruff (backend) + ESLint (frontend)
	$(PY) -m ruff check backend
	npm --prefix frontend run lint
