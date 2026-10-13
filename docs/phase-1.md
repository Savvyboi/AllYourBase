# Phase 1 data access spike

Phase 0 is merged. This branch implements provider access and offline verification.
**Phase 1 acceptance is still open:** three AOIs need owner approval, and live
pixel reads and actual radar costs still need measurement. No provider selection
is finalized and no activity is scored.

## Inputs needed

- Owner approval of the three source-backed test windows described below.
- Three reviewed, cited test AOIs in three countries at different latitudes.
  AOIs may be supplied by the owner or proposed from permitted import sources and
  then approved. Do not promote the synthetic fixture into real monitoring data.
- A CDSE Sentinel Hub OAuth client, configured on the owner's machine using
  `CDSE_CLIENT_ID` and `CDSE_CLIENT_SECRET` or the OS keychain integration.
  Secret values must not be pasted into documentation, catalogue files or chat.

The plan's pilot remains Russia. Phase 1's multinational coverage checks are
separate from the later, larger Russia catalogue. Site selection is not assumed
to establish current deployments or equipment presence.

## Proposed test windows

`docs/proposals/phase-1-aois.geojson` contains three unapproved 4 km squares:

| Country | Location | Source |
| --- | --- | --- |
| RUS | Chkalovskiy Air Base | [OurAirports UUMU](https://ourairports.com/airports/UUMU/) |
| FIN | Rovaniemi Airport | [OurAirports EFRO](https://ourairports.com/airports/EFRO/) |
| AUS | RAAF Base Richmond | [OurAirports YSRI](https://ourairports.com/airports/YSRI/) |

Each window is constructed around a cited airport point in its UTM grid. It is
not a surveyed base boundary or a unit/equipment claim. Records retain the source
row, accessed date, SHA-256 and exact pinned snapshot URL. OurAirports publishes
its airport data in the public domain; see its [download terms](https://ourairports.com/data/).

Inspect these records and their geometry. The owner can approve, adjust or replace
them; only then set `approved: true`. A live spike refuses unapproved test AOIs.
These files stay separate from the production catalogue, which remains empty.

## Implemented access paths

1. Define a provider interface for discovery and windowed retrieval with immutable
   acquisition records: provider, collection, scene ID, acquisition time,
   polarisation, direction, relative orbit and available asset references.
2. Search Earth Search and CDSE optical STAC for the last eight **complete** ISO
   weeks. Compare newest AOI item dates and record gaps rather than assuming
   either catalogue is current.
3. Read only each AOI window from optical COG assets and record transfer/caching
   behavior. Keep pixels outside the code repository.
4. Use CDSE radar Catalog discovery, then Process requests for orthorectified,
   10 m, terrain-flattened linear gamma-zero; both polarisation bands plus masks.
   Measure actual request costs and processing units.
5. Probe Planetary Computer RTC coverage before enabling the fallback. Do not
   silently substitute uncorrected GRD for terrain-corrected radar.
6. Add bounded retries and a measured budget guard; keep secrets local and
   redact HTTP diagnostics. Record errors per provider/site without producing
   a normal or elevated activity level from missing data.
7. Produce one acquisitions table per site/provider/week and a usage report.
   ADR 0002 records the implemented contracts and keeps selection provisional
   until the measurements exist.

The `ProviderClient` provides discovery and window reads behind one contract.
Scene records are immutable. Pagination includes STAC next links and Sentinel Hub
cursors, cycle checks, duplicate handling and half-open UTC filtering. Antimeridian
AOIs are split into small discovery queries.

Radar results must match their requested source IDs, CRS, full transform and
dimensions, and contain four FLOAT32 bands and valid pixels. Missing credentials,
empty searches and failed providers have distinct statuses. Provider failures do
not erase other results; a spike with access failures exits with code 1.

## Readiness and local commands

| Provider | Access | Checked here |
| --- | --- | --- |
| Earth Search | Anonymous metadata and COG pixels | Collection and sample asset keys reachable |
| CDSE STAC | Anonymous metadata; separate S3 keys for private S3 assets | Collection and sample asset keys reachable |
| CDSE Sentinel Hub | OAuth Catalog and Process | Credentials missing |
| Planetary Computer RTC | Anonymous metadata; pixel reads not implemented in this spike | Collection reachable; AOI coverage unmeasured |

RTC remains disabled as a pipeline fallback. Selecting it explicitly for a
metadata spike does not enable it or claim coverage.

```sh
uv sync --locked --extra access
uv run --extra access allyourbase providers doctor --online
uv run allyourbase providers spike --aoi-file docs/proposals/phase-1-aois.geojson --plan
```

After AOI approval, compare public metadata:

```sh
uv run allyourbase providers spike --aoi-file docs/proposals/phase-1-aois.geojson --provider earth_search --provider cdse_stac --provider planetary_computer
```

Configure OAuth credentials locally in the environment or under their variable
names in the `allyourbase-cdse` keyring service. Follow the
[CDSE authentication instructions](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html).
CDSE S3 pixel reads additionally use `CDSE_S3_ACCESS_KEY_ID` and
`CDSE_S3_SECRET_ACCESS_KEY`; these are separate from OAuth credentials. See
[CDSE S3 access](https://documentation.dataspace.copernicus.eu/APIs/S3.html).
`.env` is ignored but not loaded automatically.

```sh
uv run --extra access allyourbase providers spike --aoi-file docs/proposals/phase-1-aois.geojson --pixels --radar
```

Repeated `--provider` and optional `--site` restrict a check. `--weeks` defaults to
eight; `--end-week` selects a historical final complete UTC week. Reports and chips
are under `$ALLYOURBASE_HOME/spikes/<run-id>/`; the charge ledger is under `usage/`.

## Measurement limits

Optical bands retain native grids; resampling, cloud/SCL masking, alignment and
harmonized caching belong to Phase 3. GDAL transfer bytes and range-request counts
are explicitly unknown in usage reports. File dimensions and georeferencing are
recorded without claiming transfer measurement or cache reuse.

Radar requests ask for 10 m output pixels. EW source data at HIGH resolution has
25 m spacing; `native_spacing_m` records it. Actual cost headers replace durable
charge reservations; missing headers keep costs unknown and reservations in place.
The configured reservation is provisional, not a measured or guaranteed maximum
charge. Process POSTs are not blindly retried after ambiguous failures.

## Acceptance

The eight-week tables, windowed optical reads and valid radar chip metadata must be
reproducible for all three approved sites. The provider decision must cite measurements,
coverage and budget consumption. Live integration checks run only when explicitly
configured; offline tests use synthetic metadata and pixels. These live acceptance
criteria have not passed yet. Keep this PR in draft and update ADR 0002 after
measuring the approved AOIs before treating Phase 1 as complete.
