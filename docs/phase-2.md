# Phase 2 catalogue ingestion and review

Updated 2026-10-14 (Europe/Helsinki).

The source-to-review workflow is implemented. Phase 2 acceptance remains open:
the production catalogue is empty, and at least ten Russian sites spanning
airbases, naval bases and garrisons still need human-reviewed geometry and sourced,
dated unit/equipment links. The three existing access windows are not production
boundaries. Phase 1 was merged in PR #2 at f700c1a.

## Run the workflow

```sh
uv sync --locked --extra access --extra ingestion --extra review
```

Set `ALLYOURBASE_HOME` to an external workspace. For example, from PowerShell:

```powershell
$env:ALLYOURBASE_HOME = 'C:\Users\savva\Documents\allyourbase\phase2-data'
uv run --extra ingestion allyourbase sources fetch config/sources/ourairports-rus.yaml --max-bytes 20000000
```

The output names an immutable manifest. Substitute that path in these commands:

```sh
uv run --extra ingestion allyourbase sources verify PATH/manifest.json
uv run --extra ingestion allyourbase sources stage PATH/manifest.json
uv run --extra ingestion allyourbase sources match
uv run --extra ingestion allyourbase catalogue queue
uv run --extra ingestion --extra review allyourbase catalogue review
```

Open http://127.0.0.1:8765. Inspect citations and source records, edit a JSON
review bundle, preview every site's AOI/zones/masks, and validate before accepting.
The geometry preview unwraps longitude across the antimeridian and retains holes.
It is a geometry preview without a basemap. Point-only sources display their
coordinates and cannot supply a site polygon or monitoring zone.

Accepted bundles update YAML/GeoJSON only after full catalogue validation. Each
acceptance writes a provenance record under `catalogue/provenance/`, including
the edited bundle, reviewer, source manifest, snapshot hash and record/page locator.
Rejection persists in DuckDB. No accept/reject decisions have been made for real
sites in this milestone. Code tests accept fictional fixtures only.

CLI review is also available:

```sh
uv run --extra ingestion allyourbase catalogue show PROPOSAL_ID
uv run --extra ingestion allyourbase catalogue accept PROPOSAL_ID bundle.json --reviewer owner --dry-run
uv run --extra ingestion allyourbase catalogue accept PROPOSAL_ID bundle.json --reviewer owner
uv run --extra ingestion allyourbase catalogue reject PROPOSAL_ID --reviewer owner --note "Reason"
```

A bundle contains `sites`, `units`, `equipment`, `terms` and optional
`evidence_proposals` (a list of supporting proposal IDs). Open the main proposal,
then click **+ Evidence** beside other queue records. This keeps all source records
and citations visible while you edit the bundle. Reference the attached source
IDs in each corresponding fact/zone/link; attaching evidence does not populate
or approve facts. Supporting proposals must be active and pending or accepted.
Rejected/superseded proposals, repeated IDs and the primary ID are refused.
Acceptance preserves all attached snapshots and locators; supporting proposals
keep their existing decision states. The primary proposal alone is accepted.

Entity objects use the existing catalogue schemas; `terms` maps facet names to taxonomy-term lists.
A bundle may update existing IDs. Review all changed claims, supply dates and
citations, and preserve alternative claims rather than silently replacing a
source disagreement. Geometry/status/branch/confidence are never inferred as
approved facts from an airport name or a matching score.

## Sources and permissions

A source spec contains the existing `Source` contract under `source`, a connector,
ISO3 `country`, optional `download_url`, optional `record_ids`, and the explicit
`extraction_permitted` flag for PDFs. The included
[OurAirports spec](../config/sources/ourairports-rus.yaml) pins the same dataset
revision used by Phase 1 and selects only the three existing pilot records.

- `import`: public HTTPS downloads with a byte limit and timeout. Redirects and
  credential-bearing URLs are rejected. Raw files stay outside Git.
- `reference`: permitted local PDF extraction only; no automated download.
  Full text stays in the external workspace. Reviewers enter short structured
  facts with page citations; copied page text is not exported to the catalogue.
- `manual`: locally supplied human-authored JSON records only. No automated
  parsing or retrieval of the underlying manual-class source.

For local inputs, run `sources snapshot SPEC.yaml INPUT_FILE`, then stage its
manifest. Snapshot IDs include the source spec, exact file hash and parser version;
verification checks both manifest identity and payload size/hash. Changing source
bytes creates a new immutable snapshot. Repeated identical records create no new
proposals, even after rejection. Superseded records remain auditable and appear
in `catalogue queue --state superseded`; matching uses current staged snapshots.
Different claims from one Wikidata entity remain separate records.

Supported inputs:

| Connector | Input and requirements |
| --- | --- |
| ourairports | Official airports CSV; filters country and retains source IDs, points, ICAO/GPS codes and region. It does not establish military status. |
| runways | Official runways CSV; retains runway attributes for explicit joins by airport ident. Global rows are not assigned to production sites. |
| geonames | Official 19-column UTF-8 country text or ZIP; populated places and aliases become a local gazetteer. Country and optional region disambiguate towns; all remaining alternatives are kept. |
| osm | Filtered GeoJSON with `node/way/relation` IDs or `@type`/`@id`; Polygon/MultiPolygon geometry is validated. PBF/XML requires the external `osmium` executable. The adapter filters Geofabrik extracts and exports with `--attributes type,id --stop-on-error`; no contributor metadata is staged. |
| wikidata | SPARQL JSON with `item`, `itemLabel` and literal `kind` of site/unit/equipment; optional `coord`, `nameLocal`, `icao`, `designation`, `branch`, `town`, `region`, `garrison`, `equipment`, `as_of`, `siteType`. Queries must define country/type scope and exclude people. `sources fetch --query-file QUERY.rq` retains the exact query in the snapshot. |
| pdf | A locally provided permitted PDF; extracts page text and optional configured `pdf_unit_patterns` with a named `designation` group and optional `town`, `branch`, `as_of`. Reviewers verify the original page and supply dated links. No OCR. |
| manual | JSON object with a `records` list matching `sources.contracts.Record`; the author supplies citation locators and selected facts, not scraped source text. |

Source formats and attribution: [OurAirports](https://ourairports.com/data/),
[GeoNames](https://download.geonames.org/export/dump/readme.txt),
[Wikidata](https://www.wikidata.org/wiki/Wikidata:Data_access),
[Geofabrik](https://download.geofabrik.de/technical.html),
and [osmium export](https://docs.osmcode.org/osmium/latest/osmium-export.html).

## Matching and durability

`config/ingestion.yaml` holds distance, name-similarity, honorific, designation
and branch/site-type hints. The fixed Cyrillic transliteration is a documented
basic matching key, not a full contextual BGN/PCGN implementation. Original names
are preserved. Site matches use shared identifiers or name plus distance; unit
matches use Wikidata ID or designation plus branch. Garrison candidates keep all
matching gazetteer alternatives and compatible sites within the configured radius.
These are proposals; no matching function selects an approved link or confidence.

The external `db/catalogue.duckdb` stores records, evidence, proposals, decisions
and current snapshot heads. `stg_site`, `stg_unit`, `stg_equipment` and `stg_link`
provide staging views. A process/thread lock serializes local workflow writes.
It is not the shared local/Colab/Drive lock required in Phase 7a.

Accepted writes use a durable journal, per-file hashes and atomic replacements.
If interrupted, preserve the journal and run `catalogue recover`; recovery refuses
to overwrite intervening unrelated edits. Planning and catalogue checking refuse
work while an acceptance journal is pending. Keep the VM-local database and
completed evidence archives outside Git; Drive checkpoint synchronization is
still Phase 7a work.

## Verification and remaining acceptance

All 192 tests, Ruff, formatting, strict mypy, schema/catalogue/settings checks and
repository hooks pass. Browser checks found no JavaScript errors or horizontal
overflow at 375 px. Desktop/mobile geometry previews, including antimeridian
polygons, were visually inspected. Fictional tests cover permitted PDF extraction,
source formats, ambiguous garrison candidates, rejected-proposal persistence,
superseded records, transactional rollback and acceptance recovery.

The pinned OurAirports CSV was fetched into the external `phase2-data` workspace
with SHA-256 `61c82a74de991e138dc57e1fbc72b6f47da30db9954be4e414452e896f7d40d8`.
The first import produced three proposals; the unchanged second import produced
zero. Production catalogue checking still reports zero sites/units/equipment.
Live GeoNames/Geofabrik imports and the native osmium adapter have not
been exercised on this machine. The PBF tool is not installed here.

Next: gather reviewed boundary/zone sources for the pilot, expand to ten or more
sites across the required types, source dated home-garrison/equipment claims,
and review them through this queue. Confirm the full pilot's provenance and zone
previews before closing Phase 2. Event review remains Phase 5; no imagery analysis,
scoring or publishing has been enabled.

## Multi-source review and readiness continuation

The bounded [Wikidata spec](../config/sources/wikidata-rus-sites.yaml) and
[SPARQL query](../config/sources/queries/wikidata-rus-sites.rq) have been exercised.
The import retains the exact query in its immutable payload. The fetcher supplies
an identifiable project User-Agent, reads UTF-8 queries with or without the
Windows BOM, and reports HTTP status codes without copying response bodies.

```powershell
uv run --extra ingestion allyourbase sources fetch config/sources/wikidata-rus-sites.yaml --query-file config/sources/queries/wikidata-rus-sites.rq --max-bytes 2000000
```

Retained snapshot `b4886266e3f0ae9da89677649cd20d456673a9d2b35ae0a726f1a90b945feabd`
has payload SHA-256
`b844632862b41c394605f7f9bc08d583a06662429ec5dadb7db271dd7ca0a617`.
It staged 28 records: 12 airbase, 8 naval-base and 8 generic military-base source
hints. Repeating stage on that manifest produced zero new proposals; matching
created zero additional proposals. Together with OurAirports, the queue has 31
site records. This is not a count of distinct or approved production sites.

Wikidata's country association (`P17`) does not establish physical location or
sovereignty. This discovery contains bases abroad, organizational entities,
unnamed entities and potential duplicates. A generic military-base hint does not
establish garrison status. All candidates need location/entity-identity review;
none supplies an approved boundary, zone, status or dated unit/equipment link.
Do not convert source points or Phase 1 squares into production geometry.
Wikidata data is CC0; see its [official access guidance](https://www.wikidata.org/wiki/Wikidata:Data_access).

The external development workspace has a review packet under
`review/phase-2-evidence/review-packet.md`, with per-proposal JSON dossiers and a
`readiness.json` report. Snapshots, full proposal evidence, databases and browser
QA screenshots remain outside Git.

```sh
uv run --extra ingestion allyourbase catalogue readiness --country RUS --minimum-sites 10 --require-type airbase --require-type naval_base --require-type garrison
```

`catalogue check` checks contracts; `readiness` separately checks milestone evidence
and exits 1 until complete. It requires the minimum production count, required
site types, exact current records in reviewed bundles and retained matching source
snapshots. Each site's reviewed unit must have a reviewed equipment link whose
dated interval overlaps its garrison link. Open intervals are bounded by their
`as_of` dates, never by today's retrieval date. Edited records, missing/changed
source evidence and unfinished acceptance journals prevent readiness.
This checks evidence completeness, not factual truth, current deployments or
whether a reviewer actually inspected every polygon. Human review is still
required. It currently reports zero production sites and `ready: false`.

The continuation passes 192 tests and the required lint/type/schema/catalogue
checks. Browser QA exercised evidence attachment, citation display and synthetic
zone previews at 1280 px and 375 px with no JavaScript errors or horizontal
overflow. Production acceptance still needs permitted boundary/zone sources,
dated unit/equipment sources and owner decisions on at least ten real sites.


## Mixed scope and source geometry continuation

The owner confirmed all Russian military base types on 2026-10-14. The first
[mixed pilot packet](phase-2-mixed-pilot.md) now contains ten mapped footprint
candidates and 77 zone/mask associations. The broader OSM discovery inventory
contains 18,568 tagged features, including structures that are not bases.

Native Overpass JSON/query fetching is exercised. `catalogue packet` prepares a
read-only geometry/citation packet outside Git, flags containment and compatible
zone-role gaps and links to staged proposals. Zones and water masks have separate
staging kinds. All 209 tests and required checks pass. Production approval,
status/claim dates and dated unit/equipment links remain open. None of the ten
polygons was accepted, and no new Sentinel imagery was requested.


## Review evidence continuation (2026-10-15)

`catalogue packet` now emits packet format version 2 and `review-gaps.json`, with
snapshot-pinned footprint/zone attachments, identity-source links and a visible
per-candidate worklist. Active accepted evidence remains available; rejected,
superseded or unrelated versions cannot supply attachment links. See the
[mixed-pilot continuation](phase-2-mixed-pilot.md#evidence-link-and-review-gap-continuation-2026-10-15)
for the retained input checks, refreshed local preview and remaining gaps.
All 219 tests and required checks pass. Production acceptance remains open.
