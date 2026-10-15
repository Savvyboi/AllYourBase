# Phase 2 mixed Russian pilot source geometry

> Historical catalogue work. The 2026-10-15 scope change supersedes its
> acceptance gates; see the [active ground-change plan](build-plan.md).


Updated 2026-10-15 (Europe/Helsinki).

The owner selected the mix of all military base types across Russia. This
continuation prepares a first review batch of ten sites: four airbases, three
naval facilities and three proposed ground garrisons. It is not an exhaustive
inventory, an approved production catalogue or a claim about current deployments.
The owner approved the displayed candidate identities/classifications and source
geometry on 2026-10-15; independent evidence and geometry validation remain open.

The [selection file](proposals/rus-mixed-pilot.yaml) contains source object IDs,
identity alternatives and review notes. Coordinates and source polygons remain
in the external workspace. The production catalogue still contains zero sites.

## First review batch

| Candidate | Proposed type | OSM footprint | Contained zone/mask polygons | Boundary conflicts |
| --- | --- | --- | --- | --- |
| Chkalovsky Air Base | airbase | [relation/3300255](https://www.openstreetmap.org/relation/3300255) | 16 | 0 |
| Engels-2 Air Base | airbase | [way/240082750](https://www.openstreetmap.org/way/240082750) | 10 | 0 |
| Olenya air base | airbase | [way/1058596337](https://www.openstreetmap.org/way/1058596337) | 10 | 3 |
| Gromovo Air Base | airbase | [relation/10887616](https://www.openstreetmap.org/relation/10887616) | 4 | 0 |
| Novorossiysk naval base | naval_base | [way/233225970](https://www.openstreetmap.org/way/233225970) | 1 | 0 |
| Zapadnaya Litsa Submarine Base | naval_base | [way/1533936043](https://www.openstreetmap.org/way/1533936043) | 8 | 0 |
| Gadzhiyevo Naval Base | naval_base | [way/1534042409](https://www.openstreetmap.org/way/1534042409) | 21 | 2 |
| 7th Separate Guards Motor Rifle Regiment source parcel | garrison | [way/60208009](https://www.openstreetmap.org/way/60208009) | 0 | 0 |
| 29th Separate Railway Brigade source parcel | garrison | [way/1317407504](https://www.openstreetmap.org/way/1317407504) | 1 | 0 |
| 10th Separate Repair and Evacuation Regiment source parcel | garrison | [way/1334980464](https://www.openstreetmap.org/way/1334980464) | 1 | 0 |

There are 77 zone/mask associations, 72 fully contained and five crossing a
footprint. Crossing polygons stay visible in red; they are not clipped or
accepted. The source-zone response has 144 records across all query bounding
boxes: 80 zone candidates and 64 water-mask candidates. Features outside the
footprints are retained as evidence but omitted from the candidate associations.

Gromovo is an unnamed OSM military parcel near two Wikidata records; its identity
and duplicates need review. Gadzhiyevo is explicitly an estimated OSM outline.
The Novorossiysk parcel has no contained source pier/anchorage candidate. One
ground parcel has no mapped zone candidate, and parking tags do not establish
military vehicle use. All status/claim dates, zone roles and dated unit/equipment
links remain open. Ground-unit names are OSM source labels, not approved unit
associations or current locations.

## Retained evidence

The national discovery uses every `military=*` value plus `landuse=military`
inside the OSM Russia source area. It returned 18,568 features: 4,018 nodes,
13,576 ways and 974 relations, in a 3,091,598-byte normalized input. These include
trenches, bunkers and buildings and must not be counted as bases. OSM country-area
membership is source scope; it does not resolve physical location or disputed
borders. An external CSV inventory preserves every returned feature for expansion.

Snapshots and exact queries are immutable and retained outside Git:

| Input | Final snapshot ID | Payload SHA-256 |
| --- | --- | --- |
| National discovery | `a449e7c547e9220ae1176448188c9b743e5d6598a7c07c01bcc50e2941cb4335` | `0726a2261748ab678fb557ccd76833441391f7365821af2b80bb1a497bb009b7` |
| Pilot footprints | `48340efee73a18ecd68a8f87f9aa014ca2751d476653ab5afad271093b4b8026` | `3984170b8e98f512bceda253817681a4fda8217cbc791bb2526e8810d295f8cc` |
| Zone candidates | `0571f039c2301e630513ce7aa8adbe2dc09607487e7b93a1fd99373c3f046c59` | `3276bd17fcb831b37745474cec07ce57b0d89af993aa6eb0b6104b794df89d0d` |

The original footprint snapshot is also retained. A finalized local snapshot
keeps source geometry notes and service tags in staging: that refinement added
three proposals and superseded three older record versions. Repeating either
final footprint or zone ingestion creates zero new proposals. The active queue
has 185 record proposals: 41 site records, 80 zone candidates and 64 masks.
Site records may duplicate physical facilities. No real proposal was accepted.

## Reproduce the packet

Install the locked ingestion and review extras, and set `ALLYOURBASE_HOME` to
the external workspace. Fetch the two pilot source specs with their matching
query files and stage the returned manifests:

```sh
uv run --extra ingestion allyourbase sources fetch config/sources/osm-rus-pilot-geometry.yaml --query-file config/sources/queries/osm-rus-pilot-geometry.overpassql --max-bytes 5000000
uv run --extra ingestion allyourbase sources fetch config/sources/osm-rus-pilot-zones.yaml --query-file config/sources/queries/osm-rus-pilot-zones.overpassql --max-bytes 5000000
uv run --extra ingestion allyourbase sources stage FOOTPRINT_MANIFEST
uv run --extra ingestion allyourbase sources stage ZONE_MANIFEST
uv run --extra ingestion allyourbase catalogue packet docs/proposals/rus-mixed-pilot.yaml FOOTPRINT_MANIFEST ZONE_MANIFEST EXTERNAL_OUTPUT --review-url http://127.0.0.1:8768
```

The command creates `packet.json`, `preview.html`, `source-polygons.geojson` and
`review-packet.md` outside the repository. Preview is read-only and uses local
SVG geometry, source links, search and layer toggles. Primary monitoring zone
roles come from settings, and missing compatible roles are flagged. Source
values are escaped before embedding in HTML. Each source link can open the
corresponding staged proposal in the catalogue review app. The packet itself
does not create or accept catalogue records.

In this development session, the packet is served at http://127.0.0.1:8767/preview.html
and the catalogue review queue runs at http://127.0.0.1:8768. These local services
must be restarted after the machine or process is stopped.

## Implementation and checks

The OSM connector now accepts native Overpass JSON in addition to prepared
GeoJSON and osmium input. It assembles only complete source rings, preserving
holes, islands and antimeridian continuity. Invalid/incomplete areas retain
explicit source centres with a geometry-gap flag; a point never becomes a
footprint. Partial/error responses cannot be staged. Source notes and geometry
caveats remain available to reviewers. Query text is retained verbatim in the
hashed input; `sources fetch --query-file` uses OSM `data` parameters.

All 209 tests, Ruff, formatting, strict mypy, settings/catalogue/schema checks
and repository hooks pass. Headless Edge exercised all ten previews, search,
layer geometry and queue links with no JavaScript errors or horizontal overflow
at 375 px. Airbase/naval desktop and garrison mobile screenshots were visually
inspected. Full snapshots, CSV inventory, generated packets and browser QA remain
outside Git. No Sentinel imagery requests were made.

OSM data requires attribution and ODbL treatment. See [OSM copyright](https://www.openstreetmap.org/copyright)
and the [Overpass language reference](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL).
Native osmium and live GeoNames/Geofabrik imports remain unverified.
The Colab source exporter includes the HTML templates and SPARQL/Overpass query
files; the earlier pinned Phase 1 archive is preserved.

Phase 2 stays open until the owner reviews actual site/zone geometry and sourced,
dated unit/equipment links satisfy `catalogue readiness`. Scope approval alone
does not approve the selected polygons, source classifications or facts.


## Evidence-link and review-gap continuation (2026-10-15)

Packet format version 2 pins every footprint and zone/mask queue link to its
exact verified input snapshot and semantic source record. Each attachment names
the proposal, source, snapshot, record, locator and decision state. Active
accepted source records remain available as supporting evidence. Rejected,
superseded or unrelated-source records cannot supply a link, even when their
external IDs match. A selected footprint without eligible staged evidence stops
packet generation; unavailable zone evidence stays visible as an explicit gap.
Source record selectors are honored and duplicate input IDs are refused.

The preview now shows identity-source queue links and open review tasks, and each
zone/mask has its own review link. A new `review-gaps.json` lists per-candidate
missing evidence, crossing source IDs and unlinked records, with aggregate gap
counts. It is a worklist, not an approval or an acceptance bundle. The existing
`catalogue packet` command produces all five artifacts; it makes no decisions.

The retained inputs were reprocessed into the separate external folder
`review/mixed-pilot-evidence-20261015/`, preserving the original packet and source
snapshots. All 77 associations link to exact staged evidence, with zero unlinked
zone/mask associations. The same five boundary conflicts affect two candidates;
four candidates lack a contained source zone with a compatible configured role.
Every candidate still needs identity/location, boundary/zone, status/date and
dated historical unit/equipment evidence review. No gaps were resolved by
clipping polygons, inventing dates or treating source labels as reviewed facts.

The refreshed preview is served at http://127.0.0.1:8769/preview.html; its links
use the existing queue at http://127.0.0.1:8768. Both are loopback services and
need restarting after their processes stop.

Verification: 219 tests and all required project checks pass. Regression cases
cover external-ID collisions across sources, accepted and stale accepted
supporting records, rejected/superseded footprints and zones, selected source
records, duplicate IDs and repeatable read-only gap reports. Browser QA checked
all ten candidates, all 77 zone links, identity links, JSON download, search and a
zone deep link, with no JavaScript errors or 375 px overflow. Desktop/mobile
screenshots were visually inspected. Full QA and generated files remain outside
Git. Production catalogue and decisions are unchanged; Phase 2 remains open.


## Owner decision recorded (2026-10-15)

The owner explicitly stated "all approved, continue" for the displayed packet.
The immutable approval archive is keyed by review ID
`151d4e72412905a9b3d6168f91695f7194068d3b667063f83a5ca9d83c8660dd`.
It retains the original packet bytes with SHA-256
`a1c8e5c7cf131c1d83a6e0afa49408567d18ec59992a7162b63625578e712f5f`.
The current preview and gap report carry this approval and no longer list the
owner identity/geometry review steps as missing. The exact displayed geometry
and source associations were preserved. Existing proposal decisions and the
production catalogue are unchanged.

Owner approval is complete for these displayed proposals. Remaining work is
validating the five crossing polygons, supplying supported roles/geometry for
four candidates, and retaining source-dated status and historical evidence.
Approval dates do not populate factual claim dates. Keep the recorded decision
for unchanged content; changed source content uses a different review ID.


## Monitoring geometry preparation continuation (2026-10-15)

PR #7 is merged. The [geometry preparation record](phase-2-geometry-preparation.md)
documents 47 usable contained source zones across six candidates, transparent
zone-level water-mask handling, four remaining primary-zone gaps and two pending
historical evidence notes. The five crossing source water polygons are deferred
because they do not overlap selected monitoring zones; the source packet and its
approval remain intact. All 243 tests, required checks and desktop/mobile preview
checks pass. No production records or source decisions were accepted; milestone
readiness remains false.


## Structured bundle continuation (2026-10-15)

Draft [PR #8](https://github.com/Savvyboi/AllYourBase/pull/8) remains open and now
prepares ten incomplete structured review bundles with exact source evidence and
validation worklists. The existing owner approval and 47 contained zones are
preserved; four zone gaps and factual evidence remain. The two pending historical
notes pass retained-snapshot integrity checks, while their original references
and modern footprint correspondence remain unverified. See
[bundle preparation](phase-2-bundle-preparation.md) for reproduction, source
limitations and 254 passing tests plus required checks. Production acceptance
and milestone readiness remain incomplete.
