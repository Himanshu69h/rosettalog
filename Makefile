PYTHON ?= python
WHEELS_DIR := wheels

.PHONY: vendor test lint typecheck ci airgap-test

vendor:
	mkdir -p $(WHEELS_DIR)
	$(PYTHON) -m pip download --dest $(WHEELS_DIR) -r requirements.txt

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy src

ci: lint typecheck test

airgap-test:
	docker build --network none -t rosettalog:gate0 .
