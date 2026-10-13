# Phase 0 verification

Verified on 2026-10-13 in Linux with Python 3.12.14 and the committed uv lockfile.

| Check | Result |
| --- | --- |
| `uv sync --locked` | Pass |
| `make check` | Pass |
| Ruff lint and format | Pass |
| Strict mypy | Pass across 31 source and test files |
| pytest and Hypothesis | 71 tests pass |
| Settings validation | Pass |
| Production catalogue validation | Pass; empty catalogue warning is expected |
| JSON Schema consistency | Six schemas match their models |
| `uv run pre-commit run --all-files` | All five hooks pass |

The checker, schemas and CLI planning paths were exercised offline using
synthetic fixtures. The source archive excludes virtual environments, caches,
Git metadata, credentials, databases and imagery.

Windows-specific runtime execution, live provider requests, processing-unit
measurement, geospatial preprocessing, scoring, Hugo/browser rendering and
GitHub publication have not been tested because they are outside Phase 0.
