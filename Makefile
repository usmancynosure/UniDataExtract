.PHONY: install install-all render-setup ui test lint format run samples clean

VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

install:                ## Create venv and install core dependencies
	python3 -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt

install-all: install    ## Install core + render + UI + dev extras
	$(PIP) install -r requirements-render.txt -r requirements-ui.txt pytest ruff

render-setup:           ## Download the Chromium browser for --render
	$(PY) -m playwright install chromium

ui:                     ## Launch the Streamlit web interface
	$(VENV)/bin/streamlit run app.py

test:                   ## Run the offline unit tests
	$(PY) -m pytest

lint:                   ## Lint with ruff
	$(VENV)/bin/ruff check unidata tests

typecheck:              ## Static type-check with mypy
	$(VENV)/bin/mypy

check: lint typecheck test  ## Run lint + type-check + tests

format:                 ## Auto-format with ruff
	$(VENV)/bin/ruff format unidata tests

run:                    ## Example: make run DOMAIN=bucknell.edu
	$(PY) main.py $(DOMAIN)

samples:                ## Regenerate sample output for the three reference schools
	$(PY) main.py bucknell.edu salisbury.edu udc.edu --out-dir samples

clean:
	rm -rf $(VENV) **/__pycache__ .pytest_cache

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
