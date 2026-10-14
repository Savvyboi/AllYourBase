.PHONY: check format schemas
check:
	uv run python scripts/check.py

format:
	uv run ruff check --fix .
	uv run ruff format .

schemas:
	uv run allyourbase schemas generate

