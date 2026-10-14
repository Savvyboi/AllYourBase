# ADR 0003 Source staging and catalogue review

Date: 2026-10-14. Status: implemented workflow; production acceptance pending.

## Decision

Use immutable content-addressed source snapshots and an external DuckDB staging
store. Source records create unapproved content-addressed proposals. Current
snapshot heads keep matching on the latest imported data; previous evidence and
decisions remain auditable. Identical records do not create new proposals after
acceptance or rejection. Conflicting claims remain separate.

Enforce source reuse class before retrieval or parsing. Reference PDFs are local,
explicitly permitted inputs; source page text stays outside the catalogue.
Manual-class records are entered by a human and never scraped. Automatic imports
stage a narrow field allow-list without personal/contributor data.

Review uses a loopback FastAPI app and an equivalent CLI. Validate complete edited
bundles against the catalogue before writing, preserve a provenance record and
use a recoverable write journal. Session-token API protection and a host/origin
check keep browser writes within the local review session. No event/publication
actions are included.

## Tradeoffs

The review editor accepts structured JSON rather than a visual polygon drawing
tool. The SVG geometry preview needs no remote tiles/scripts and handles polygon
holes and continuous longitude at the antimeridian. Reviewers still obtain and
verify the real boundaries and zones themselves.

Use a fixed basic Cyrillic transliteration for matching keys while retaining the
original names. Full contextual BGN/PCGN transliteration is deferred and is not
claimed by this implementation. Matching scores are suggestions, not confidence
or proof of a military affiliation.

PBF/XML parsing invokes an installed osmium-tool executable. Prepared GeoJSON
works on Windows without it. Native adapter live validation remains open.
The staging lock serializes local writers; it does not implement Drive-based
checkpoint synchronization or the cross-runtime lock planned for Phase 7a.

## Acceptance

Offline workflow tests and one bounded live OurAirports import pass. Phase 2 is
not complete until ten or more real Russian sites, zones and sourced dated unit/
equipment links have been reviewed and every fact traces to its source. The
three Phase 1 access windows remain separate from the production catalogue.
