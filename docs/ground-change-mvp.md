# Sentinel-2 monitor and site categories

Updated 2026-10-20. The owner requested Sentinel-2 only and category grouping;
[ADR 0005](adr/0005-optical-only-categories.md) records the change. Earlier
[two-sensor execution evidence](ground-change-v0.1-history.md) and
[historical validation](historical-validation.md) remain archived.

## Active pipeline

`sites.yaml` defines stable IDs, coordinates, `size_m: 1000` and an optional
`category`. Chkalovsky remains the first location, using the retained OurAirports
UUMU centre at 55.8783, 38.061699. Its category is `Airfields`. Missing/blank
categories normalize to `Uncategorized`; labels may contain Unicode and are
limited to 80 characters. They are display groups, not claims about current use.

Freeze a 100x100 grid at 10 m in the centre's metric CRS, with 500 m extent in
each direction. Changing coordinates/size needs a new ID. Names/categories can
change without relocating the grid or creating new detection IDs.

Use CDSE Sentinel Hub Catalog/Process numerical Sentinel-2 L2A cutouts only:
B02/B03/B04/B08 reflectance, SCL and dataMask. Verify the exact returned scene,
grid, transform and numerical/categorical bands. Radar requests are refused
before authentication or network access. Legacy radar provider code is retained
outside the active monitor package.

Use seven complete UTC target days and the preceding 28-day baseline, with an
exclusive `--end-date`. Keep SCL 4/5 and valid data, with a one-cell cloud/shadow
buffer. Categorical masks use nearest-neighbour sampling; SCL is native 20 m.
Require two independent earlier observations per pixel and 70% common coverage.
Compare the pixelwise median baseline with each usable target using mean absolute
four-band reflectance difference >0.10; keep eight-connected patches of at least
nine cells. Alternative products from one pass cannot inflate observation counts.
These are unvalidated prototype thresholds. Cloud/snow/water and missing coverage
produce insufficient data rather than a quiet result.

## Local category management

```sh
uv sync --locked --extra monitor --extra review
uv run --extra monitor --extra review allyourbase monitor review
```

Open `http://127.0.0.1:8766/`, select sites, enter an existing/new category, and
apply it. The editor displays grouped sites and a category selector. It updates
only category values in `sites.yaml`, preserving comments and coordinate fields.
A file lock, expected revision and atomic replacement protect against overwritten
edits. Reload after a stale-write message. The existing catalogue review page
also links to this tool at `/monitor`.

CLI equivalents:

```sh
uv run --extra monitor allyourbase monitor sites
uv run --extra monitor allyourbase monitor sites --category Airfields
uv run --extra monitor allyourbase monitor categorize chkalovsky --category Airfields
```

All commands accept `--sites` for a different YAML file. Local edits become
public after committing/pushing the YAML and running the publishing workflow.

## Viewer and history migration

The homepage groups latest location checks by category. Category selection applies
to checks and recent detections; status buttons further filter the checks. Empty
states are explicit. The selected category/status is retained in the URL. Site
pages link back to the selected category. Current category/name metadata is used
when building older reports without changing archived acquisition/grid evidence.

Only optical reports enter `reports.json`, site pages and news cards. Older
combined checks are projected to optical comparisons/errors/detections, so an old
radar flag cannot keep a possible-change status. Known obsolete generated radar
preview files are removed only from the validated output directory. Radar JSONs
and original previews stay in the results archive; raw rasters stay outside Git.
Unexpected output files and symlinks are still refused.

```sh
uv run --extra monitor allyourbase monitor build ../monitor-results ../monitor-site
```

A manual Actions run with **Rebuild only** publishes current categories and the
retained optical history without fetching imagery or requiring CDSE credentials.
Weekly runs continue normal optical analysis, history persistence and Pages
publication, with explicit permissions, concurrency and bounded deployment retries.

## Verification and acceptance

The earlier unattended workflow succeeded on [2026-10-19](https://github.com/Savvyboi/AllYourBase/actions/runs/39261644688)
at code `d76ba5e23410d6c10862d829ba3747d60035b465`. It restored and retained history,
ran analysis and deployed Pages. It still used the older two-sensor version.

The new implementation passes 296 tests and required lint/type/catalogue/schema
checks. Category coverage includes YAML/comment preservation, Unicode, default
labels, stale writes, local API protection, CLI edits, category changes without
reanalysis, HTML escaping and archived-radar migration. A verified cached optical
historical check is quiet with zero network/Process requests. Rebuilding the
current durable history produces one optical site check and zero optical news
items; radar archive files remain unchanged.

Desktop/mobile browser QA checks local saves/reload persistence, grouping,
combined filters, empty states, category links, previews and no overflow or
JS/HTTP errors. Evidence stays outside Git in `../monitor-optical-qa/`.

First publication of this new scope and its following unattended optical-only
run remain to be verified after merge. The next configured weekly trigger is
2026-10-26 06:23 UTC; actual Actions start time may be delayed. Independent optical
threshold validation remains open. Do not call the MVP calibrated or complete.
