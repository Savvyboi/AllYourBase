.PHONY: check format schemas
check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src tests
	uv run pytest
	uv run allyourbase config check
	uv run allyourbase catalogue check
	uv run allyourbase schemas check

format:
	uv run ruff check --fix .
	uv run ruff format .

schemas:
	uv run allyourbase schemas generate

