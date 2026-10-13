# Phase 1 implementation verification

Revalidated on Windows on 2026-10-14 with Python 3.12.6 and the committed uv
lockfile. The interrupted Phase 1 work was recovered from its cloud chat before
these local checks; its original cloud run passed 121 tests.

| Check | Result |
| --- | --- |
| `uv run --extra access python scripts/check.py` (Windows equivalent of `make check`) | Pass |
| Ruff lint and format | Pass |
| Strict mypy | Pass across 48 source/test files |
| pytest/Hypothesis with the access extra | 131 tests pass |
| Generated radar evalscript executed in Node | Pass: samples, empty/ambiguous looks and orbit metadata |
| Catalogue and settings validation | Pass; production catalogue remains empty |
| JSON Schema consistency | Pass |
| Public collection diagnostics | Earth Search, CDSE optical and Planetary Computer RTC reachable |
| Public sample asset inspection | Optical aliases verified; Earth Search B08 is `nir` at 10 m |
| CDSE authenticated access | Catalogue and radar window reads pass at all three approved sites |

Offline tests cover compressed responses, retry limits, redaction, pagination,
duplicate scenes, ISO-week endpoints, antimeridian query splitting, native optical
windows (including Windows drive paths), northern/southern/polar grids, both radar
polarisation pairs, malformed response/mask handling, correct and
incorrect scene IDs, shifted radar grids, unknown charges and budget locking.
End-to-end mocked spikes preserve successes and failures in eight-week tables.

The owner approved three Russian airbase test areas on 2026-10-14, replacing the
original Finland/Australia proposals. Their point records come from the pinned
OurAirports snapshot named inside the GeoJSON; its SHA-256 was checked.

Live evidence is recorded in `docs/phase-1-live-validation.md`: all four catalogues
have items for every site/week, seven-band Earth Search window reads pass for all
three sites, and three CDSE radar chips pass grid, source and mask validation.
Actual radar request costs are measured. CDSE optical fallback reads still need
separate S3 keys, so the Phase 1 PR remains in draft. The production catalogue is
empty and no activity assessment or publication has been made.
