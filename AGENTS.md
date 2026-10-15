# AllYourBase agent guide

Updated 2026-10-15 (Europe/Helsinki), after the owner replaced the project scope.
This file applies to the whole repository. Current user instructions take precedence.

## Active goal

Build the small coordinate-based Sentinel ground-change MVP specified in the
[owner's replacement plan](docs/ground-change-agent-plan.md). The current roadmap
and acceptance status are in [docs/build-plan.md](docs/build-plan.md). The earlier
catalogue/Colab/Hugo plan is preserved in [the legacy roadmap](docs/legacy-build-plan.md)
and [legacy guide](docs/legacy-agent-guide.md); its milestones no longer gate this MVP.
Do not resume catalogue research or ask for old packet approval as a prerequisite.

The MVP uses `sites.yaml`, one location initially, a fixed 1 km metric square and
100 Ã— 100 cells at 10 m spacing. It compares every usable acquisition in the latest
seven complete UTC days with the preceding 28 days. `--end-date` is an exclusive
UTC date for historical runs. Start location: Chkalovsky, using the retained
OurAirports UUMU centre. The owner authorized using any existing approved base
on 2026-10-15. This square is a processing window, not a surveyed facility boundary.

Use CDSE Sentinel Hub Catalog and Process APIs, OAuth credentials, numerical TIFFs,
one acquisition at a time and exact grid/scene verification. Optical uses B02,
B03, B04, B08, SCL and dataMask. Radar uses IW VV/VH, terrain gamma-zero,
orthorectification, Copernicus 30 m DEM, LEE 3Ã—3 and data/shadow masks. A 10 m
grid does not imply 10 m resolving power. Preserve product identity, including
COG suffixes. Unknown relative orbit means no radar comparison.

Keep prototype thresholds in `config/monitor.yaml`: optical mean absolute band
reflectance difference >0.10, radar absolute VV or VH difference >3 dB, at least
nine eight-connected cells, at least two independent earlier baseline observations
per evaluated pixel, and at least 70% valid common AOI coverage. Optical keeps only
SCL 4/5 with a cloud/shadow buffer; categorical data uses nearest neighbour.
Radar baseline medians are linear before dB conversion, grouped by relative
orbit, direction, mode and polarisation. Alternative tile/reprocessed products
from one pass must not inflate observation counts. Baselines exclude the target week.

Every detection is **possible ground change**. Do not infer cause, military
activity, unit/equipment deployments, intent, people/vehicle counts or confidence
percentages. Keep sensor areas separate. A quiet result describes only valid
observed coverage; missing data is `insufficient_data`, and failures are `error`.

## Implementation and evidence

- PRs #1â€“#8 are merged. PR #8 merged at `9e0269b`; all previous source snapshots,
  approval archives and provider evidence remain intact and are historical records.
- Active implementation is under `src/allyourbase/monitor/`: configuration/grid,
  fetch, prepare, detect, report and CLI modules. `allyourbase monitor run` supports
  `--plan`, `--demo` or explicit `--live`; `monitor build` rebuilds retained history.
  Legacy catalogue/access commands and their checks remain available.
- Local historical Chkalovsky check: target 2026-10-05 through 2026-10-11 UTC,
  exclusive end 2026-10-12; baseline 2026-09-07 through 2026-10-04. Both sensors
  supplied usable observations. One radar candidate was generated; one optical
  comparison was quiet at 99.76% common coverage, three were insufficient.
  These are prototype outputs, not independently verified real-world events.
- The corrected uncached run used 47 HTTP requests and reported 7.1607681139640045
  total PU across catalogue/Process responses. A later run after product
  deduplication used three catalogue/auth requests, zero Process calls, reported
  0.04 PU and retained one detection. Earlier scene-selection diagnostics are
  preserved; charges for the first rejected batch were not retained and remain
  unknown. Do not present these figures as account-wide usage.
- External workspaces: `../monitor-data` for cache/usage/QA, `../monitor-results`
  for small JSON/PNG history, `../monitor-site` for generated static output.
  Earlier `../phase1-data` and `../phase2-data` are preserved. All are outside Git.
- 294 tests, Ruff, formatting, strict mypy and all legacy settings/catalogue/schema
  checks pass. Headless Edge checks of desktop and 375 px mobile verify images,
  filter buttons, detail links, provenance, no overflow and no JS/HTTP errors.
  A flagged radar comparison and quiet optical comparison were visually inspected.
- The requested known-change fixture passes; real historical cause/ground truth
  and threshold calibration remain unverified. Do not mark thresholds accepted.
- Weekly/manual Actions workflow is implemented in `.github/workflows/monitor.yml`:
  persistent `monitor-results` branch, single-run concurrency, explicit permissions,
  official Pages artifact/deployment actions and bounded deployment retries.
  Repository Actions secrets and workflow-based Pages are configured.
  Manual Pages publication and the following unattended scheduled run still need
  live verification. Do not mark the MVP complete until those acceptance checks pass.

## Working rules

Preserve old evidence, approval records, source decisions and unrelated edits.
The legacy ten-site catalogue gate, dated unit/equipment requirements, Colab runtime,
Hugo frontend and human-reviewed publication policy are superseded for this MVP.
The owner now requests automatic possible-change publication through Actions/Pages.
Keep code changes reviewable through draft PRs to Savvyboi/AllYourBase; do not merge
PRs without authorization. Prepare deployment completely before any approval step.

Keep raw rasters, source payloads, credentials, local environments, diagnostics and
full usage logs outside Git and published output. Only small report JSON/PNG history
belongs on the dedicated results branch. Main holds code/config/docs/tests.
Publish only the static builder's allow-listed output; never upload the workspace.
Use environment variable names `CDSE_CLIENT_ID` and `CDSE_CLIENT_SECRET`, stored as
Actions secrets. Reuse existing secure credentials; never request or print values.
Tokens remain in memory. Increment `monitor.ANALYSIS_VERSION` for output-affecting
algorithm changes, and preserve reports from earlier versions. Do not include raw response bodies or signed URLs in logs.

Transport retries catalogue/transient reads with backoff and counts every attempt
against the configured cap. Process calls retry explicit 429 rejections only;
ambiguous charged failures are not blindly repeated. Retain measured and unknown
costs separately. Inspect source IDs and grid metadata before using cutouts.

Do not add object recognition, a coordinate-entry form, a database, a complex
frontend or country-specific algorithm code. Resolve routine implementation choices
autonomously. Keep the roadmap and ADRs current when behavior or scope changes.

## Development and verification

```sh
uv sync --locked --extra access --extra ingestion --extra review --extra monitor
uv run --extra access --extra ingestion --extra review --extra monitor python scripts/check.py
uv run --extra access --extra ingestion --extra review --extra monitor pre-commit run --all-files
```

On this Windows host, default sandbox process startup may fail with
`setup refresh had errors`; bounded reviewed PowerShell commands work. The legacy
review service holds `.venv/Scripts/allyourbase.exe` open, so the current MVP checks
use `UV_PROJECT_ENVIRONMENT` pointing at the external sibling `../monitor-env`.
Do not stop unrelated services or mistake infrastructure errors for missing secrets.

For source edits, run appropriate offline tests and required checks. Use numerical
fixtures and mocked non-secret API responses. Live imagery checks must serve actual
MVP validation, remain bounded and retain costs. Do not repeat paid Process calls
just to verify documentation; reuse verified cache and earlier reports.
Before committing, inspect the diff and staged paths for credentials, imagery and
workspace files. Keep remaining validation gaps explicit.
