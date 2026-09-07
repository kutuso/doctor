.PHONY: test lint fmt install vmtest

test:
	python3 -m pytest

lint:
	python3 -m ruff check .

fmt:
	python3 -m ruff check --fix .
	python3 -m ruff format .

vmtest:
	bash scripts/vmtest.sh

install:
	pipx install -e .
