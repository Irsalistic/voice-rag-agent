PYTHON ?= python3

.PHONY: install test lint format dev web compose

install:
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt
	cd frontend && npm install

dev:
	$(PYTHON) -m uvicorn app.main:create_app --factory --reload --app-dir backend --host 0.0.0.0 --port 8000

web:
	cd frontend && npm run dev

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check backend
	$(PYTHON) -m ruff format --check backend

format:
	$(PYTHON) -m ruff format backend
	$(PYTHON) -m ruff check --fix backend

compose:
	docker compose up --build
