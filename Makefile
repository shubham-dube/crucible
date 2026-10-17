.PHONY: install lint fmt type test test-e2e test-all check

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff format .
	uv run ruff check --fix .

type:
	uv run mypy

test:
	uv run pytest -m "not live and not e2e"

test-e2e:
	uv run pytest -m e2e

test-all:
	uv run pytest

check: lint type test
