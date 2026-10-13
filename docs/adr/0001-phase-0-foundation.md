# ADR 0001 Local foundation and project naming

Status: accepted for Phase 0. Date: 2026-10-13.

## Context

The owner names the tool AllYourBase. The supplied plan uses Basewatch for the
package and CLI, requires local analysis, a human-curated catalogue, and a
separate static GitHub Pages publication repository. It orders implementation
by milestone, starting with a tested skeleton.

## Decision

Use `allyourbase` as the package and primary CLI name. Keep `basewatch` as a
compatibility entry point for the plan's command examples. Resolve paths from
`ALLYOURBASE_HOME`, falling back to `BASEWATCH_HOME` and then settings.
Use strict Pydantic models and generate JSON Schemas from them; validate
cross-file references and spatial relationships in Python.

Keep the production catalogue empty until source-derived facts pass review.
Commit an explicitly fictional fixture for offline testing. Put all numerical
thresholds and provider candidates in configuration and mark undefined values
as provisional. Install the lightweight foundation by default and reserve
imagery/review/ingestion dependencies as optional extras.

Expose future command names now, but refuse their execution until implemented.
Planning is explicit and cannot create results, download imagery or publish.
The algorithm version is `0.0.0` because there is no algorithm yet; the package
version is `0.1.0`.

Do not create a hosted Sites dashboard for this milestone: the owner's plan calls
for Hugo/GitHub Pages in Phase 6, after the local pipeline and review gate.

## Consequences

Phase 0 is usable for input validation and review but makes no GEOINT detections.
A new country or site type is expressed in catalogue/configuration records;
algorithms do not need country-specific branches. Unknown fields, tags,
unsourced references and malformed polygons fail early.

Provider selection remains provisional until the Phase 1 spike. The build plan
labels its eventual provider decision ADR-001; this project reserves ADR-0001
for the foundation and will record that measured decision as ADR-0002 instead.
