# Phase 1 data access spike

Phase 0 is merged. This branch implements provider access and offline verification.
**Primary access passes for the Russian pilot:** the owner approved three airbase
test windows on 2026-10-14. Eight-week discovery, Earth Search optical windows and
CDSE radar windows now pass. CDSE optical fallback also passes from Google Colab,
with 21 band TIFFs independently verified locally. See `docs/phase-1-live-validation.md` for measured evidence. No activity is scored.

## Inputs needed

- Three reviewed, cited Russian airbase test windows at different latitudes,
  approved by the owner on 2026-10-14.
- New or replacement AOIs still require review of their sources and geometry.
  Do not promote synthetic fixtures into real monitoring data.
- A CDSE Sentinel Hub OAuth client, configured on the owner's machine using
  `CDSE_CLIENT_ID` and `CDSE_CLIENT_SECRET` or the OS keychain integration.
  Secret values must not be pasted into documentation, catalogue files or chat.

The owner changed this access spike from three countries to Russian airbases on
2026-10-14. Southern-hemisphere and multinational live coverage are outside this
pilot; synthetic global-grid tests remain in place. Site selection is not assumed
to establish current deployments or equipment presence.

## Approved test windows

`docs/proposals/phase-1-aois.geojson` contains three owner-approved 4 km test squares:

| Country | Location | Source |
| --- | --- | --- |
| RUS | Chkalovskiy Air Base | [OurAirports UUMU](https://ourairports.com/airports/UUMU/) |
| RUS | Engels Air Base | [OurAirports RU-8602](https://ourairports.com/airports/RU-8602/) |
| RUS | Olenya Air Base | [OurAirports RU-4464](https://ourairports.com/airports/RU-4464/) |

Each window is constructed around a cited airport point in its UTM grid. It is
not a surveyed base boundary or a unit/equipment claim. Records retain the source
row, accessed date, SHA-256 and exact pinned snapshot URL. OurAirports publishes
its airport data in the public domain; see its [download terms](https://ourairports.com/data/).

The owner explicitly approved these three areas and the live access checks on
2026-10-14. A live spike continues to refuse any unapproved replacement AOIs.
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

## Readiness and runtime commands

| Provider | Access | Checked here |
| --- | --- | --- |
| Earth Search | Anonymous metadata and COG pixels | Eight-week discovery and seven-band windows pass at all three sites |
| CDSE STAC | Anonymous metadata; separate S3 keys for private S3 assets | Eight-week discovery and seven-band windows pass at all three sites from Colab |
| CDSE Sentinel Hub | OAuth Catalog and Process | Eight-week discovery, radar windows and actual PU measurement pass |
| Planetary Computer RTC | Anonymous metadata; pixel reads not implemented in this spike | Metadata present at every site/week in this sample; pipeline fallback disabled |

RTC remains disabled as a pipeline fallback. Selecting it explicitly for a
metadata spike does not enable it or claim coverage.

```sh
uv sync --locked --extra access
uv run --extra access allyourbase providers doctor --online
uv run allyourbase providers spike --aoi-file docs/proposals/phase-1-aois.geojson --plan
```

After AOI approval, compare public metadata:

```sh
uv run allyourbase providers spike --aoi-file docs/proposals/phase-1-aois.geojson --provider earth_search --provider cdse_stac --provider cdse_sentinelhub --provider planetary_computer
```

Configure OAuth credentials locally in the environment or under their variable
names in the `allyourbase-cdse` keyring service. Follow the
[CDSE authentication instructions](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html).
CDSE S3 pixel reads additionally use `CDSE_S3_ACCESS_KEY_ID` and
`CDSE_S3_SECRET_ACCESS_KEY`; these are separate from OAuth credentials. See
[CDSE S3 access](https://documentation.dataspace.copernicus.eu/APIs/S3.html).
`.env` is ignored but not loaded automatically. `providers doctor` separately
reports `pixel_credentials` for S3, so anonymous metadata readiness cannot be
mistaken for authenticated pixel access. Presence does not prove authentication.

The owner selected **Google Colab for processing** on 2026-10-14. The bounded
[Colab notebook](../notebooks/phase-1-cdse-optical.ipynb) passed this acceptance
check on 2026-10-14; follow [its setup guide](../notebooks/README.md). Create keys in the
[CDSE S3 key manager](https://eodata-s3keysmanager.dataspace.copernicus.eu/), choose
an expiry and save the one-time secret directly in Colab Secrets under the two
variable names above. Enable access for this notebook. OAuth credentials stored
in the Windows keychain are not copied to Colab and are not needed for this
optical-only check. The notebook keeps credentials in subprocess memory and does
not write them to the source ZIP, runtime settings or evidence archive.

A source ZIP with a matching SHA-256 includes the exact CLI/verifier and locked
requirements, including current working-tree changes. The notebook runs only
`cdse_stac`, with `--weeks 8 --end-week 2026-W41 --pixels`. It reads one acquisition
per approved area. A CPU runtime is sufficient. Full resumable processing and
shared writer locking remain future Phase 7a work.

After retrieval, verify the saved output without repeating network requests:

```sh
uv run --extra access allyourbase providers validate-optical --report-dir /path/to/external/spikes/RUN_ID --aoi-file docs/proposals/phase-1-aois.geojson --provider cdse_stac
```

The verifier writes `optical-validation.json` only on success. It requires all
configured bands/parts for all approved areas, matching scene/asset provenance,
SHA-256 hashes, CRS, transforms, bounded dimensions, finite non-nodata pixels and
valid SCL classes. Native windows may be clipped to their source tile; these
checks do not establish cloud-free coverage. Export the complete evidence ZIP
before the Colab VM is discarded.

```sh
uv run --extra access allyourbase providers spike --aoi-file docs/proposals/phase-1-aois.geojson --provider earth_search --provider cdse_sentinelhub --pixels --radar
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
configured; offline tests use synthetic metadata and pixels. Primary-provider
access, measured radar costs and CDSE optical fallback windows pass for this
Russian pilot. The Colab source manifest matches the delivered bundle, and local
revalidation agrees with the Colab result. PR #2 can proceed to code review;
passing access acceptance does not itself authorize merging. Multinational live
testing was removed from this pilot by the owner; global synthetic geometry
tests still run.
