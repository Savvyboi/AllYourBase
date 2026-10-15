"""Cross-platform equivalent of make check."""

import subprocess

PREFIX = [
    "uv",
    "run",
    "--extra",
    "access",
    "--extra",
    "ingestion",
    "--extra",
    "review",
    "--extra",
    "monitor",
]
COMMANDS = [
    [*PREFIX, "ruff", "check", "."],
    [*PREFIX, "ruff", "format", "--check", "."],
    [*PREFIX, "mypy", "src", "tests"],
    [*PREFIX, "pytest"],
    [*PREFIX, "allyourbase", "config", "check"],
    [*PREFIX, "allyourbase", "catalogue", "check"],
    [*PREFIX, "allyourbase", "schemas", "check"],
]


def main() -> int:
    for command in COMMANDS:
        result = subprocess.run(command, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
