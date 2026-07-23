PYTHON ?= python
PNPM ?= pnpm

.PHONY: setup lint typecheck test smoke paper-smoke demo docker-up docker-test reproduce-mini

setup:
	$(PYTHON) -m pip install -e ".[dev]"
	cd apps/web && $(PNPM) install --frozen-lockfile

lint:
	ruff check src tests scripts
	cd apps/web && $(PNPM) lint

typecheck:
	mypy src/evidroute
	cd apps/web && $(PNPM) typecheck

test:
	pytest --cov=evidroute --cov-report=term-missing
	cd apps/web && $(PNPM) test

smoke:
	$(PYTHON) -m evidroute.cli smoke --output artifacts/smoke

paper-smoke:
	$(PYTHON) -m evidroute.cli paper-smoke

demo:
	$(PYTHON) -m evidroute.cli demo

docker-up:
	docker compose up --build

docker-test:
	docker compose run --rm api pytest

reproduce-mini:
	$(PYTHON) -m evidroute.cli reproduce-mini --output artifacts/reproduce-mini
