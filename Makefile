.PHONY: test lint fmt install vmtest vendor

test:
	python3 -m pytest

lint:
	python3 -m ruff check .

fmt:
	python3 -m ruff check --fix .
	python3 -m ruff format .

vmtest:
	bash scripts/vmtest.sh

vendor:
	rsync -a --delete --exclude __pycache__ src/kutu_doctor/ ../os/packages/kutu-doctor/kutu_doctor/

install:
	pipx install -e .
