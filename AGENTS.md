# AllYourBase agent guide

Updated 2026-10-20 (Europe/Helsinki). Applies to this repository. Current user
instructions take precedence.

## Active scope

The owner removed Sentinel-1 and requested category grouping in the local tool
and category views online. Build the Sentinel-2-only monitor described in
[the current guide](docs/ground-change-mvp.md), [roadmap](docs/build-plan.md) and
[ADR 0005](docs/adr/0005-optical-only-categories.md). Earlier catalogue/Colab/Hugo
milestones and two-sensor validation are historical. Do not resume radar fetching
or catalogue research as prerequisites.

`sites.yaml` defines stable site IDs, coordinates, size 1000 m and an optional
category (default Uncategorized). Start with Chkalovsky at 55.8783, 38.061699,
category Airfields. The centre comes from retained OurAirports UUMU evidence;
the owner authorized any existing base on October 15. This is a processing square,
not a surveyed boundary. Categories/names are mutable display metadata; they must
not relocate the frozen grid or change detection IDs. Coordinate/size changes
require a new ID.

Freeze 100x100 cells at 10 m in a metric CRS, extent 500 m from the centre. Compare
every usable observation in seven complete UTC days against the preceding 28 days.
`--end-date` is exclusive UTC midnight. Use CDSE Catalog/Process numerical
Sentinel-2 L2A B02/B03/B04/B08, SCL and dataMask. Verify exact product identity,
CRS/bounds/transform/bands; preserve COG suffixes and categorical nearest sampling.
Keep SCL 4/5 with a cloud/shadow buffer. Require >=2 independent baseline
observations per pixel and >=70% common coverage. Alternative products from the
same pass cannot inflate counts. Prototype detection is mean absolute four-band
reflectance difference >0.10 and >=9 eight-connected cells. Optical thresholds
are not independently accepted. Missing/cloudy data is insufficient data.

Use one Python pipeline in `src/allyourbase/monitor/`. Radar is refused at active
fetch/comparison boundaries. Keep legacy provider/catalogue code and older reports
as historical evidence. The static builder must exclude radar news/assets and
project older combined checks to their optical status while preserving originals.

The local category UI (`monitor review`, port 8766) and CLI (`monitor sites`,
`monitor categorize`) edit categories in YAML. It is also linked from the existing
catalogue review UI. Preserve comments/coordinates; use atomic writes, locking,
revision checks and loopback/session/same-origin protection. The online viewer
groups sites, filters category plus check status, and applies categories to recent
optical reports. Current categories override display metadata on build. Manual
Actions Rebuild only publishes retained history/category edits without imagery.

Every detection is possible ground change. Do not infer cause, military activity,
deployments, intent, object counts or invented confidence. A 10 m grid does not
imply 10 m resolving power. No-change only describes valid observed coverage.

## Evidence and acceptance

PRs #1-#12 are merged; the sensor/category change is prepared separately for review.
The earlier manual publication and October 19 unattended two-sensor publication
succeeded (scheduled run `39261644688`, main `d76ba5e`). Durable history is on
`monitor-results`. The next configured weekly trigger is October 26 06:23 UTC;
start time can be delayed. The first optical-only/category publication and its
following unattended run remain unverified before merge/deployment.

296 tests and required checks pass. Optical cache replay is quiet with zero
network requests. Rebuilding real durable history yields one site check and no
optical detections; archived radar reports are preserved. Desktop/mobile category
QA covers saves/reload persistence, combined filters, empty states, category links,
images and no overflow/JS/HTTP errors. External evidence: `../monitor-optical-qa/`.
[Older live/provider/usage evidence](docs/ground-change-v0.1-history.md) and
[CEMS historical validation](docs/historical-validation.md) are retained. The latter
flagged radar pre-event controls and had insufficient optical coverage; it does
not calibrate current optical thresholds. Do not call the MVP calibrated/complete.

## Working rules

Preserve old evidence, approvals, records, raw workspaces and unrelated edits.
Keep code/config/docs/tests on main and only small JSON/PNG history on the results
branch. Keep raw rasters, payloads, credentials, environments, full usage journals
and QA outside Git/published output. Publish only the builder's allow-listed site.
Refuse unexpected output files/symlinks. Retain history on location failures.
Use explicit weekly/manual Actions with concurrency, permissions, retries and
safe measured/unknown usage aggregates. Never print credentials, raw responses
or signed URLs. Reuse `CDSE_CLIENT_ID`/`CDSE_CLIENT_SECRET` secure credentials;
do not request values. Tokens remain in memory. Process calls retry explicit 429
only; do not blindly repeat ambiguous charged failures. Bound every HTTP attempt.

Keep code changes reviewable through draft PRs to Savvyboi/AllYourBase; do not merge
PRs without authorization. Prepare deployment completely before approval. The
owner authorizes automatic possible-change Pages publication, replacing the
legacy human-reviewed publication policy. Do not add object recognition, a
coordinate-entry form, database or complex frontend. Increment ANALYSIS_VERSION
for output-affecting algorithm changes; this scope uses ground-change-0.2.0.

```sh
uv sync --locked --extra access --extra ingestion --extra review --extra monitor
uv run --extra access --extra ingestion --extra review --extra monitor python scripts/check.py
uv run --extra access --extra ingestion --extra review --extra monitor pre-commit run --all-files
```

Default Windows sandbox process startup can fail with `setup refresh had errors`;
bounded reviewed PowerShell commands work. A legacy review service holds the old
.venv CLI open; use external `UV_PROJECT_ENVIRONMENT=../monitor-env`. Do not stop
unrelated services. Resolve routine implementation choices autonomously. Reuse
cache for validation, retain measured/unknown costs, and never repeat paid Process
calls merely to verify documentation. Inspect diffs/staged paths before committing.
