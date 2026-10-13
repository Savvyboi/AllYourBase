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
- CDSE optical metadata is current at all three AOIs, but pixel reads report
  `s3_credentials_missing`: separate CDSE S3 keys are not configured.
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
| CDSE optical fallback check | `20261013T225301Z-5f10525d9794471bb46b92bc2f92aa15` |

Set `ALLYOURBASE_HOME` to the external data workspace and rerun the commands in
`docs/phase-1.md`. Acquisition results may change as catalogues ingest late scenes.

## Remaining acceptance

Primary optical and radar access pass for the owner-approved Russian pilot.
Complete the CDSE optical window-read check after local S3 setup before closing
the original provider-comparison acceptance criteria. The measured primary choices
are Earth Search and CDSE Sentinel Hub; fallback pixel access is still provisional.
