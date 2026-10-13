# AllYourBase

AllYourBase is a local, review-first GEOINT tool for weekly aggregate change
monitoring with Sentinel-1 and Sentinel-2. Phase 0 is complete. This version adds
the **Phase 1 provider-access spike**: discovery, optical window reads, radar
requests and local usage reports. Eight-week discovery, optical/radar reads and
measured radar costs now pass for three owner-approved Russian airbase test areas.
CDSE optical fallback reads still need separate S3 credentials. Indicators,
scoring, review UI and the Hugo website remain future milestones.

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
- `providers doctor` checks readiness; `--online` checks collection access.
- `providers spike` writes acquisition, window-read, failure and usage reports
  to the external local workspace. Pixel reads are explicit options.

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
uv run allyourbase providers doctor --online
uv run allyourbase providers spike --aoi-file docs/proposals/phase-1-aois.geojson --plan
```

Global `--root PATH` selects another project directory. A settings path can be
selected with `--settings PATH` (relative to that root or absolute).
`run`, `backfill`, `review` and `publish` refuse actual execution until their
implementation milestones. Their help screens describe that limitation.

## Configuration and workspace

`config/settings.yaml` holds all thresholds, provider definitions, budgets and
publishing settings. Primary-provider access and radar request costs have been
measured for the Russian pilot; see `docs/phase-1-live-validation.md`. Numerical
analysis thresholds, account quota assumptions and fallback pixel access remain
provisional. These measurements do not establish global coverage.

`ALLYOURBASE_HOME` overrides the configured workspace; legacy `BASEWATCH_HOME`
is also supported. When both are set, `ALLYOURBASE_HOME` wins. The default is
`~/allyourbase-data`, outside this repository. Relative workspace paths are
resolved against the project root, and paths inside the code repository are
rejected. Checks and planning create no state. An actual access spike writes
its reports, chips and budget ledger under this external workspace.

Only environment variable **names**, never credential values, belong in YAML.
CDSE OAuth credentials can come from the environment or OS keychain. CDSE S3
pixel access uses separate environment keys. See `docs/phase-1.md` for local
setup; `.env` is ignored but not loaded automatically. The public website will
use a separate repository.

Publishing defaults to `reviewed_only`. `delay_days: 0` is provisional and is
not a decision to publish anything; the publish command is inactive. Publication
delay, site exclusions and GitHub account/repository selection remain owner
decisions before Phase 7.

## Structure and next steps

See `docs/phase-0.md` for completed acceptance criteria, `docs/phase-1.md` for
the access spike and remaining acceptance work, and `docs/adr/` for design decisions.
The `site/` folder is reserved for Hugo and is not a deployed website.

The code follows [Pydantic's model contracts](https://docs.pydantic.dev/latest/concepts/models/)
and [uv's lock and sync workflow](https://docs.astral.sh/uv/concepts/projects/sync/).
The lockfile fixes the resolved dependency versions for this milestone.
