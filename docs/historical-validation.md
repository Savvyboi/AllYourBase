# Historical validation: EMSR773

Evaluated 2026-10-15. **Initial thresholds are not accepted.** The mapped-event
case produces radar candidates, but pre-event controls also produce substantial
flags. Optical has no comparison meeting 70% common coverage. These examples
establish neither an accuracy estimate nor validated detection limits.

## Independent reference and selection

Use [CEMS activation EMSR773](https://mapping.emergency.copernicus.eu/activations/EMSR773/),
AOI03 Horta Sud, delineation product version 1. Its post-event reference imagery
is GeoEye-1 / WorldView-2 from 2024-10-31 around 10:22 UTC, independently sourced
from the Sentinel imagery used by this pipeline. The source table links the
mapped features to those sensors. The [official event account](https://mapping.emergency.copernicus.eu/news/flood-in-valencia-region-spain/)
dates the flood onset to 2024-10-29.

The [official vector package](https://rapidmapping.emergency.copernicus.eu/backend/EMSR773/AOI03/DEL_PRODUCT/EMSR773_AOI03_DEL_PRODUCT_v1.zip)
is 17,494,094 bytes, SHA-256
`9a756cafde913034bbeffc1ac5a53582cffa28034d7173c78a5988ac2c40cd3b`.
The package, reference GeoJSON, source metadata, numerical cutouts and previews
stay outside Git. CEMS reference data: European Union / Copernicus Emergency
Management Service.

Before making Sentinel requests, select the 1 km square with the largest combined
CEMS `Flooded area` or `Flood trace` fraction among 250 m-spaced metric centres in
EPSG:32630. Require the whole square inside AOI03 and longitude -0.50 to -0.37,
latitude 39.37 to 39.46; break ties by easting then northing. The selected centre is
**39.432640653389136, -0.4061112725881115**, projected centre 723250, 4368000 m.
The independently mapped fraction is 66.94%; only 0.99% is still mapped as flooded
at reference time, with most of the remainder labelled flood trace. This is an
urban flood/trace example, not a mostly open-water test.

This one-off location is `emsr773-validation`, outside the production `sites.yaml`
and all published history. Keep the production detection settings unchanged:
3 dB radar, 0.10 optical, nine connected cells, two earlier observations per pixel,
70% common coverage and LEE 3x3. Only the validation request cap changes to 70;
its configuration fingerprint is therefore distinct. Validation code is
`44843b1f8f69adc2cd4396fbdc5762a291a3d3e6`, analysis version
`ground-change-0.1.0+9aaf25de2929`.

## Windows and outcomes

The predeclared event run ends exclusively 2024-11-04: target October 28 through
November 3, baseline September 30 through October 27. The predeclared control
ends 2024-10-28: target October 21 through 27, baseline September 23 through
October 20. All dates are UTC. The control predates this event; that alone does
not establish complete landscape stability or prove every flag false.

| Case | Radar acquisition UTC | Relative orbit / direction | Earlier observations | Common coverage | Flagged area, this acquisition |
| --- | --- | --- | --- | --- | --- |
| Event | 2024-10-31 18:02:56 | 103 ascending | 2 | 100% | 381,700 m2 |
| Event | 2024-11-01 06:02:07 | 110 descending | 2 | 100% | 358,400 m2 |
| Pre-event control | 2024-10-25 06:10:16 | 8 descending | 2 | 100% | 340,700 m2 |
| Pre-event control | 2024-10-26 17:55:01 | 30 ascending | 2 | 100% | 296,100 m2 |
| Cached matching-orbit control | 2024-10-19 18:02:56 | 103 ascending | 2 | 100% | 157,000 m2 |
| Cached matching-orbit control | 2024-10-20 06:02:07 | 110 descending | 2 | 100% | 188,300 m2 |

Do not add these areas across acquisitions or sensors. Each comparison uses
matching baseline geometry. Because the first control week contains different
orbit groups from the event week, a follow-up diagnostic checks matching-orbit
pre-event acquisitions from the existing verified cache. That diagnostic uses
an exclusive end of October 21, with the strictly earlier September 16 through
October 13 baseline. It is exploratory, selected after the first results, limited
to orbits 103/110, and explicitly refuses all network requests. Both matching
baseline groups contain two observations. It is not a third full live run.

The October 31 candidate intersects 273,428.91 m2 of mapped flood/trace polygons;
the November 1 candidate intersects 265,214.00 m2. These are geometric overlaps,
not precision, recall or evidence of cause. The reference covers 66.94% of the
square, differs in acquisition time and resolution, and is not complete truth
for every possible ground change. Broad flags in the controls prevent accepting
thresholds on overlap alone.

Optical: the event comparison has 33.09% valid common coverage. The two control
comparisons have 0% and 67.73%. All are `insufficient_data`; none establishes a
quiet optical comparison. Seven optical products in each live window are
rejected as `scene_selection_mismatch`; overlapping alternative products are
tried without weakening exact returned-product verification. Those rejections
are retained in check diagnostics. A successful radar candidate does not remove
the optical gaps/errors.

Fixed-stretch radar baseline/current previews were visually inspected for the
October 31 event and October 26 control. Broad bright returns persist in both;
these coarse previews do not verify event cause. The earlier Chkalovsky optical
quiet comparison remains a visually inspected example, not independent proof
that the radar thresholds are reliable.

## Requests, cost and retained evidence

| Run | HTTP requests | Process calls | Reported PU sum | Unknown Process charges |
| --- | --- | --- | --- | --- |
| Event | 29 | 26 | 6.397828733598581 | 0 |
| Pre-event control, shared cache | 7 | 4 | 1.0572525981033687 | 0 |
| Matching-orbit cached diagnostic | 0 | 0 | 0 | 0 |

These are measured response-header totals for these requests, not account-wide
usage. Raw usage journals retain every attempt. No further paid runs were made
for documentation, visual checks or the matching-orbit diagnostic.

External sibling paths, relative to the repository:

- `../monitor-data/validation-emsr773/`: frozen `protocol.json`, reference archive,
  `validation-receipt.json`, `matched-control-receipt.json` and local YAML inputs.
- `../monitor-data/validation-emsr773-data/`: verified cache and request journals.
- `../monitor-data/validation-emsr773-results/`: event reports/previews.
- `../monitor-data/validation-emsr773-control-results/`: original control reports/previews.
- `../monitor-data/validation-emsr773-matched-results/`: cached control reports/previews.

The run CLI now returns `request_cap`, `requests_used`,
`reported_processing_units` and `unknown_process_charges` from the same totals
saved in the local journal. GitHub Actions logs can retain these safe aggregates
when its temporary workspace disappears. Full observations, payloads and
credentials are excluded from this console summary. This does not recover the
unknown PU total of the first manual Pages publication.

## Acceptance decision

Keep thresholds labelled unvalidated prototypes. Do not tune them to suppress
this single control and then call the same case independent validation. Next,
assemble additional independently assessed quiet and changed cases, separate
calibration from held-out evaluation, and assess radar background variability
and optical availability. Preserve this failed control expectation as evidence.
The unattended weekly publication check also remains open until its actual
scheduled execution.
