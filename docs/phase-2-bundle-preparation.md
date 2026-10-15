# Phase 2 structured review bundle preparation

> Historical catalogue work. The 2026-10-15 scope change supersedes its
> acceptance gates; see the [active ground-change plan](build-plan.md).


Updated 2026-10-15 (Europe/Helsinki). This continuation extends draft
[PR #8](https://github.com/Savvyboi/AllYourBase/pull/8); it is not merged.

Ten source-pinned bundle drafts are prepared outside Git. Six retain the existing
47 contained monitoring zones. Four still lack a supported primary zone. All ten
remain incomplete: status, factual claim dates, processing sensor choices and
verified dated historical unit/equipment links are still required. Production
catalogue counts remain zero and milestone readiness remains false.

## Reproduce from retained evidence

Set `ALLYOURBASE_HOME` to the external Phase 2 workspace, then run:

```sh
uv run --extra ingestion allyourbase catalogue prepare-bundles EXTERNAL_PACKET/packet.json EXTERNAL_OUTPUT
```

Use the retained packet under `review/mixed-pilot-evidence-20261015/`. The command
reconstructs its source records against verified immutable snapshots and eligible
staged proposals, reuses the existing owner approval and applies the same geometry
preparation as `catalogue prepare-geometry`. It does not trust an edited geometry
report. Source footprints and selected zones remain unchanged. Mask operations,
deferred source associations and original boundary/identity caveats are retained.

The shared geometry check validates exact zone/AOI and mask/zone containment,
including holes and antimeridian wrapping, without inventing status or dates just
to instantiate a complete site. The existing production validator uses the same
check. Polygon contracts and the six production schemas are unchanged.

Output contains:

- `bundle-drafts.json`: candidate worklist, contract-validation errors, evidence
  tasks, owner approval, exact input hash and hashes of each draft/sidecar.
- `review-bundles.md`: a readable table linking to each draft.
- `CANDIDATE/bundle-draft.json`: the existing review-bundle JSON shape, with
  incomplete site properties and no inferred units/equipment.
- `CANDIDATE/provenance.json`: exact evidence/proposal/snapshot locators, source
  manifests, owner approval scope, source caveats and geometry operations.

Each draft references its pending footprint proposal as the primary proposal and
attaches only evidence used for its footprint, selected zones and derived masks.
Identity suggestions and historical notes are not silently converted to approved
associations. `status`, `as_of` and `sensors` are omitted. Empty zone lists remain
visible for the four geometry gaps. Validation errors name the missing fields.
Contract validity, evidence readiness and factual verification remain distinct.

Repeat generation is byte-identical. Regeneration refuses conflicting existing
files before writing anything, preserving review edits. Copy a draft before
editing it and use a new output directory when regenerating changed content.
After supported facts and choices have been supplied, use the existing
`catalogue accept --dry-run` workflow for contract checks and `catalogue readiness`
for milestone evidence checks. Neither replaces verification of the cited facts.

## Retained batch and provenance checks

The output is under `review/mixed-pilot-bundles-20261015/`. It has ten draft
bundles, 47 zones, six geometry-ready candidates and zero contract-valid bundles.
The worklist records ten status/date gaps, ten dated historical-link gaps, ten
sensor choices and four primary-zone gaps. The owner review ID is unchanged:
`151d4e72412905a9b3d6168f91695f7194068d3b667063f83a5ca9d83c8660dd`.

External `review/bundle-preparation-20261015/validation.json` records repeat
identity, preserved packet/geometry/approval hashes, unchanged catalogue files and
queue decisions, and readiness false. The queue remains 187 pending record
proposals plus three superseded versions, with zero accepted/rejected proposals.
No new imagery requests or source imports were made.

The two pending historical notes were checked against their retained manual
snapshot, semantic record hashes and exact locators. A separate
`historical-source-check.json` records the bibliographic inspection of the
[NTI overview](https://www.nti.org/analysis/articles/heavy-bomber-force-overview/).
NTI lists reference [13] on 18 October 2000 and reference [19] for
8–14 September 2000. The latter predates the reported October announcement;
this timing means bibliography inspection alone cannot corroborate that event.
Bounded title/date searches did not retrieve either original publication. Their
contents and correspondence with the modern mapped footprint remain unverified.
The notes remain historical reported evidence, unattached to production bundles.
No current deployment, count or continuous interval is inferred.

## Verification and remaining acceptance

All 254 tests, Ruff, formatting, strict mypy, settings/catalogue/schema checks and
all five repository hooks pass. Eleven new regression cases cover usable draft
shape, missing roles, exact evidence attachments, repeat generation, review-edit
protection, rejected/corrupt/forged/unapproved inputs, output boundaries and
geometry-only checks of holes/masks across the antimeridian. The existing geometry
preview templates and displayed source geometry are unchanged.

Next: resolve the four supported-role/zone gaps with permitted independent
sources; verify source-dated status and historical associations before attaching
complete unit/equipment contracts. Reuse the saved owner approval for unchanged
content. Phase 2 remains open until at least ten production sites across all
required types pass actual evidence readiness. Phase 3 remains gated.
