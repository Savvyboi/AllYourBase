# ADR 0002 Provider access and selection

Status: primary and optical fallback selection verified for the approved Russian pilot.
Date: 2026-10-13.

## Context and decisions

The original build plan requested an eight-week multinational spike. On
2026-10-14 the owner changed the test scope to Russian airbases and approved
Chkalovskiy, Engels and Olenya. This pilot measures northern-latitude Russian
coverage; multinational and southern-hemisphere live validation remain outside
its scope. Use one `ProviderClient` discovery/window-read
interface. Endpoints, collections, band aliases and tuning values stay in settings.
Direct STAC/Process REST calls via HTTPX expose per-attempt accounting; Rasterio
reads bounded native optical windows. Higher-level STAC/xarray packages remain
available for Phase 3 harmonization.

Tokens stay in memory. Client credentials come from environment variables or
the OS keychain; private S3 access uses separate environment keys. Serialized
asset URLs exclude signatures, and public errors omit raw HTTP/GDAL bodies.

The access spike uses a locked, atomic JSON radar charge ledger, separate from
the future DuckDB results store. Actual reported costs replace reservations;
unknown or ambiguous costs keep their reservation. Process POSTs are not blindly
retried after failures that may already have incurred charges. Catalogue reads
have bounded retries. Reservations need calibration against actual charges.

Use supported ORBIT mosaicking for radar scene metadata; its sample array and
`scenes.orbits[].tiles` follow the [CDSE evalscript contract](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Evalscript/Functions.html).
Return masked pixels for empty or ambiguous orbit samples.

Validate exact radar scene provenance, requested CRS, transform, dimensions,
FLOAT32 bands and masks before recording a successful chip. Any mismatch is a
data-access failure, never an activity assessment.

## Measured primary selection for the Russian pilot

On 2026-10-14, eight-week discovery returned items at each of the three approved
Russian airbases from Earth Search, CDSE optical, CDSE Sentinel Hub and Planetary
Computer RTC. Earth Search and CDSE optical have the same newest acquisition date
at each site within the sampled window. Seven-band Earth Search AOI reads and
terrain-corrected four-band CDSE radar reads pass for all three sites. Each radar
Process request reported 3.067035675 PU for a 401 by 401, 10 m output grid.

Use Earth Search as the measured optical primary and CDSE Sentinel Hub as the
measured radar primary for this pilot. Select CDSE STAC as the verified optical
fallback: its separate S3 keys enabled seven-band Colab reads at all three areas,
and independent local validation passes all 21 files. Planetary Computer metadata
coverage is present for this sample, but pixel retrieval/signing is unimplemented and its
pipeline fallback remains disabled. These observations do not establish global
coverage, clear optical observations, or future availability.

See `docs/phase-1-live-validation.md` for per-week tables, local report IDs, all
attempted-request costs and acceptance evidence. The CDSE optical window-read
check now passes, so PR #2 can proceed to code review. Only a terminal `.SAFE` suffix is
normalized when comparing radar product IDs; checksums and `_COG` remain exact.

## Colab continuation on 2026-10-14

Google Colab is the owner-selected processing runtime. The Phase 1 notebook is
thin: it installs a SHA-256-pinned source ZIP with locked dependencies, loads
separate S3 credentials from Colab Secrets into subprocess memory, calls the CLI
and exports completed evidence. It does not establish full processing, resumable
backfill or shared writer locking. Keep working files on the VM and archive
completed runs to downloads or Drive.

The owner supplied the successful Colab run
`20261013T234356Z-1737c37ff296467c979cd05e9ab00b63`. All 24 site/week rows contain
acquisitions and match the earlier discovery counts. Independent local checks
agree with Colab on all 21 files: configured bands/parts, scene/asset provenance,
hashes, native grids and finite non-nodata pixels. The source manifest matches
the delivered bundle. The run made no radar Process calls; STAC PU headers were
absent and S3 transfer bytes/range-request counts remain unknown. This verifies
optical fallback for these areas and dates, not general availability or full
Colab processing. Secret values were not imported into the local project.

## Primary references

- [CDSE STAC](https://documentation.dataspace.copernicus.eu/APIs/STAC.html)
- [Catalog search and pagination](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Catalog/Examples.html)
- [Sentinel-1 GRD processing and native spacing](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S1GRD.html)
- [Process examples](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Process/Examples/S1GRD.html)
- [Earth Search optical collection](https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a)
