# Phase 2 monitoring geometry preparation

Updated 2026-10-15 (Europe/Helsinki).

The existing owner-approved ten-candidate batch now has 47 usable source zones
across six candidates. Production acceptance is still open: four candidates have
no supported primary zone, and sourced status/dates and historical unit/equipment
contracts remain incomplete. Nothing has been written to the production catalogue.

## Reproduce the preparation

Set `ALLYOURBASE_HOME` to the external Phase 2 workspace, then run:

```sh
uv run --extra ingestion allyourbase catalogue prepare-geometry EXTERNAL_PACKET/packet.json EXTERNAL_OUTPUT
```

The command checks the retained owner approval, verifies its immutable source
payloads and reconstructs the packet from exact snapshots and currently eligible
proposals. A packet that differs from those records is refused, even if someone
recorded approval of the edited packet. Rejected/superseded evidence cannot supply
prepared geometry. Input/output separation prevents overwriting the source packet.

It writes `geometry-drafts.json`, `prepared-geometry.geojson` and `preview.html`.
These are geometry components for later structured review bundles, not complete
`ReviewBundle` documents. They intentionally omit status, factual claim dates,
unit/equipment links and processing choices. No source proposal decisions change.

Contained zones with a configured primary role are retained exactly. Parking
candidates are not promoted to vehicle parks. Crossing monitoring zones are
explicitly deferred. Water polygons are intersected with each selected zone;
zero-area intersections, including boundary touches, are omitted. Any positive
intersection retains its source evidence and operation; resulting masks must pass
exact containment after longitude wrapping. Holes and disjoint parts are retained.
There is no geometry buffering or expansion of approved site boundaries.

## Retained batch result

| Candidate | Prepared zones | Result |
| --- | --- | --- |
| Chkalovsky | 9 aprons | Geometry prepared |
| Engels | 9 aprons | Geometry prepared |
| Olenya | 5 aprons | Geometry prepared |
| Gromovo | 4 aprons | Geometry prepared |
| Novorossiysk | 0 | Parking does not establish a pier/anchorage |
| Zapadnaya Litsa | 8 piers | Geometry prepared |
| Gadzhiyevo | 12 piers | Geometry prepared |
| Ground parcel 60208009 | 0 | No mapped monitoring zone |
| Ground parcel 1317407504 | 0 | Water alone is not a monitoring zone |
| Ground parcel 1334980464 | 0 | Parking does not establish military vehicle use |

All five crossing features in the source packet are water masks. None overlaps
any of the 47 selected zones by positive area, so they are excluded from those
zone components with an explicit reason. The original source polygons and their
five source-boundary conflicts remain unchanged in the original packet. The other
25 deferred associations are also recorded. No water mask was needed in this
retained batch; clipping itself is exercised by synthetic regression fixtures.

The output is under external `review/mixed-pilot-geometry-20261015/`, with a
loopback preview at http://127.0.0.1:8770/preview.html. The original approved
source preview remains at http://127.0.0.1:8769/preview.html. Restart the loopback
servers if their processes stop. Approval remains tied to review ID
`151d4e72412905a9b3d6168f91695f7194068d3b667063f83a5ca9d83c8660dd`.
The report hashes the exact input packet bytes, independently of that review ID.

## Historical source continuation

The [NTI paper published 10 May 2009](https://www.nti.org/analysis/articles/heavy-bomber-force-overview/)
reports an 18 October 2000 refurbishment announcement associating the 22nd Bomber
Aviation Division, Engels and Tu-160 aircraft. Two short manually curated records
retain the unit and the reported association with that historical date, its
section/paragraph locator and an explicit `reported` confidence. The original
references [13,19] have not been verified; the source does not establish current
status, current equipment, or an association with the exact modern OSM footprint.

The [manual source spec](../config/sources/nti-rus-bombers-history.yaml) permits
locally curated notes only. No article was automatically parsed or stored, and
no article text or personal data was copied into the catalogue. The publication
and access dates are distinct from the reported historical claim date. The link
is bounded to 2000-10-18; it does not assert a continuous deployment interval.

Snapshot ID: `c31937e9302ee7a5c4d9f65f2d955a9b74e2a902255e7f86c391715d740b2a3f`.
Payload SHA-256: `0f5d9800a48aec66c2d6839b3803ebe9fb0945f77e65b6fda7a64190efffcf1a`.
The first stage created two proposals; repeat staging created zero. Notes,
locators, proposal IDs and validation remain outside Git under
`review/historical-evidence-20261015/`. Both proposals are pending.

## Verification and next work

All 243 tests and required project checks pass. Regression cases cover mask
clipping, holes/disjoint parts, antimeridian containment, unsupported roles,
missing evidence, reconstruction after rejection, forged packets, repeated
outputs, CLI output paths and unchanged input/catalogue decisions. Redirected
Windows JSON output now escapes unencodable characters, preserving Cyrillic
source names instead of misreporting an encoding failure as corrupt source data.

Desktop and 375 px Edge checks exercised all ten candidates, all 47 zones,
search and JSON/GeoJSON downloads with no JavaScript errors or horizontal
overflow. Screenshots were visually inspected. Every real prepared zone passes
exact footprint containment. `catalogue readiness` returns `ready: false` with
zero production sites and 41 pending site records. The queue now has 187 active
record proposals, including the two historical notes, plus three superseded ones.

Next: retain permitted independent evidence for the four role/geometry gaps,
status dates and dated historical links, then assemble complete validated review
bundles using these geometry components. Preserve the existing owner decision.
Keep Phase 2 incomplete until ten production sites across the required types
satisfy evidence readiness; Phase 3 remains gated on that acceptance.
