.PHONY: install seed serve test eval reset clean all help

PYTHON ?= python3

help:
	@echo "Kivi word memory -- available targets:"
	@echo "  make install    verify python version"
	@echo "  make seed       migrate + load canonical demo seeds (hermetic)"
	@echo "  make serve      start the demo server on http://127.0.0.1:8000"
	@echo "  make test       run the full test suite (unittest, stdlib only)"
	@echo "  make eval       run the reproducible evaluation"
	@echo "  make reset      wipe the demo DB and re-seed"
	@echo "  make clean      remove __pycache__ and the demo DB"

install:
	@$(PYTHON) -c "import sys; assert sys.version_info >= (3,10), 'need python 3.10+'; \
	print(f'python {sys.version.split()[0]} OK -- zero runtime deps, ready to go')"

seed:
	$(PYTHON) -m app.seed --reset

serve:
	$(PYTHON) app/server.py

test:
	$(PYTHON) -m unittest discover -s tests -v

eval:
	$(PYTHON) -m evals.run_eval

reset:
	rm -f db/kivi.db*
	$(PYTHON) -m app.seed --reset

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -f db/kivi.db*
	@echo "cleaned"

all: install seed test eval
