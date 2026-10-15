# Sentinel ground-change monitor: coding-agent plan

Build a small working MVP. Given coordinates, monitor a 1 km × 1 km square, analyse Sentinel-1 and Sentinel-2 imagery acquired during the last seven days, and automatically publish possible changes to GitHub Pages.

Use one Python pipeline, GitHub Actions for the weekly run, and plain HTML/CSS/JavaScript for the website. Start with one location. If working in an existing repository, inspect its instructions and reuse working components.

1. **Define inputs and time windows.**

   Put locations in `sites.yaml`: stable ID, name, latitude, longitude, and `size_m: 1000`. Coordinates are entered here for the MVP. Validate latitude/longitude, including their order when calling APIs. Project each centre into an appropriate local metric CRS and create a square extending 500 m in each direction. Freeze one grid per location: 10 m spacing, 100 × 100 pixels. Use UTC and non-overlapping windows: the latest seven complete days, with the preceding 28 days as the baseline. Allow an explicit end date for reproducible historical runs.

2. **Fetch small imagery cutouts from Copernicus.**

   Use Copernicus Data Space Sentinel Hub: Catalog API for discovery and Process API for numerical GeoTIFF cutouts. Fetch each acquisition separately, retain scene IDs and acquisition times, and request the same CRS, extent and grid every time.

   - Sentinel-2 L2A: reflectance bands B02, B03, B04 and B08, plus SCL and dataMask.
   - Sentinel-1 GRD: IW mode, VV/VH, dataMask and shadowMask; request `GAMMA0_TERRAIN`, `orthorectify: true`, `demInstance: COPERNICUS_30` and a small LEE speckle filter.

   Use OAuth client credentials stored as GitHub Actions secrets. Reuse tokens until expiry. Cache cutouts locally, retry temporary errors/429 responses with backoff, and cap requests per run. Never analyse display PNGs or download whole satellite tiles unnecessarily.

3. **Prepare comparable images.**

   For Sentinel-2, mask missing, defective, cloud, cloud-shadow, snow/ice and water pixels using SCL; conservatively keep land classes 4 and 5, with a small buffer around cloud/shadow masks. Resample categorical masks with nearest neighbour. SCL is native 20 m even when placed on the 10 m grid.

   For Sentinel-1, compare only matching relative orbit, flight direction, acquisition mode and polarisation. Obtain relative-orbit metadata during discovery; direction alone is insufficient. Fetch the selected acquisition without mixing passes. Mask missing data, radar shadow and invalid/non-positive power values. Skip comparisons when geometry cannot be verified.

   Build pixelwise baseline medians from valid earlier observations, separately for each sensor and radar orbit group. Compute radar medians in linear power before conversion to dB. Evaluate every usable acquisition from the target week against its matching baseline. Require at least two baseline observations per evaluated pixel and 70% valid common AOI coverage per comparison. If these checks fail, record `insufficient_data`.

4. **Detect change with simple rules.**

   Start with these configurable prototype rules:

   - Optical: mean absolute reflectance difference across the four bands exceeds 0.10.
   - Radar: absolute backscatter difference exceeds 3 dB in VV or VH.
   - Retain connected patches of at least nine 10 m grid cells, approximately 900 m².

   These are starting values to tune against real examples, not validated detection limits. Either sensor can produce a candidate. When both show overlapping change, label it as supported by both sensors. Keep changed-area measurements separate per sensor to avoid double counting.

   Call every detection **possible ground change**. Weather, moisture, vegetation, snow and image misalignment can produce changes. Do not infer the cause, count people or vehicles, or assign an invented confidence percentage. A 10 m output grid does not guarantee 10 m resolving power.

5. **Generate a small static report.**

   For a flagged location, publish its name, coordinates, observation and baseline dates, sensor(s), valid coverage, changed area, before/after previews and highlighted change patches. Clearly label baseline previews as composites. Include source scene IDs, analysis version, thresholds and Copernicus attribution. Use fixed image stretches for comparable previews.

   The homepage shows recent detections and each location's latest check status: `possible_change`, `no_change_detected`, `insufficient_data` or `error`. No-change and failed-data runs create no activity news item. Report which sensors were usable; no detected change only describes the valid area observed.

6. **Automate and preserve history.**

   Add weekly and manual GitHub Actions triggers. The workflow checks out code and persistent report history, runs Python, commits small report JSON files and previews to a dedicated results branch, builds the complete site, and deploys through the official GitHub Pages Actions workflow. GitHub Pages serves the output; analysis runs in Actions.

   Use deterministic detection IDs based on location, sensor, current acquisition and analysis version so reruns do not duplicate detections. Preserve history across fresh runners; Actions cache is optional acceleration. Use a concurrency lock, explicit workflow permissions and deployment retries. Keep raw rasters and credentials out of the published site. Preserve earlier reports when a location fails, show the error, and continue processing other locations.

7. **Build and verify in this order.**

   First make a local command work for one location and historical week. Then add the second sensor, report generation, and finally scheduled publication. Suggested modules: `fetch.py`, `prepare.py`, `detect.py`, `report.py` and `main.py`; keep thresholds in one configuration file. Provide a README for credentials, adding coordinates, local execution and Pages setup.

   Acceptance checks: an unchanged fixture produces no detection; a qualifying changed patch does; cloudy/no-data imagery produces `insufficient_data`; mismatched radar orbits are rejected; rerunning identical inputs preserves history without duplicate reports. Visually inspect one known-change and one quiet historical example before accepting the initial thresholds. A manual workflow must publish a working page without exposing secrets.

The MVP is complete when adding coordinates and running the workflow produces a correctly dated result, and the next scheduled run can do the same unattended. Defer object recognition, a coordinate-entry web form, a database and a complex frontend.

Official implementation references:

- [CDSE Sentinel Hub authentication](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html)
- [Sentinel-2 L2A bands, masks and processing](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html)
- [Sentinel-1 GRD processing and speckle filtering](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S1GRD.html)
- [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
