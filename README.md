# AllYourBase

AllYourBase is a local, review-first GEOINT tool for weekly aggregate change
monitoring with Sentinel-1 and Sentinel-2. This release implements **Phase 0** of
the supplied build plan: the Python foundation and catalogue validation.
Imagery retrieval, indicators, scoring, review UI and the Hugo website are future
milestones. No military site facts or coordinates are seeded from memory.

Code repository: [Savvyboi/AllYourBase](https://github.com/Savvyboi/AllYourBase).
Each build-plan phase is proposed through a separate pull request.

## Start

Install Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).
From this directory:

```sh
uv sync --locked
uv run allyourbase --help
uv run allyourbase config check
uv run allyourbase catalogue check
make check
```

On Windows without Make, use `uv run python scripts/check.py`. The `basewatch`
command is an alias for `allyourbase`, preserving the build plan's examples.
You can also run `uv run python -m allyourbase`.

When starting from the source ZIP, initialize Git before installing hooks:

```sh
git init -b main
uv run pre-commit install
```

Git metadata and the virtual environment are omitted from the source archive.

## What works now

- Strict Pydantic contracts for settings, sites/zones, units and dated links,
  equipment, sources with reuse classes, and taxonomy terms.
- Offline catalogue checking: citations, stable site IDs, country placement,
  term membership, missing references, parent cycles, polygon validity,
  zone/mask containment and duplicate records.
- Generated JSON Schemas with drift checking.
- UTC ISO-week parsing and planning, including year boundaries and week 53.
- `run --plan` and `backfill --plan` print a work plan without accessing a provider,
  creating a database or marking any week complete.
- Ruff, strict mypy, pytest/Hypothesis and pre-commit configuration.

The catalogue is intentionally empty. Synthetic examples live only in `fixtures/`
and are labelled fictional. Add reviewed, cited records under
`catalogue/countries/<ISO3>/` before planning work.

## Commands

```sh
uv run allyourbase config check
uv run allyourbase catalogue check
uv run allyourbase catalogue check --json
uv run allyourbase schemas check
uv run allyourbase schemas generate
uv run allyourbase run --site xxx-example-site --week 2026-W41 --plan
uv run allyourbase backfill --from 2024-W01 --to 2024-W04 --plan
uv run allyourbase status
```

Global `--root PATH` selects another project directory. A settings path can be
selected with `--settings PATH` (relative to that root or absolute).
`run`, `backfill`, `review` and `publish` refuse actual execution until their
implementation milestones. Their help screens describe that limitation.

## Configuration and workspace

`config/settings.yaml` holds all thresholds, provider definitions, budgets and
publishing settings. Values from the plan are provisional; provider coverage,
quota and request costs still need Phase 1 measurements. No live source or quota
was verified in this release.

`ALLYOURBASE_HOME` overrides the configured workspace; legacy `BASEWATCH_HOME`
is also supported. When both are set, `ALLYOURBASE_HOME` wins. The default is
`~/allyourbase-data`, outside this repository. Relative workspace paths are
resolved against the project root, and paths inside the code repository are
rejected. Phase 0 only resolves paths; it never creates the workspace.

Only environment variable **names**, never credential values, belong in YAML.
CDSE credential provisioning will be added in Phase 1. Do not paste secrets
into the catalogue or commit `.env` files. Large imagery, database and cache
files are ignored. The public website will be built into a separate repository.

Publishing defaults to `reviewed_only`. `delay_days: 0` is provisional and is
not a decision to publish anything; the publish command is inactive. Publication
delay, site exclusions and GitHub account/repository selection remain owner
decisions before Phase 7.

## Structure and next steps

See `docs/phase-0.md` for completed acceptance criteria, `docs/phase-1.md` for
the next spike, and `docs/adr/0001-phase-0-foundation.md` for design decisions.
The `site/` folder is reserved for Hugo and is not a deployed website.

The code follows [Pydantic's model contracts](https://docs.pydantic.dev/latest/concepts/models/)
and [uv's lock and sync workflow](https://docs.astral.sh/uv/concepts/projects/sync/).
The lockfile fixes the resolved dependency versions for this milestone.
