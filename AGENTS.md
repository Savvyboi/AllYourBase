# AllYourBase agent guide and build plan

Updated 2026-10-14 (Europe/Helsinki). This file applies to the whole repository.

## Purpose and authoritative records

Build a local, review-first Sentinel-1/Sentinel-2 pipeline with a human-curated,
sourced catalogue and a later static Hugo/GitHub Pages website. Current user
instructions take precedence over historical documents and this guide.

Read [the active build plan](docs/build-plan.md) for detailed acceptance criteria
and [the updated Word plan](docs/build-plan.docx) for the full original design
with current progress annotations. Original design proposals are not completed
features or authorization to deploy, publish, merge, scrape restricted sources,
or change credentials. Verify actual repository state before acting.

Use [Phase 1 setup](docs/phase-1.md),
[live measurements](docs/phase-1-live-validation.md),
[implementation verification](docs/phase-1-validation.md) and
[ADR 0002](docs/adr/0002-provider-selection.md) for current provider evidence.

## Current implementation

- Phase 0 is complete and merged in PR #1. The Python 3.12/uv foundation, strict
  models, six JSON Schemas, catalogue checking, UTC ISO-week planning and CLI
  command surface are implemented.
- PR #2 contains Phase 1 and remains draft. Earth Search optical and CDSE
  Sentinel Hub radar access pass for the approved Russian pilot.
- The owner approved Chkalovskiy, Engels and Olenya as 4 km test windows on
  2026-10-14 and explicitly authorized the live access checks. This replaced the
  original three-country spike. Do not request that approval again for the same
  scope; new/replacement areas still need review.
- 2026-W34 through W41 produced 96 site/provider/week rows with acquisitions.
  Optical reads produced 21 local band TIFFs; radar reads produced three
  validated four-band, 401 by 401, 10 m TIFFs. Item counts are not aircraft counts,
  clear-sky observations or unique satellite overpasses.
- Successful radar Process calls each reported 3.067035675 PU. Charges for
  failed/debug attempts were retained. These are measurements for these requests,
  not an account-wide quota or a guaranteed future cost.
- Last verified code checks: 131 pytest/Hypothesis tests, Ruff, format, strict
  mypy, settings/catalogue/schema checks and all five pre-commit hooks pass.
- Production catalogue is empty. The approved test windows are separate from
  production geometry and contain no established unit/equipment claims.
- Package version is 0.2.0; algo_version is 0.0.0 because analysis is not implemented.
  run/backfill execution, scoring, review UI, Hugo and publishing remain reserved.

## Immediate continuation

1. Finish the CDSE optical fallback check. OAuth/keychain setup works; separate
   CDSE_S3_ACCESS_KEY_ID and CDSE_S3_SECRET_ACCESS_KEY are missing. The current S3
   reader uses environment variables. Never ask for secret values in chat or print
   them. .env files are ignored but not loaded automatically.
2. Run a bounded cdse_stac optical spike for all three approved areas using
   --pixels. Keep reports/imagery in the external workspace and verify seven
   band windows, georeferencing and hashes. Preserve existing evidence.
3. Update ADR 0002 and validation docs with actual fallback results. Keep PR #2
   in draft until this acceptance check passes, then prepare it for review.
4. Continue with Phase 2 source ingestion and catalogue review after Phase 1
   acceptance. Do not confuse the existing schemas with a completed catalogue.

Earth Search is the measured optical primary; CDSE Sentinel Hub is the measured
radar primary. CDSE optical fallback pixels remain unverified. Planetary Computer
RTC metadata coverage was observed in this pilot, but pixel retrieval/signing
is unimplemented and its pipeline fallback stays disabled. GDAL HTTP transfer
bytes and range-request counts remain unknown.

## Build plan and acceptance sequence

Implement milestones in order and use a separate reviewable PR per phase.
The current phase is Phase 1; its remaining fallback check is the first priority.

| Phase | Current status | Next work and acceptance |
| --- | --- | --- |
| 0 Foundation | Complete, merged | Preserve strict contracts, schema generation, catalogue integrity and planning without side effects. Required CLI commands and checks already pass. |
| 1 Data access | Primary providers verified; draft | Finish CDSE optical S3 reads. Acceptance: eight-week provider tables, Earth Search/CDSE optical windows, valid radar chips, measured usage and documented primary/fallback choice for the approved Russian pilot. |
| 2 Catalogue and ingestion | Contracts/schemas done; ingestion not started | Import OSM/Wikidata/OurAirports/GeoNames with immutable manifests; extract permitted PDFs; add DuckDB staging, normalization, geocoding, matching and proposals; build review queue. Acceptance: 10+ reviewed Russian production sites with sourced links, idempotent ingestion and correct zone preview. |
| 3 Preprocessing and indicators | Radar grid/discovery prototypes only | Finish global grids, resampling, persistent cache, masks, alignment and all configured indicators. Acceptance: synthetic/golden correctness and measured run timing under five minutes cold, one minute cached. Targets are not achieved claims. |
| 4 Backfill and baselines | Not implemented | Resumable processing from 2024-W01, catch-up, late scenes, seasonal baselines and warm-up. Acceptance: 52+ weeks per pilot site plus data-gap report. Planning is not processing. |
| 5 Scoring events images review | Not implemented | Explainable levels/direction/confidence/drivers, merging, image pairs and durable local review decisions. Acceptance: event images <=40 KB and decisions survive restart. |
| 6 Website | Not implemented | Hugo pages/taxonomies, facet index, Pagefind, maps/charts and schema/link/browser checks. Acceptance: 100-site build under two minutes, 375 px usability, no console errors/broken links. |
| 7 Publish and operations | Not implemented; spike ledger prototype exists | Reviewed export, separate site repo, scoped credentials, allow-list and size/schema/link checks, scheduler, locks, catch-up, notifications, backup and full usage accounting. Acceptance: two unattended scheduled weeks and publishing after review. |
| 7a Colab | Optional, not implemented | Thin notebook, Drive archives, secrets, VM-local DB, checkpoint/atomic sync and one-writer lock. Acceptance: clean resume after interruption and no overlapping writers. |
| 8 Another country | Deferred beyond Russian pilot | Add a country/climate through sourced catalogue/config records. Acceptance: no country-specific algorithm code changes and global edge-case tests pass. |
| 9 Validation and tuning | Not implemented | Sourced event backtests, threshold tuning and methods. Acceptance: documented confirmation rates, false events per site-year and no-data fractions; version and retain old results. |
| 10 Machine learning | Optional, not implemented | Isolation Forest second opinion; supervised work only after sufficient reviewed labels and a validated rule-based pipeline. |

Phase 2 includes site/unit/equipment/source/taxonomy provenance, dated garrison
and equipment links, reusable source classification and human-approved zones.
Phase 3 includes radar bright-target, ship-occupancy and backscatter-change
indicators plus optical blob, disturbance, snow, burn and persistent-change
indicators. All thresholds remain configurable.

Owner decisions still needed before publication: final production sites/zones and
exclusions, publication delay, final publish policy and destination repository/
account. The three approved access windows do not decide these later questions.

## Architecture and data boundaries

- Keep code and curated catalogue in this repository. Keep bulky data, raw imagery,
  local databases, source snapshots and full runtime reports outside Git. Publish
  only reviewed, validated outputs to the eventual separate site repository.
- Use allyourbase as package/CLI; basewatch remains a compatibility alias.
  ALLYOURBASE_HOME overrides BASEWATCH_HOME and the configured external workspace.
- Resolve all workspace paths through Project. Never allow a data workspace inside
  the code repository. This development session used the sibling phase1-data
  folder; do not hard-code a developer's absolute path into package code.
- Keep country/site names, coordinates, unit/equipment facts and thresholds out of
  algorithms. Use sourced catalogue/configuration data; never invent facts from memory.
- No named individuals or personal data in the catalogue. Keep citations, reuse
  classes, dates, confidence and immutable source manifests. Respect import,
  reference and manual source limits; excluded/leaked sources remain excluded.
- Preserve algo_version, provider, scene IDs and processed_at in outputs.
  Missing data/provider failures are gaps, not normal or elevated activity.
- Sentinel resolution supports aggregate change; it does not establish equipment
  identity, reliable small-target counts, current unit deployments or intent.
- Publication defaults to reviewed_only. delay_days: 0 is provisional and publish
  is inactive. Do not activate publication based on a default value.
- Record design decisions as ADRs and update progress/acceptance records when
  implemented behavior or the owner-approved scope changes.

## Provider implementation notes

Use ProviderClient's discovery/window-read contract. Keep endpoints, collections,
band aliases, request bounds and tuning in config/settings.yaml.

Acquisitions are immutable. Discovery handles half-open UTC windows, pagination,
deduplication and antimeridian query splitting. Optical access currently preserves
native grids; shared preprocessing and harmonized caching belong to Phase 3.

Radar requests use GAMMA0_TERRAIN, orthorectification, COPERNICUS_30, linear
backscatter and both polarisation bands plus masks. Requesting 10 m output does
not turn EW's 25 m source spacing into 10 m source data. Validate provenance,
CRS/transform/dimensions, FLOAT32 bands, finite pixels and binary masks.
Normalize only a terminal .SAFE suffix on both product IDs; retain checksum and
_COG identity. Never accept a genuinely different scene.

Use bounded retries for catalogue reads and redacted diagnostics. Do not blindly
retry charged Process POSTs after ambiguous failures. The atomic/locked JSON
radar budget ledger is a Phase 1 prototype; the future results store is DuckDB.
Actual costs replace reservations; unknown charges remain reserved. No secret
values, bearer tokens, signed URL parameters or raw sensitive response bodies
belong in logs, docs or commits.

## Development and verification

Install the locked environment with uv sync --locked --extra access.
For implementation changes, run:

```sh
uv run --extra access python scripts/check.py
uv run --extra access pre-commit run --all-files
```

The first command is the Windows equivalent of make check. Regenerate schemas
with uv run allyourbase schemas generate when models change. Use synthetic pixels
and non-secret metadata for offline tests; live requests must serve an explicitly
configured check and retain measured costs.

For documentation-only changes, check consistency, links and git diff --check.
Do not rerun imagery requests merely to verify documentation. Render and visually
inspect Word artifacts after edits. Keep their QA PDFs/PNGs outside the repository.

Before committing, inspect the diff and staged paths for credentials, imagery and
workspace files. Never overwrite unrelated user changes. Preserve prior evidence
and reports; keep incomplete milestones visibly incomplete.
