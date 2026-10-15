# Superseded agent guide

Historical record. Current instructions are in [AGENTS.md](../AGENTS.md).

# AllYourBase agent guide and build plan

Updated 2026-10-15 (Europe/Helsinki), after Phase 2 structured review bundle preparation.
This file applies to the whole repository.

## Purpose and authoritative records

Build a review-first Sentinel-1/Sentinel-2 pipeline with Google Colab processing,
a human-curated, sourced catalogue and a later static Hugo/GitHub Pages website. Current user
instructions take precedence over historical documents and this guide.

Read [the active build plan](build-plan.md) for detailed acceptance criteria
and [the Word plan snapshot](build-plan.docx) for the full original design.
The Word snapshot predates the successful Colab fallback check; the Markdown
plan and this guide contain current acceptance status. The Windows Word renderer
is unavailable, so do not claim that snapshot has been updated or re-rendered. Original design proposals are not completed
features or authorization to deploy, publish, merge, scrape restricted sources,
or change credentials. Verify actual repository state before acting.

Use [Phase 1 setup](phase-1.md),
[live measurements](phase-1-live-validation.md),
[implementation verification](phase-1-validation.md) and
[ADR 0002](adr/0002-provider-selection.md) for current provider evidence.

## Current implementation

- Phase 0 is complete and merged in PR #1. The Python 3.12/uv foundation, strict
  models, six JSON Schemas, catalogue checking, UTC ISO-week planning and CLI
  command surface are implemented.
- PR #2 is merged at f700c1a. Earth Search optical, CDSE
  optical fallback and CDSE Sentinel Hub radar access pass for the approved pilot.
- The Colab optical run 20261013T234356Z-1737c37ff296467c979cd05e9ab00b63
  produced 21 verified CDSE band TIFFs and 24 successful site/week rows. Local
  revalidation agrees with Colab, and its source manifest matches the delivered
  bundle. Credential setup is complete in Colab; secret values were not imported.
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
- Phase 2 implementation is merged: [PR #3](https://github.com/Savvyboi/AllYourBase/pull/3)
  at 2d8135f added source ingestion and review;
  [PR #4](https://github.com/Savvyboi/AllYourBase/pull/4) at b97c9c6 added supporting
  evidence and readiness checks; [PR #5](https://github.com/Savvyboi/AllYourBase/pull/5)
  at 378ee08 added native Overpass geometry and the mixed-pilot review packet.
  Immutable snapshots, permission-gated connectors/PDF extraction, DuckDB staging,
  candidate matching and the loopback review app are implemented, including
  validated, recoverable YAML/GeoJSON acceptance. See [Phase 2](phase-2.md)
  and [ADR 0003](adr/0003-catalogue-ingestion.md).
  Live OurAirports/Wikidata imports produced 31 site records; repeating retained
  snapshots produces zero new proposals. All source records remain unapproved;
  production catalogue acceptance is still open.
- The owner confirmed the mix of all Russian military base types on 2026-10-14.
  Native OSM discovery retained 18,568 tagged features (not a count of bases).
  The first mixed review packet has ten source footprints: four airbases, three
  naval facilities and three ground-garrison candidates. Its 77 zone/mask
  associations include 72 contained polygons and five boundary conflicts.
  See [mixed-pilot evidence](phase-2-mixed-pilot.md) and the
  [selection](proposals/rus-mixed-pilot.yaml). This is the first review batch;
  the broader scope is not an exhaustive completed inventory. All ten candidates
  have owner approval of the displayed proposals; status/claim dates, supported
  zone roles and dated historical unit/equipment evidence are still open. The
  initial queue had 185 record proposals: 41 site records,
  80 zone candidates and 64 masks, with three superseded versions retained.
  Site records may duplicate physical facilities. Repeat finalized footprint and
  zone imports produce zero new proposals. The owner approved all ten displayed
  candidate identities/classifications and source geometry on 2026-10-15; the
  dated source gaps and containment conflicts are separate validation work.
- Phase 2 packet evidence continuation pins footprint and zone queue links to
  exact verified snapshots, retains active accepted supporting records and flags
  rejected/superseded/unlinked evidence. Packet format is now version 2, with a
  per-candidate `review-gaps.json` and visible identity/zone links and review tasks.
  The refreshed external packet is under `review/mixed-pilot-evidence-20261015/`;
  all 77 associations have exact staged evidence. Five boundary conflicts across
  two candidates and four compatible-zone gaps remain. Production decisions and
  the original packet/snapshots are unchanged.
- PR #6 is merged at 130c81a. The owner explicitly approved all displayed
  proposals on 2026-10-15. The exact packet and its SHA-256 are archived under
  `review/packet-approvals/151d4e72412905a9b3d6168f91695f7194068d3b667063f83a5ca9d83c8660dd/`.
  `catalogue approve-packet` records this approval durably and idempotently;
  regenerated matching packets clear owner-review tasks. Changed identities,
  geometry, roles or source versions do not inherit the recorded approval.
  Do not ask the owner to approve the unchanged displayed packet again.
  Approval does not supply absent status/claim dates or historical evidence,
  repair crossing polygons, or create production catalogue records.
- A bounded live GeoNames cities5000 import retained 2,759 Russian populated
  places, with zero new proposals on first/repeat staging. Its source spec is
  `config/sources/geonames-rus-cities5000.yaml`; exact manifest/hash and validation
  are outside Git under `review/geonames-cities5000-20261015/`. This is a partial
  populated-place gazetteer, not an inventory of facilities or deployments.
  Re-staging the same verified current snapshot now skips parsing and row writes;
  retained payloads are still hashed and old snapshot heads can still be restored.
- PR #7 is merged at 364d8c4. Draft PR #8 is open on
  `codex/phase-2-geometry-preparation`. `catalogue prepare-geometry` reconstructs
  owner-approved source packets against retained snapshots and eligible evidence,
  and prepares contained primary-role zones without changing source geometry.
  The external `review/mixed-pilot-geometry-20261015/` contains 47 zones for six
  candidates and a preview at http://127.0.0.1:8770/preview.html. All five crossing
  source features are water masks with no area overlap with any selected zone;
  they are explicitly deferred, not boundary repairs or production masks. Four
  candidates still lack supported primary zones. The original approval, source
  packet and five source-boundary conflicts are preserved. See
  [geometry preparation](phase-2-geometry-preparation.md).
- Two pending manually curated NTI historical records retain a reported
  2000-10-18 Engels/division/Tu-160 association; original references and modern
  footprint correspondence remain unverified. No current claim or production
  decision is inferred. Repeat staging creates zero proposals. The queue now has
  187 active record proposals and three retained superseded versions.
- Draft PR #8 now also includes `catalogue prepare-bundles`: ten incomplete
  source-pinned bundle drafts, exact evidence sidecars and field/evidence worklists
  under external `review/mixed-pilot-bundles-20261015/`. Six candidates retain the
  existing 47 zones; four zone gaps remain. Status, factual dates and sensor
  choices are omitted, and historical notes are not automatically attached.
  Repeat output is identical; regeneration refuses to overwrite review edits.
  Generic containment checks need no invented metadata. See
  [bundle preparation](phase-2-bundle-preparation.md).
- The two pending NTI notes match their retained snapshot and semantic hashes.
  Bibliography inspection dates reference [19] to September 2000, before the
  reported October announcement. Neither original reference was retrieved;
  modern footprint correspondence remains unverified. Full checks are external
  under `review/bundle-preparation-20261015/`. No new imports or decisions.
- Last verified code checks: 254 pytest/Hypothesis tests, Ruff, format, strict
  mypy, settings/catalogue/schema checks and all five pre-commit hooks pass.
  Browser QA covered all ten previews, search, layers and queue links; desktop
  and 375 px mobile checks found no JavaScript errors or horizontal overflow.
- Production catalogue has zero sites, units, equipment and sources; readiness
  remains false. No production proposal was accepted or rejected. The approved
  Phase 1 access windows are separate from production geometry and contain no
  established unit/equipment claims. No new Sentinel requests were made for the
  mixed packet.
- Package version is 0.3.0; algo_version is 0.0.0 because analysis is not implemented.
  run/backfill execution, scoring, event review, Hugo and publishing remain reserved.

## Immediate continuation

1. Preserve the merged Phase 1 and Phase 2 evidence. Do not repeat imagery
   requests merely to verify documentation, or start Phase 3 as if catalogue
   acceptance were complete.
2. Continue review of the existing ten-candidate mixed batch in the external
   sibling workspace `../phase2-data`. Its packet is under
   `review/mixed-pilot/`: `review-packet.md`, `packet.json`, `preview.html` and
   `source-polygons.geojson`. The national inventory CSV supports later expansion.
   Use the refreshed packet under `review/mixed-pilot-evidence-20261015/`, including
   its `review-gaps.json`. Its preview is http://127.0.0.1:8769/preview.html and the
   review queue is http://127.0.0.1:8768; restart those services if needed. The preview
   is read-only and now displays the owner's 2026-10-15 approval of the existing
   candidate identities/classifications and source geometry. Preserve that decision;
   source evidence and valid production contracts remain separate requirements.
3. Owner review of the displayed batch is complete. Reuse the prepared geometry
   under `review/mixed-pilot-geometry-20261015/`; six candidates have 47 usable
   contained source zones. Resolve the four remaining zone-role gaps and source
   evidence before production acceptance. The five crossing water polygons do
   not overlap the prepared zones and are deferred, with source polygons intact.
   Original source caveats remain:
   Gromovo is an unnamed parcel near two Wikidata records; Gadzhiyevo has an
   explicitly estimated outline. Olenya has three crossing zone/mask polygons
   and Gadzhiyevo has two. Novorossiysk lacks a contained pier/anchorage candidate;
   one ground parcel has no mapped zone, and parking tags do not establish
   military vehicle use. Inspect location, source scope and duplicates, including
   whether separately mapped parcels belong to one facility. Source points and
   approved access-test squares are not production boundaries.
4. Use the structured drafts under `review/mixed-pilot-bundles-20261015/` and
   their per-candidate validation/evidence worklists. Copy files before editing;
   regeneration protects edited output. Obtain permitted sources for status/claim
   dates and dated historical unit/equipment evidence, choose processing sensors,
   then complete and validate the structured review bundles. Reuse
   existing owner approval for unchanged displayed content.
   Ground-unit labels alone do not establish an association or current deployment.
   Re-run `catalogue readiness --country RUS --minimum-sites 10 --require-type airbase --require-type naval_base --require-type garrison`
   after production acceptance. Keep Phase 2 incomplete until ten or more
   reviewed production sites, all required types, approved zones and retained
   provenance with overlapping dated unit/equipment links satisfy acceptance.
5. Google Colab is the selected processing runtime. The thin Phase 1 notebook has
   been exercised successfully. Full processing still needs the resumable results
   store, VM-local DB, checkpoint sync and shared one-writer lock. Keep secret
   values in Colab Secrets, with notebook access enabled; never ask for values
   in chat or print them. The S3 reader consumes environment variables and .env
   is not loaded automatically.

Earth Search is the measured optical primary; CDSE Sentinel Hub is the measured
radar primary. CDSE optical fallback pixels are verified for these three areas. Planetary Computer
RTC metadata coverage was observed in this pilot, but pixel retrieval/signing
is unimplemented and its pipeline fallback stays disabled. GDAL HTTP transfer
bytes and range-request counts remain unknown.

## Build plan and acceptance sequence

Implement milestones in order and use a separate reviewable PR per phase.
Phases 0–1 and Phase 2 implementation PRs #3–#5 are merged. Phase 2 production
acceptance remains open.

| Phase | Current status | Next work and acceptance |
| --- | --- | --- |
| 0 Foundation | Complete, merged | Preserve strict contracts, schema generation, catalogue integrity and planning without side effects. Required CLI commands and checks already pass. |
| 1 Data access | Complete, merged in PR #2 | Eight-week provider tables, Earth Search/CDSE optical windows, valid radar chips, measured radar usage and provider choice are verified. Preserve measured evidence. |
| 2 Catalogue and ingestion | Workflow and owner approval merged; geometry and incomplete bundle drafts prepared; zero production sites | Complete four primary-zone gaps and sourced status/historical links, then assemble validated review bundles. Acceptance: 10+ reviewed Russian production sites across airbase, naval_base and garrison, with sourced dated links, idempotent ingestion and correct approved zone preview; milestone readiness must pass. |
| 3 Preprocessing and indicators | Radar grid/discovery prototypes only | Finish global grids, resampling, persistent cache, masks, alignment and all configured indicators. Acceptance: synthetic/golden correctness and measured run timing under five minutes cold, one minute cached. Targets are not achieved claims. |
| 4 Backfill and baselines | Not implemented | Resumable processing from 2024-W01, catch-up, late scenes, seasonal baselines and warm-up. Acceptance: 52+ weeks per pilot site plus data-gap report. Planning is not processing. |
| 5 Scoring events images review | Not implemented | Explainable levels/direction/confidence/drivers, merging, image pairs and durable local review decisions. Acceptance: event images <=40 KB and decisions survive restart. |
| 6 Website | Not implemented | Hugo pages/taxonomies, facet index, Pagefind, maps/charts and schema/link/browser checks. Acceptance: 100-site build under two minutes, 375 px usability, no console errors/broken links. |
| 7 Publish and operations | Not implemented; spike ledger prototype exists | Reviewed export, separate site repo, scoped credentials, allow-list and size/schema/link checks, scheduler, locks, catch-up, notifications, backup and full usage accounting. Acceptance: two unattended scheduled weeks and publishing after review. |
| 7a Colab | Selected runtime; Phase 1 access notebook exercised | Full processing still needs VM-local DB, checkpoint/atomic sync and one-writer lock. Acceptance: clean resume after interruption and no overlapping writers. |
| 8 Another country | Deferred beyond Russian pilot | Add a country/climate through sourced catalogue/config records. Acceptance: no country-specific algorithm code changes and global edge-case tests pass. |
| 9 Validation and tuning | Not implemented | Sourced event backtests, threshold tuning and methods. Acceptance: documented confirmation rates, false events per site-year and no-data fractions; version and retain old results. |
| 10 Machine learning | Optional, not implemented | Isolation Forest second opinion; supervised work only after sufficient reviewed labels and a validated rule-based pipeline. |

Keep catalogue proposals/decisions and raw sources in the external workspace. Local
workflow locking and recoverable acceptance are implemented; shared Colab/Drive
checkpointing and locks remain Phase 7a work. Native Overpass OSM import, geometry
preview and the bounded live GeoNames cities5000 import pass. Native osmium and
live Geofabrik/full-country gazetteer imports remain unverified. The basic
transliteration is not full BGN/PCGN.

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
  local databases, source snapshots and full runtime reports outside Git. Colab
  working state stays on the VM; Drive receives completed evidence archives. Publish
  only reviewed, validated outputs to the eventual separate site repository.
- Use allyourbase as package/CLI; basewatch remains a compatibility alias.
  ALLYOURBASE_HOME overrides BASEWATCH_HOME and the configured external workspace.
- Resolve all workspace paths through Project. Never allow a data workspace inside
  the code repository. This development session uses sibling phase1-data for
  provider evidence and phase2-data for snapshots, the staging DB and review
  packets; do not hard-code a developer's absolute path into package code.
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

Install the locked environment with uv sync --locked --extra access --extra ingestion --extra review.
For implementation changes, run:

```sh
uv run --extra access --extra ingestion --extra review python scripts/check.py
uv run --extra access --extra ingestion --extra review pre-commit run --all-files
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
