# =============================================================================
# JewelScope Research — Makefile
# =============================================================================
# One-command setup:  make install
# One-command run:    make run
# =============================================================================

.PHONY: help install run test clean docker-build docker-run

help:
	@echo "JewelScope Research — Makefile"
	@echo ""
	@echo "  make install     Create venv, install deps, install Playwright browsers"
	@echo "  make run         Launch the Streamlit app"
	@echo "  make test        Run unit tests"
	@echo "  make clean       Remove venv, caches, and generated files"
	@echo "  make docker-build  Build Docker image"
	@echo "  make docker-run    Run Docker container"
	@echo ""

VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip
BROWSERS = ./browsers

install: $(VENV)/bin/activate
	@echo "✓ All set — run 'make run' to start"

$(VENV)/bin/activate: requirements.txt
	@echo "Creating virtual environment..."
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip -q
	$(PIP) install -r requirements.txt -q
	@echo "Installing Playwright browsers..."
	PLAYWRIGHT_BROWSERS_PATH=$(BROWSERS) $(PYTHON) -m playwright install chromium
	@touch $(VENV)/bin/activate
	@echo "✓ Dependencies installed"

run: $(VENV)/bin/activate
	PLAYWRIGHT_BROWSERS_PATH=$(BROWSERS) $(PYTHON) -m streamlit run main.py

test: $(VENV)/bin/activate
	PLAYWRIGHT_BROWSERS_PATH=$(BROWSERS) $(PYTHON) -m pytest tests/ -v --tb=short 2>&1

clean:
	rm -rf $(VENV) $(BROWSERS) __pycache__ */__pycache__ .pytest_cache
	rm -f .coverage
	rm -rf databases/*.db databases/sessions/
	rm -f reports/*.html reports/*.pdf
	@echo "✓ Cleaned"

docker-build:
	docker build -t jewelscope-research .

docker-run:
	docker run -p 8501:8501 -v $(PWD)/databases:/app/databases -v $(PWD)/reports:/app/reports jewelscope-research

docker-run-bare:
	docker run -p 8501:8501 jewelscope-research
