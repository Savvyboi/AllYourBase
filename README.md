# AllYourBase

AllYourBase is a review-first Sentinel-1/Sentinel-2 tool with Google Colab
processing and a human-curated catalogue. Phases 0 and 1 are merged. Version 0.3
adds **Phase 2 source ingestion and catalogue review**: immutable snapshots,
DuckDB staging, candidate matching and a local review queue with source citations
and zone previews. See [the Phase 2 workflow](docs/phase-2.md) and the
[first mixed-pilot geometry packet](docs/phase-2-mixed-pilot.md).

Primary optical, CDSE optical fallback and radar access pass for three approved
Russian access-test areas; see the [validated Colab notebook](notebooks/README.md).
The production catalogue still needs reviewed sites, geometry and sourced dated
unit/equipment claims. Indicators, scoring, event review and the Hugo website
remain future milestones.

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
- `providers doctor` checks metadata and S3 pixel-credential readiness separately;
  `--online` checks collection access.
- `providers spike` writes acquisition, window-read, failure and usage reports
  to the external local workspace. Pixel reads are explicit options.
- `sources snapshot/fetch/stage/match` preserves source permissions and exact evidence,
  stages candidate facts and retains rejected proposals across repeat imports.
- `catalogue review` opens the loopback review app; `queue/show/accept/reject/recover`
  provide CLI review with validated bundles and provenance-preserving writes.
  Supporting source proposals can be attached to one bundle; `catalogue readiness`
  checks milestone evidence separately from structural catalogue validity.
- `providers validate-optical` verifies existing optical band files and provenance
  without making network requests.

The catalogue is intentionally empty. Synthetic examples live only in `fixtures/`
and are labelled fictional. Add reviewed, cited records under
`catalogue/countries/<ISO3>/` before planning work.

## Commands

```sh
uv run allyourbase config check
uv run allyourbase catalogue check
uv run allyourbase catalogue check --json
uv run --extra ingestion allyourbase catalogue readiness --country RUS --require-type airbase --require-type naval_base --require-type garrison
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
`run`, `backfill` and `publish` refuse actual execution until their
implementation milestones. Their help screens describe that limitation.

## Configuration and workspace

`config/settings.yaml` holds all thresholds, provider definitions, budgets and
publishing settings. Primary-provider access and radar request costs have been
measured for the Russian pilot; see `docs/phase-1-live-validation.md`. Numerical
analysis thresholds and account quota assumptions remain provisional. CDSE
optical fallback is verified for the three approved pilot areas. These measurements do not establish global coverage.

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

See the [active build plan](docs/build-plan.md), [Word plan snapshot](docs/build-plan.docx)
and [AGENTS.md](AGENTS.md) for completed work, remaining acceptance checks and the
phase-by-phase roadmap. [Phase 0](docs/phase-0.md), [Phase 1](docs/phase-1.md) and
[ADRs](docs/adr/) contain the milestone evidence and design decisions.
The `site/` folder is reserved for Hugo and is not a deployed website.

The code follows [Pydantic's model contracts](https://docs.pydantic.dev/latest/concepts/models/)
and [uv's lock and sync workflow](https://docs.astral.sh/uv/concepts/projects/sync/).
The lockfile fixes the resolved dependency versions for this milestone.
