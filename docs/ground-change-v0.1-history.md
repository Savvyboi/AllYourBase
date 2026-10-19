> Historical v0.1 implementation and validation. The owner switched the active monitor to Sentinel-2 only on 2026-10-20; see [the current guide](ground-change-mvp.md).

# Ground-change MVP execution and validation

Updated 2026-10-15 (Europe/Helsinki). The [owner's replacement plan](ground-change-agent-plan.md)
and [active roadmap](build-plan.md) supersede the older catalogue-first sequence.
[ADR 0004](adr/0004-ground-change-mvp.md) records the scope change.

## Inputs and runtime

`sites.yaml` starts with Chkalovsky at latitude 55.8783, longitude 38.061699,
size 1000 m. The centre is the retained OurAirports UUMU record (ID 34969), from
revision `132fc8c3471c96cfffe3ece8a89f9f252f670243` and CSV SHA-256
`61c82a74de991e138dc57e1fbc72b6f47da30db9954be4e414452e896f7d40d8`.
The owner selected any existing approved base for this MVP on 2026-10-15. This
1 km processing square does not assert the facility boundary or current use.

The centre is projected using `always_xy=True` into local UTM (UPS at polar
latitudes); Chkalovsky uses EPSG:32637. The extent is exactly 500 m around the
projected centre, 100×100 pixels at 10 m. Grid metadata is retained by stable
location ID in the report history, so fresh runners reuse the same contract.
A relocated ID is refused and reported as an error while other locations continue.

`config/monitor.yaml` contains prototype thresholds, mask/coverage requirements,
preview stretches, request/retry bounds, provider URLs and credential variable
names. There is one active Python pipeline under `src/allyourbase/monitor/`.
Existing token, HTTP, STAC and geographic discovery components are reused. The
legacy catalogue, source staging and Colab evidence remain intact.

## Numerical behavior and provenance

The target is `[end-7 days, end)` and the baseline `[end-35 days, end-7 days)`.
The end is exclusive UTC midnight, explicitly selectable for historical runs.
Each usable target acquisition is compared with its strictly earlier baseline.
Alternative tile/reprocessed products from one pass do not count as independent
observations; a conservative same-platform separation also prevents granule-time
differences from inflating counts. Radar additionally requires a matching relative
orbit, direction, IW mode and VV/VH group; unverified metadata is skipped.

Process requests use the frozen CRS/bounds/100×100 extent, numerical FLOAT32 TIFF
bands and returned product-ID metadata. More than one sample produces no valid
pixels; unexpected returned products are rejected. Only a terminal `.SAFE` suffix
is normalized; COG identity is preserved. The first live attempt exposed an
incompatible product filter in an earlier evalscript stage. It was removed, and
returned-scene verification remains mandatory. One bounded acquisition per sensor
proved the corrected request before the batch rerun.

Optical masks require finite reflectance, dataMask and SCL 4/5, with a one-cell
cloud/shadow buffer; categorical bands use nearest neighbour. SCL's native 20 m
resolution is explicit. Radar requires finite positive VV/VH power, dataMask and
no shadow. Pixelwise medians use valid baseline observations; radar medians are
computed in linear power before dB. At least two independent observations per
pixel and 70% common AOI coverage are required. Low coverage is insufficient data.

Prototype detection uses optical mean absolute four-band difference >0.10 or
absolute VV/VH change >3 dB, retaining eight-connected patches of at least nine
10 m cells. Either sensor can flag a candidate. Overlapping patches from opposite
sensors in the target week are labelled as supported by both; areas remain separate
per sensor. No cause, equipment, deployment, activity, count or confidence is inferred.

Detections use deterministic IDs from stable location ID, sensor, acquisition and
an analysis version including a configuration fingerprint. Small JSONs retain
scene IDs/dates, baseline IDs, masks/coverage, grid, patches, thresholds, version
and attribution. Fixed-stretch PNGs show baseline composite, current acquisition
and highlighted patches. Report generation copies only allow-listed JSON/PNG/site
assets and refuses unexpected files in the publication output.

## Live historical validation

For exclusive end **2026-10-12**, the target is **2026-10-05 through 2026-10-11 UTC**
and the baseline **2026-09-07 through 2026-10-04 UTC**.

- Discovery retained 38 optical products; 19 alternative products were omitted
  from independent observation counts. Four optical target acquisitions remained:
  one quiet comparison with 99.76% common coverage, three insufficient comparisons.
- Six radar acquisitions share verified relative orbit 94, descending IW VV/VH.
  Five form the earlier baseline and one is the target comparison. The prototype
  produced one possible-change report with 100% common coverage. This result has
  not been independently verified as a real-world ground-change event.
- The first corrected uncached batch used 47 HTTP requests and reported
  7.1607681139640045 PU across measured catalogue/Process responses. The later
  deduplicated cached run used three requests, zero Process calls, reported 0.04 PU
  and preserved the single detection. The initial rejected selection batch's
  charges were not retained and remain unknown; these totals are not account usage.

All raw TIFFs, source/cache metadata, earlier diagnostics and per-attempt usage
stay outside Git under sibling `monitor-data/`. Small reports are under
`monitor-results/`, and the generated static site is under `monitor-site/`.
The retained Phase 1/2 workspaces and approval archives are unchanged.

## Verification

All 295 tests, Ruff, formatting, strict mypy, legacy settings/catalogue/schema
checks and repository hooks pass. New coverage includes unchanged/changed fixtures,
cloud/no-data/snow/water masks, pixelwise observation counts, linear radar medians,
missing/mismatched orbits, wrong scenes/transforms, cache integrity, request caps,
ambiguous charge failures, duplicate products, idempotent history, separate sensor
areas, XSS escaping, publication allow-list and failure isolation across locations.

Headless Edge verified desktop and 375 px report layouts, all images, filters,
detail links, source details and no JS/HTTP errors or overflow. Screenshots and
QA JSON remain under `monitor-data/qa/`. The flagged radar preview and a quiet
optical before/composite pair were visually inspected from the verified cache.
This is output/visual verification, not independent ground truth or threshold
calibration. The known synthetic changed/quiet cases pass. A subsequent
[independent CEMS event/control evaluation](historical-validation.md) produces
radar candidates in both periods, including matching-orbit cached controls.
Initial thresholds are not accepted; optical comparisons lack required coverage.
No validation location or report was added to the published production site.

## Actions, Pages and remaining acceptance

`.github/workflows/monitor.yml` provides weekly Monday 06:23 UTC and manual triggers,
a non-overlapping concurrency group, explicit permissions, a persistent
`monitor-results` branch, complete static build and official Pages artifact/deploy
actions with three bounded deployment attempts. Failed locations preserve earlier
reports. Cache is optional; history survives a fresh runner through Git.

Repository Actions is enabled. The existing working CDSE OAuth credentials were
encrypted with the repository public key and stored as `CDSE_CLIENT_ID` and
`CDSE_CLIENT_SECRET`; values were not written to local files, output or Git.
Pages uses build type `workflow`. The MVP merged in [PR #9](https://github.com/Savvyboi/AllYourBase/pull/9).
GitHub rejected the initial dispatch before any imagery request because
`runner.temp` was used in job-level `env`. [PR #10](https://github.com/Savvyboi/AllYourBase/pull/10)
moved it to supported step-level environments and added actionlint v1.7.12 to CI.
The validator rejects the original workflow and accepts the corrected workflows;
all 294 tests and required checks/hooks also pass on the clean GitHub runner.

The [first manual run](https://github.com/Savvyboi/AllYourBase/actions/runs/38756679440)
on 2026-10-15 succeeded at code `76991305c6c781d94aae46aa0c74643ab9d5eb43`, using
exclusive end 2026-10-12. It made 28 HTTP requests, retained one radar candidate,
and reproduced the local numerical/provenance result, including the optical
quiet comparison and three data gaps. The public notice additionally states
that thresholds are unvalidated prototypes. The ephemeral runner's PU journal
was not retained, so its measured PU total is unknown; the earlier local PU
figures are not substituted for this run.

The `monitor-results` branch at `d3c93e27a6fac199025a5812e801e910bf218c8f`
contains exactly six expected JSON/PNG files. The downloaded Pages artifact
contains exactly eight expected site/report/preview files, with no raw rasters
or credentials. The optional hidden `.nojekyll` marker is omitted by artifact
upload; the workflow serves static files directly. Public `reports.json` matches
the artifact, and the [live report](https://savvyboi.github.io/AllYourBase/) passes
1280 px desktop and 375 px mobile browser checks for images, filters, detail
links, source details, no overflow and no JS/HTTP errors. Both screenshots were
visually inspected. Deployment succeeded on its first attempt.

Metadata-only receipts and screenshots stay outside Git under
`monitor-data/publication-validation.json` and `monitor-data/qa/public-*`.
The next weekly run is scheduled for **2026-10-19 06:23 UTC**. Its unattended
execution, correctly dated output and retained history still require verification.
The [historical evaluation](historical-validation.md) supplies independent event
evidence but fails the quiet-control expectation; further independent evaluation
and threshold acceptance remain open. The MVP must not be reported complete yet.

Official references: [CDSE authentication](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html),
[Sentinel-2 L2A](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html),
[Sentinel-1 GRD](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S1GRD.html),
[GitHub Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages),
[encrypted Actions secrets](https://docs.github.com/en/rest/guides/encrypting-secrets-for-the-rest-api).
