# AllYourBase — Sentinel ground-change monitor

A small coordinate-based Sentinel-1/2 MVP. Check a fixed **1 km × 1 km** square
against its earlier imagery and report **possible ground change**. Analysis runs
in Python; weekly GitHub Actions retain report history and deploy a plain static
site through GitHub Pages.

The [2026-10-15 replacement plan](docs/ground-change-agent-plan.md) defines the
active scope. See [current acceptance status](docs/build-plan.md) and
[execution/validation details](docs/ground-change-mvp.md). Earlier catalogue,
Colab and provider work is preserved; it no longer gates this MVP.

## Run locally

Install Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/),
then from this repository:

```sh
uv sync --locked --extra monitor
uv run --extra monitor allyourbase monitor run --plan --end-date 2026-10-12
uv run --extra monitor allyourbase monitor run --demo
uv run --extra monitor allyourbase monitor run --live --end-date 2026-10-12
```

Choose exactly one mode. `--plan` makes no requests or writes. `--demo` uses
labelled synthetic changed/quiet examples and makes no requests. `--live` uses
CDSE OAuth credentials named `CDSE_CLIENT_ID` and `CDSE_CLIENT_SECRET` in the
environment or the existing secure keychain. Never put their values in YAML,
source control, command arguments or chat.

`--end-date` is exclusive midnight UTC. Omitting it ends at today's UTC midnight:
the target is the seven complete days before it, and the baseline is the preceding
28 days. Default external paths are `../monitor-data` (cache/usage),
`../monitor-results` (JSON/PNG history), and `../monitor-site` (static output).
Use `--workspace`, `--history` and `--output` to choose separate external directories.

On this Windows workstation, the retained legacy review service may hold the old
CLI executable open. Use PowerShell `$env:UV_PROJECT_ENVIRONMENT = '../monitor-env'`
to select the isolated MVP environment without stopping that service.

Build the full site again without imagery requests:

```sh
uv run --extra monitor allyourbase monitor build ../monitor-results ../monitor-site
```

## Add coordinates

Edit `sites.yaml`:

```yaml
sites:
  - id: my-location
    name: My location
    latitude: 60.0
    longitude: 25.0
    size_m: 1000
```

The first configured location is Chkalovsky, chosen from the retained approved
pilot at the owner's request. Each location has a frozen metric CRS/extent and
100×100 grid at 10 m spacing. A coordinate/size change needs a new stable ID;
changing a display name does not relocate a site's history. Coordinates are
latitude/longitude in YAML; API transformations explicitly use longitude/latitude.

## GitHub Actions and Pages

The confirmed repository is [Savvyboi/AllYourBase](https://github.com/Savvyboi/AllYourBase).
CDSE OAuth credentials have been stored as encrypted repository Actions secrets,
and Pages uses **GitHub Actions** as its build source. The MVP and workflow fix
are merged in PRs #9 and #10. The [first manual publication](https://github.com/Savvyboi/AllYourBase/actions/runs/38756679440)
succeeded on 2026-10-15 for exclusive end date 2026-10-12.

For a manual run, open **Actions → Weekly ground-change monitor → Run workflow**.
Leave `end_date` empty for the latest complete days, or enter an exclusive UTC date
for a historical run. The workflow will:

1. Restore the dedicated `monitor-results` branch (or initialize it on first run).
2. Run the bounded numerical pipeline and retain small report JSON/PNG files.
3. Commit/push the results without force, build the complete static site, and
   deploy through the official GitHub Pages actions with bounded retries.

The schedule is Monday at **06:23 UTC**. Concurrency prevents overlapping workflow
writers. Cache is optional acceleration; persistent report history is restored
from Git on fresh runners. Raw rasters and credentials never enter the results
branch or Pages artifact. A location failure preserves earlier detections, records
an error, and allows other locations to continue.

The live report is [savvyboi.github.io/AllYourBase](https://savvyboi.github.io/AllYourBase/).
Its eight-file Pages artifact and six-file results branch contain only the expected
site assets and small JSON/PNG records. Desktop/mobile browser checks pass. The
next unattended run is scheduled for **2026-10-19 at 06:23 UTC**; its success and
independent historical threshold validation remain open acceptance checks.

## What results mean

The homepage shows recent possible changes and each location's latest status:
`possible_change`, `no_change_detected`, `insufficient_data` or `error`. Quiet and
failed-data runs create no news item. The report includes acquisition/baseline
dates, usable sensors, valid common coverage, separate sensor areas, highlighted
patches, before/current previews, source scene IDs, analysis version, thresholds
and Copernicus attribution. Baseline previews are labelled median composites.

Thresholds in `config/monitor.yaml` are prototypes: optical mean absolute difference
>0.10, radar VV or VH difference >3 dB, patches of at least nine connected cells.
Comparisons need at least two independent baseline observations per pixel and
70% valid common coverage. Radar requires matching relative orbit, direction,
IW mode and VV/VH; missing geometry is skipped. Optical conservatively keeps land
SCL 4/5 and buffers cloud/shadow masks. The 20 m SCL is nearest-neighbour sampled
onto the 10 m grid.

Weather, moisture, vegetation, snow and misalignment can produce changes. These
reports do not establish cause, activity, deployments, object counts or a confidence
percentage. A 10 m output grid does not guarantee 10 m resolving power. Independent
historical ground truth and threshold acceptance remain open.

## Verify

```sh
uv sync --locked --extra access --extra ingestion --extra review --extra monitor
uv run --extra access --extra ingestion --extra review --extra monitor python scripts/check.py
uv run --extra access --extra ingestion --extra review --extra monitor pre-commit run --all-files
```

Current validation: 294 tests, required lint/type/schema/catalogue checks, live
historical cutouts, repeat cache/history checks, desktop and 375 px browser QA.
Legacy catalogue/access commands are retained; their roadmap is archived under
[the superseded plan](docs/legacy-build-plan.md).
