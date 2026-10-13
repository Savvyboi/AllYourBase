# Phase 1 implementation verification

Revalidated on Windows on 2026-10-14 with Python 3.12.6 and the committed uv
lockfile. The interrupted Phase 1 work was recovered from its cloud chat before
these local checks; its original cloud run passed 121 tests.

| Check | Result |
| --- | --- |
| `uv run --extra access python scripts/check.py` (Windows equivalent of `make check`) | Pass |
| Ruff lint and format | Pass |
| Strict mypy | Pass across 48 source/test files |
| pytest/Hypothesis with the access extra | 129 tests pass |
| Generated radar evalscript executed in Node | Pass: samples, empty/ambiguous looks and orbit metadata |
| Catalogue and settings validation | Pass; production catalogue remains empty |
| JSON Schema consistency | Pass |
| Public collection diagnostics | Earth Search, CDSE optical and Planetary Computer RTC reachable |
| Public sample asset inspection | Optical aliases verified; Earth Search B08 is `nir` at 10 m |
| CDSE authenticated access | Not run; credentials missing |

Offline tests cover compressed responses, retry limits, redaction, pagination,
duplicate scenes, ISO-week endpoints, antimeridian query splitting, native optical
windows (including Windows drive paths), northern/southern/polar grids, both radar
polarisation pairs, malformed response/mask handling, correct and
incorrect scene IDs, shifted radar grids, unknown charges and budget locking.
End-to-end mocked spikes preserve successes and failures in eight-week tables.

The three proposed 4 km test AOIs are unapproved and stay outside the production
catalogue. Their point records come from the pinned OurAirports snapshot named
inside the GeoJSON. The snapshot's SHA-256 was checked against that exact commit.

No live AOI acquisition table, optical/radar chip or radar charge was measured.
This is verification of the implemented access paths, not completion of Phase 1's
multinational acceptance criteria. Keep the PR in draft until those measurements
and the final provider decision are recorded.
