"""Cross-platform equivalent of make check."""

import subprocess

COMMANDS = [
    ["uv", "run", "ruff", "check", "."],
    ["uv", "run", "ruff", "format", "--check", "."],
    ["uv", "run", "mypy", "src", "tests"],
    ["uv", "run", "--extra", "access", "pytest"],
    ["uv", "run", "allyourbase", "config", "check"],
    ["uv", "run", "allyourbase", "catalogue", "check"],
    ["uv", "run", "allyourbase", "schemas", "check"],
]


def main() -> int:
    for command in COMMANDS:
        result = subprocess.run(command, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
