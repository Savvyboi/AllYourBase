# Phase 1 data access spike

After the Phase 0 source is reviewed, implement and measure provider access before
building indicators. The deliverable is evidence of usable acquisitions and costs,
not a monitoring claim.

## Inputs needed

- Review of the Phase 0 pull request in `Savvyboi/AllYourBase`. The built website
  later uses its own repository; its destination is still to be chosen.
- Three reviewed, cited test AOIs in three countries at different latitudes.
  AOIs may be supplied by the owner or proposed from permitted import sources and
  then approved. Do not promote the synthetic fixture into real monitoring data.
- A CDSE Sentinel Hub OAuth client, configured on the owner's machine using
  `CDSE_CLIENT_ID` and `CDSE_CLIENT_SECRET` or the planned keychain integration.
  Secret values must not be pasted into documentation, catalogue files or chat.

The plan's pilot remains Russia. Phase 1's multinational coverage checks are
separate from the later, larger Russia catalogue. Site selection is not assumed
to establish current deployments or equipment presence.

## Implementation work

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
   Write `docs/adr/0002-provider-selection.md` only after the measurements.

## Acceptance

The eight-week tables, windowed optical reads and valid radar chip metadata are
reproducible for all three sites. The provider decision cites the measurements,
coverage and budget consumption. Live integration checks run only when explicitly
configured; offline tests use recorded non-secret metadata and synthetic pixels.
