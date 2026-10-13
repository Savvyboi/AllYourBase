# Phase 0 foundation

The first milestone is a runnable, offline foundation. It validates inputs before
any imagery is fetched and preserves the build plan's local analysis and separate
publication architecture.

## Acceptance criteria

| Requirement | Implementation |
| --- | --- |
| Repository layout | Catalogue, config, schemas, Python packages, fixtures, tests, site, notebooks and ADRs |
| Python 3.12 with uv | `pyproject.toml`, `.python-version` and committed `uv.lock` |
| Ruff, mypy and pytest | `make check` and a cross-platform `scripts/check.py` |
| Pre-commit | Local hooks using the locked project environment |
| Pydantic for every catalogue file | Sites/zones, units/links, equipment, sources and taxonomy models |
| Pydantic settings | Nested runtime, provider, preprocessing, indicator, scoring and publish contracts |
| Required CLI commands | `run`, `review`, `publish`, `backfill`, `catalogue` listed by `--help` |

The owner selected `Savvyboi/AllYourBase` as the code repository. This milestone
is prepared on `codex/phase-0-foundation` for a Phase 0 pull request into `main`.
Repository access has been verified. Live data access must not be confused with
this milestone's offline validation.

## Validation coverage

The suite checks source references, dated claims, taxonomy and unit-parent cycles,
duplicate catalogue records, unknown tags, GeoJSON validity, contained zones and
masks, antimeridian geometries, Unicode names, UTC ISO-year boundaries, week 53,
schema drift, safe YAML parsing, redacted errors, and workspace separation.
Hypothesis checks ISO-week round trips over dates spanning two centuries.

The committed fixture country `XXX` and every record inside it are synthetic.
They are never loaded from the production catalogue by default. They test file
formats and validation, not the detection algorithm's accuracy.

## Commands and limits

Planning commands validate the catalogue and print explicit site/week UTC windows.
They do not query APIs or look at a results database. A run plan defaults to the
last fully completed UTC week; catch-up and late-arrival processing will be added
with the persistent run ledger. Backfill plans take an inclusive range of week
labels, while each week's acquisition interval is half-open.

Actual processing, backfill, review and publication exit with code 2 and a clear
implementation-status message. Invalid settings/catalogues exit with code 1.
Valid checks and planning exit with code 0.

Generated JSON Schemas cover structural validation. The Python checker additionally
enforces spatial and cross-file integrity, which JSON Schema cannot express.

## Provisional configuration

The supplied plan provides initial thresholds and API/provider candidates. These
are configuration inputs, not measured performance or verified live availability.
MAD floors were not specified numerically in the plan; the YAML marks them as
provisional. They must be calibrated before any scored output is published.
The snow-track NDSI cutoff and hotspot rule still need explicit definitions.

The publish allow-list includes CSV for the promised time-series downloads, XML
for the Atom feed and text for static search/robots assets. The eventual publisher
must separately handle `.nojekyll` and verify every file before pushing.

This release creates neither a data workspace nor a public website.
