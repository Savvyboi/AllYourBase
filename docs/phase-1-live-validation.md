# Phase 1 Russian airbase access measurements

Measured on 2026-10-14 in Europe/Helsinki; report folder IDs use UTC.
The owner approved Chkalovskiy, Engels and Olenya as 4 km access-test windows.
This changes the original three-country spike to a Russian northern-latitude pilot.
No activity, aircraft count, unit deployment or equipment assessment is produced.

## Eight complete ISO weeks

Window: 2026-W34 through 2026-W41, from 2026-08-17T00:00:00Z to
2026-10-12T00:00:00Z (exclusive). All 96 site/provider/week searches have items.
Counts below are catalogue scene items; overlapping optical tiles are not merged
into satellite overpasses, and scene presence does not establish clear pixels at the AOI.

### Chkalovskiy Air Base

| Week | Earth Search optical | CDSE optical | CDSE radar | PC RTC |
| --- | ---: | ---: | ---: | ---: |
| 2026-W34 | 8 | 8 | 2 | 2 |
| 2026-W35 | 6 | 6 | 1 | 1 |
| 2026-W36 | 8 | 8 | 1 | 1 |
| 2026-W37 | 8 | 8 | 1 | 1 |
| 2026-W38 | 8 | 8 | 1 | 1 |
| 2026-W39 | 8 | 8 | 1 | 1 |
| 2026-W40 | 6 | 6 | 2 | 2 |
| 2026-W41 | 8 | 8 | 1 | 1 |

### Engels Air Base

| Week | Earth Search optical | CDSE optical | CDSE radar | PC RTC |
| --- | ---: | ---: | ---: | ---: |
| 2026-W34 | 3 | 3 | 1 | 1 |
| 2026-W35 | 3 | 3 | 1 | 1 |
| 2026-W36 | 4 | 4 | 1 | 1 |
| 2026-W37 | 4 | 4 | 1 | 1 |
| 2026-W38 | 4 | 4 | 2 | 2 |
| 2026-W39 | 3 | 3 | 1 | 1 |
| 2026-W40 | 3 | 3 | 1 | 1 |
| 2026-W41 | 4 | 4 | 1 | 1 |

### Olenya Air Base

| Week | Earth Search optical | CDSE optical | CDSE radar | PC RTC |
| --- | ---: | ---: | ---: | ---: |
| 2026-W34 | 6 | 6 | 6 | 7 |
| 2026-W35 | 5 | 5 | 6 | 6 |
| 2026-W36 | 6 | 6 | 5 | 6 |
| 2026-W37 | 7 | 7 | 6 | 6 |
| 2026-W38 | 6 | 6 | 6 | 7 |
| 2026-W39 | 6 | 6 | 6 | 7 |
| 2026-W40 | 5 | 5 | 6 | 6 |
| 2026-W41 | 6 | 6 | 6 | 6 |

## Windowed retrieval and usage

- Earth Search: one acquisition per site, all seven configured bands, 21 local TIFF files.
  Native 10 m and 20 m grids were preserved; cloud/SCL screening is a later milestone.
- CDSE radar: one validated FLOAT32 TIFF per site, with VV, VH, shadowMask and dataMask.
  Each output is 401 by 401 pixels at 10 m; source identity, CRS, transform, dimensions,
  finite values, masks and output SHA-256 pass validation.
- Successful radar Process requests each reported 3.067035675 PU; three chips used
  9.201107025 PU, plus 0.06 PU for their three radar catalogue searches.
- The complete session made seven radar Process requests, including rejected validation
  attempts and one diagnostic request: 21.469249725 reported Process PU. Radar catalogue
  searches across the recorded runs added 0.18 PU. These are measured charges, not quota estimates.
- The first radar responses exposed asymmetric `.SAFE` suffix handling. Both IDs now
  have only that terminal suffix normalized; product checksum and `_COG` remain part
  of the exact identity. Original and returned identifiers are retained.
- CDSE optical fallback: the Colab run produced all seven configured bands at
  each site, 21 TIFFs in total. Local verification independently passes scene and
  asset provenance, band completeness, CRS, transforms, bounded dimensions,
  finite non-nodata pixels, SCL classes and SHA-256 hashes. Its 24 site/week rows
  all contain acquisitions and exactly match the earlier CDSE counts above.
- The fallback run recorded three successful STAC discovery requests and made
  no radar Process calls. STAC processing-unit headers were absent, so the
  report's zero known PU is not an account-wide cost or quota measurement.
- Planetary Computer RTC has metadata coverage at every site/week in this sample.
  RTC pixel retrieval/signing remains unimplemented and this pipeline fallback stays disabled.
- GDAL HTTP range-request counts and transfer bytes remain uninstrumented.

## Reproducible local evidence

Raw imagery, source records, request ledgers and full reports remain outside Git
under the local data workspace. Recorded runs:

| Check | Local run ID |
| --- | --- |
| Four-provider metadata | `20261013T224829Z-078734a919274bc291cdd3770deef2f8` |
| Primary optical reads and initial radar validation | `20261013T224923Z-b8a0ac0dad054b08a7cf615ccd406574` |
| Successful radar verification | `20261013T225212Z-ac086a1b121f432abf48df71cff4a0b7` |
| CDSE optical attempt before S3 setup | `20261013T225301Z-5f10525d9794471bb46b92bc2f92aa15` |
| Successful Colab CDSE optical fallback | `20261013T234356Z-1737c37ff296467c979cd05e9ab00b63` |

Set `ALLYOURBASE_HOME` to the external data workspace and rerun the commands in
`docs/phase-1.md`. Acquisition results may change as catalogues ingest late scenes.

## Colab fallback acceptance on 2026-10-14

The owner selected Google Colab for processing, configured its separate S3 keys
and supplied the completed evidence archive. The source manifest exactly matches
the delivered 49-file bundle. Runtime settings match project settings except for
the Colab profile and VM workspace. Local validation exactly matches the archived
Colab `optical-validation.json`; no new imagery requests were made during review.

| Area | CRS | 10 m band windows | 20 m band windows |
| --- | --- | --- | --- |
| Chkalovskiy | EPSG:32637 | 411 by 412 | 206 by 207 |
| Engels | EPSG:32638 | 414 by 414 | 207 by 208 |
| Olenya | EPSG:32636 | 407 by 407 | 204 by 204 |

Dimensions above are width by height. B02, B03, B04 and B08 retain 10 m pixels;
B11, B12 and SCL retain 20 m pixels. Native windows may include edge padding or
source-tile clipping; these results are access evidence, not cloud-free coverage
or completed preprocessing.

Evidence archive SHA-256:
`7f7e1fd3857ee53660b2001a7a8298e9ba765c10d228b49cd4faa5730800797e`.
Source bundle SHA-256:
`687f96a2112500c2c82b1a1eeaaa694eab59acef4321dacdfc90027aeb88b23b`.
The source bundle records base revision `5dff830b5acd7b7b3900bde5cc6be1ce58346148`
and exact working-tree file hashes. The original ZIP is preserved under the
external workspace's `archives/`, and the extracted run under `spikes/` includes
`optical-validation.json` and local `evidence-acceptance.json`. Credentials and
full reports remain outside Git.

## Acceptance status

Phase 1 live access acceptance passes for the owner-approved Russian pilot.
Earth Search is the measured optical primary, CDSE STAC the verified optical
fallback and CDSE Sentinel Hub the measured radar primary. PR #2 can proceed to
code review. Planetary Computer RTC pixel retrieval, GDAL transfer accounting,
production catalogue ingestion and full resumable Colab processing remain pending.
