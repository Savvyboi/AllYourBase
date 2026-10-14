# AllYourBase build plan

Updated 2026-10-14 (Europe/Helsinki).

AllYourBase will run Sentinel processing in Google Colab and publish reviewed results to
a separate static GitHub Pages repository. Phase 0 is merged. Phase 1 has verified
primary optical, CDSE optical fallback and radar access for the approved Russian
pilot. Phase 1 is merged in PR #2. No activity analysis or website
has been implemented.

The [Word plan snapshot](build-plan.docx) preserves the original detailed design
and earlier progress. It predates the passing Colab fallback run; its Windows
renderer is unavailable, so it was left unchanged. This Markdown file records
current implementation status and the next work. The repository
[AGENTS.md](../AGENTS.md) embeds the roadmap and working rules for future agents.

## Verified progress

| Area | Status and evidence |
| --- | --- |
| Phase 0 foundation | Complete and merged in [PR #1](https://github.com/Savvyboi/AllYourBase/pull/1). Python 3.12/uv, CLI, strict settings/catalogue models, six JSON Schemas, offline validation and UTC ISO-week planning. |
| Phase 1 provider access | Pilot access acceptance passes in [PR #2](https://github.com/Savvyboi/AllYourBase/pull/2). Discovery, native optical windows, terrain-corrected radar windows, explicit failure reports, retries, local credentials and usage accounting. |
| Approved test scope | Chkalovskiy, Engels and Olenya; 4 km windows derived from pinned OurAirports records. Owner approved the locations and live checks on 2026-10-14, replacing the original three-country spike. |
| Live evidence | 2026-W34 through W41; 96 site/provider/week rows across four catalogues contain acquisitions. Earth Search and CDSE optical each produced 21 verified band TIFFs; CDSE radar produced three validated four-band 10 m TIFFs. The Colab fallback also produced 24 successful site/week rows. |
| Measured radar usage | Each successful 401 by 401 radar Process call reported 3.067035675 PU. Three successful chips used 9.201107025 PU plus 0.06 catalogue PU. The entire debug/test session used 21.469249725 Process PU plus 0.18 catalogue PU. |
| Verification | 192 pytest/Hypothesis tests, Ruff, formatting, strict mypy, settings/catalogue/schema checks and all five pre-commit hooks pass. Generated radar JavaScript was executed against representative samples and metadata. |
| Phase 2 workflow | Immutable snapshots, source-reuse enforcement, DuckDB staging, matching/geocoding proposals, permitted PDF page/rule extraction and a local catalogue review UI/CLI are implemented. 31 live OurAirports/Wikidata site records; unchanged snapshots produce zero new proposals. Multi-source review and separate evidence-readiness checks pass. Production catalogue remains empty. |
| Phase 3 prototypes | Radar request grids and antimeridian discovery splitting exist and have synthetic coverage. Shared preprocessing, persistent chip cache, masks, alignment and indicators are not implemented. |

Detailed evidence: [implementation verification](phase-1-validation.md),
[live tables and local run IDs](phase-1-live-validation.md) and
[provider decision](adr/0002-provider-selection.md).

Catalogue item counts are not aircraft counts or unique satellite overpasses.
Optical window reads preserve native grids and do not yet establish cloud-free
observations. The approved windows are access-test areas, not surveyed base
boundaries or a production monitoring catalogue.

## Immediate next steps

1. Phase 1 is merged. Preserve the existing access evidence.
2. Continue [Phase 2 production review](phase-2.md). Gather permitted geometry and
   dated unit/equipment sources; review at least ten Russian sites across the
   required site types. The workflow and a 31-record discovery packet are implemented;
   source points/hints do not establish production sites, zones or military unit/equipment claims.
3. Continue processing through Colab as selected by the owner. Its Phase 1 access
   notebook is exercised; full processing still needs a resumable results store,
   VM-local working DB, checkpoint sync and a shared one-writer lock.

Earth Search is the measured optical primary and CDSE Sentinel Hub the measured
radar primary for this pilot. CDSE optical fallback pixels are verified at all
three approved areas.
Planetary Computer RTC has metadata coverage in this sample, but its pixel
retrieval/signing is unimplemented and its pipeline fallback remains disabled.
GDAL transfer bytes and range-request counts are explicitly unknown. Account
quota assumptions and later performance targets remain provisional.

## Ordered roadmap

### Phase 0 Foundation complete

- [x] Repository layout, Python/uv environment, lint/type/test tools and pre-commit.
- [x] Strict settings and catalogue models; six generated JSON Schemas.
- [x] Catalogue integrity checks and UTC work planning.
- [x] Required CLI command names; unimplemented actions fail without side effects.

Acceptance passed in PR #1. `allyourbase` is the primary CLI;
`basewatch` is the compatibility alias.

### Phase 1 Data access acceptance passes

- [x] Approved Russian test windows and eight-week discovery from all four providers.
- [x] Earth Search seven-band AOI reads at all three sites.
- [x] CDSE orthorectified, terrain-flattened linear gamma-zero radar windows with
  both polarisations, shadowMask and dataMask.
- [x] Scene/grid/mask validation, bounded catalogue retries, redacted diagnostics,
  explicit gaps and measured radar usage.
- [x] CDSE optical window reads using separate S3 credentials in Colab; all 21 files independently revalidated.
- [x] Record fallback evidence and finalize provider choice in ADR 0002.
- [x] PR #2 merged at f700c1a on 2026-10-14.

Acceptance: reproducible per-site/provider/week acquisition tables, optical
reads from Earth Search and CDSE, valid radar chip metadata, measured costs and
an evidence-based primary/fallback decision. The owner replaced multinational
live testing with this Russian pilot; synthetic global-geometry checks remain.

### Phase 2 Catalogue source ingestion and taxonomy

- [x] Models and JSON Schemas for sites, units, equipment, sources and taxonomy.
- [x] OSM/Geofabrik, Wikidata, OurAirports and GeoNames import connectors with
  immutable source snapshots and manifests.
- [x] PDF extraction with page references for permitted reference-class sources.
- [x] DuckDB staging, name/designation normalization, geocoding, deduplication,
  matching and link proposals.
- [x] Local catalogue review queue; accepted edits written with provenance and
  rejected proposals remembered.
- [ ] At least 10 reviewed Russian production sites across airbases, naval bases
  and garrisons, with sourced unit/equipment links and reviewed zones.

Workflow checks and live OurAirports/Wikidata imports pass; native osmium,
GeoNames and Geofabrik remain unverified. Basic Cyrillic matching keys are
implemented; full contextual BGN/PCGN transliteration is deferred. See [Phase 2 evidence and limitations](phase-2.md).

Acceptance: `catalogue check` passes; every fact traces to a snapshot or cited
page; unchanged ingestion creates no new proposals; a preview map displays zones
correctly. Empty contracts and test AOIs do not satisfy this phase.

### Phase 3 Preprocessing and indicators

- [ ] Finish shared 10 m grids for UTM north/south, polar areas and antimeridian AOIs.
- [ ] Persistent compressed chip cache, optical resampling/SCL masks, radar masks,
  alignment checks and explicit quality gaps.
- [ ] Radar bright-target/occupancy/backscatter-change indicators; optical blob,
  disturbance, snow-track, burn and persistent-change indicators.
- [ ] Synthetic correctness tests and small golden fixtures; track algo_version.

Radar grids and discovery splitting are prototypes, not completion of shared
preprocessing. Acceptance target: `run --site X --week W` under five minutes cold
and under one minute from cache. These timings have not been measured.

### Phase 4 Backfill and baselines

- [ ] Resumable historical processing from 2024-W01 with catch-up and late-scene checks.
- [ ] Baseline store with seasonal windows, observation counts and warm-up handling.

Acceptance: at least 52 weeks of history per pilot site and a data-gap report.
Existing `backfill --plan` only plans work.

### Phase 5 Scoring events images and review

- [ ] Explainable levels, direction, confidence, drivers and event merging.
- [ ] Radar image pairs/change composites and optical pairs when quality allows.
- [ ] Local review app bound to 127.0.0.1, persistent decisions and publication policy.

Acceptance: Elevated/High events have images no larger than 40 KB each, and
review decisions survive restart. Scoring must not infer normal activity from
missing data or claim equipment identity at Sentinel resolution.

### Phase 6 Static website

- [ ] Hugo overview, site, unit, equipment, tag, country, event, digest and methods pages.
- [ ] Taxonomy metadata, facet index, Pagefind, maps and charts.
- [ ] Schema/link checks and browser smoke tests.

Acceptance target: build under two minutes for 100 sites, usable at 375 px,
no console errors and no broken internal links. Website destination is undecided.

### Phase 7 Publishing and operations

- [ ] Export reviewed results, build Hugo/Pagefind, validate an output allow-list,
  link/schema checks and file/site size budgets.
- [ ] Set up the separate site repository and scoped publication credentials.
- [ ] Scheduler, notifications, backups, locks, catch-up and full usage accounting.

The spike's JSON radar reservation ledger is a prototype; DuckDB results and
operational accounting remain future work. Acceptance: two consecutive scheduled
weeks run unattended and publishing succeeds after review. Decide publication
delay, final policy, exclusions and hosting account before activation.

### Phase 7a Selected Colab processing runtime

- [ ] Launcher notebook, Drive archives, secrets, VM-local working database,
  checkpoints, atomic sync and a shared one-writer lock.
- [ ] Optional notebook review UI.

The owner selected Colab on 2026-10-14. A thin Phase 1 optical access notebook
has successfully installed a SHA-256-pinned source bundle with locked
dependencies, loaded S3 secrets and archived verified optical evidence. Full processing integration does not
exist yet; the VM-local results store, checkpoints and shared lock are pending. Acceptance:
interrupted backfill resumes without duplicate/corrupt results and local/Colab
writers cannot run together. Verify current runtime entitlements before use.

### Phase 8 Another country or climate

- [ ] Add a country through source ingestion, reviewed catalogue/configuration
  records and the same provider/analysis interfaces.

Acceptance: no country-specific code changes and all global edge-case tests pass.
Southern-hemisphere live validation is deferred from the current Russian pilot.

### Phase 9 Validation and tuning

- [ ] Backtest against independently sourced, dated reported events.
- [ ] Tune thresholds and publish methods, confirmation rates, false events per
  site-year and no-data fractions.

Acceptance: documented confirmation and false-event rates per site. Keep old
outputs when algo_version changes; do not treat test downloads as detections.

### Phase 10 Optional machine learning

- [ ] Evaluate an Isolation Forest second opinion only after the rule pipeline works.
- [ ] Consider supervised models only when reviewed labels are sufficient.

This phase is optional and follows the validated rule-based system.

## Working boundaries

Keep the original local architecture: code/catalogue repository, separate local
data workspace, separate eventual publication repository. Keep provider choices,
thresholds and country/site facts in configuration or sourced catalogue records.
No personal data belongs in the catalogue. Import only sources permitted for
automation; reference/manual sources retain their reuse restrictions.

Preserve provider and scene provenance, algo_version and processing timestamps.
Keep credentials, raw imagery, databases and the full runtime workspace outside
Git. Published outputs later need review, attribution and size/schema/link checks.
Current publication policy defaults to reviewed_only; delay_days 0 is provisional,
not an instruction to publish. New user instructions override historical scope
and should be reflected in this plan, AGENTS.md and the relevant ADR.
