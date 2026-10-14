# Phase 1 implementation verification

Revalidated on Windows on 2026-10-14 with Python 3.12.6 and the committed uv
lockfile. The interrupted Phase 1 work was recovered from its cloud chat before
these local checks; its original cloud run passed 121 tests.

| Check | Result |
| --- | --- |
| `uv run --extra access python scripts/check.py` (Windows equivalent of `make check`) | Pass |
| Ruff lint and format | Pass |
| Strict mypy | Pass across 50 source/test files |
| pytest/Hypothesis with the access extra | 147 tests pass |
| Generated radar evalscript executed in Node | Pass: samples, empty/ambiguous looks and orbit metadata |
| Catalogue and settings validation | Pass; production catalogue remains empty |
| JSON Schema consistency | Pass |
| Public collection diagnostics | Earth Search, CDSE optical and Planetary Computer RTC reachable |
| Public sample asset inspection | Optical aliases verified; Earth Search B08 is `nir` at 10 m |
| CDSE authenticated access | Colab optical fallback and radar window reads pass at all three approved sites |
| Downloaded Colab evidence | 21 files independently revalidated; source manifest and runtime settings match |

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
Actual radar request costs are measured. The CDSE optical fallback also passes
from Colab, with 21 files revalidated locally. Phase 1 access acceptance passes
and PR #2 can proceed to code review. The production catalogue is empty and no
activity assessment or publication has been made.


## Colab preparation and optical evidence verification

The owner selected Colab for processing. The bounded Phase 1 notebook is prepared
with a matching hashed source bundle, locked Python 3.12 environment, Colab Secrets,
CLI calls and a completed evidence archive. Notebook cells have no stored outputs.
A real Colab execution and authenticated CDSE optical check now pass. The
owner-supplied archive contains 21 valid TIFFs, 24 successful site/week rows and
a source manifest matching the supplied bundle. Runtime settings differ only in
runtime profile/workspace. Local verification exactly matches the Colab summary.

Synthetic validation tests reject missing/duplicate bands, changed hashes,
wrong scenes or asset references, unsafe paths, mismatched AOIs, unfinished runs,
provider failures, missing areas, shifted grids, empty pixels and invalid SCL.
The verifier also passed on the preserved Earth Search optical run: three sites,
21 band files, with no new network or imagery requests. `providers doctor` reports
S3 pixel credential presence separately from anonymous metadata readiness. Colab
keys remain in Colab Secrets; local absence does not invalidate the measured run.

The Word plan remains an earlier snapshot: the Windows renderer fails because
LibreOffice is unavailable. Its source was left unchanged; current status is in
AGENTS.md, the Markdown build plan, this verification record and ADR 0002.
