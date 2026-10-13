# ADR 0002 Provider access and selection

Status: access contracts implemented; provider selection provisional.
Date: 2026-10-13.

## Context and decisions

The build plan requires an eight-week multinational spike before relying on
provider coverage or costs. Use one `ProviderClient` discovery/window-read
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

## Provider selection pending

Earth Search, CDSE optical and Planetary Computer RTC collections were reachable
on 2026-10-13. Optical asset names/schemes were inspected in global sample items.
CDSE OAuth was not configured in the development environment. No approved-area
acquisition table, live chip or measured radar charge is yet available.
Primary/fallback choices remain provisional; RTC collection access does not
prove recent coverage at an AOI.

The three cited AOI proposals need owner approval. Once their searches, pixel
reads and costs are measured, update this ADR with evidence and final selection.
Phase 1 remains incomplete until that acceptance work passes.

## Primary references

- [CDSE STAC](https://documentation.dataspace.copernicus.eu/APIs/STAC.html)
- [Catalog search and pagination](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Catalog/Examples.html)
- [Sentinel-1 GRD processing and native spacing](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S1GRD.html)
- [Process examples](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Process/Examples/S1GRD.html)
- [Earth Search optical collection](https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a)
