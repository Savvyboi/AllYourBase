# AllYourBase build plan

Updated 2026-10-15 (Europe/Helsinki). The owner replaced the earlier scope with the
[Sentinel ground-change MVP plan](ground-change-agent-plan.md). This is now the
active roadmap. The [previous roadmap](legacy-build-plan.md), catalogue workflow,
source evidence and owner approvals are retained as historical work; their
production catalogue milestones are not prerequisites for this MVP.

## Current scope

One Python pipeline; coordinates in `sites.yaml`; fixed 1 km × 1 km, 10 m,
100 × 100 grids; CDSE Sentinel Hub numerical Sentinel-1/2 cutouts; latest seven
complete UTC days against the preceding 28; prototype possible-change patches;
small static HTML/CSS/JS reports; weekly GitHub Actions and automatic GitHub Pages.
Start with Chkalovsky, chosen from the existing approved records at the owner's
instruction. Defer object recognition, web coordinate entry, a database and a
complex frontend. Colab, Hugo, broad catalogue ingestion and unit/equipment facts
are outside the active MVP.

## Ordered implementation and acceptance

| Step | Implemented/verified | Remaining acceptance |
| --- | --- | --- |
| 1 Coordinates, grid and UTC windows | Strict coordinates, fixed metric 100×100 grid, persistent grid identity, exclusive historical end date, 7-day target/28-day earlier baseline | Keep coordinate changes under a new stable ID. |
| 2 Optical access and masks | CDSE Catalog/Process, FLOAT32 reflectance/SCL/dataMask cutouts, exact scene/grid verification, nearest categorical sampling, land/cloud buffer | Preserve live source provenance and explicit data gaps. |
| 3 Radar access and comparison | IW VV/VH, relative-orbit/direction/mode/polarisation groups, LEE/terrain correction, positive power/masks, linear median before dB | Skip unverified geometry; do not mix passes or duplicate products. |
| 4 Prototype detection | Every usable target acquisition, >=2 independent baseline observations per pixel, >=70% common coverage, optical >0.10, radar >3 dB, >=9 connected cells | Independently sourced historical ground truth and initial threshold acceptance remain open. |
| 5 Report and history | Deterministic detection IDs, separate sensor areas/overlap labels, composite/current/patch previews, statuses, source IDs/version/thresholds/attribution, preserved history | Continue validation on real examples without inferring cause. |
| 6 Actions and Pages | PRs #9/#10 merged; first manual run succeeded on 2026-10-15 for end 2026-10-12; expected results branch/artifact and public desktop/mobile report verified; actionlint added to CI | First publication accepted. Retain explicit error/data-gap status and small report history. |
| 7 Unattended acceptance | Not yet achieved | Next scheduled run: 2026-10-19 06:23 UTC. It must succeed with correctly dated output and retained history on a fresh runner. |

All 294 offline tests and required lint/type/catalogue/schema checks pass. The local
historical run ending 2026-10-12 produced one radar possible-change report; optical
had one usable quiet comparison and three data gaps. Cached rerun produced the same
single detection and no new Process requests. Desktop/mobile browser QA and visual
inspection of the flagged radar/quiet optical previews pass. These outputs do not
verify a real-world event or calibrate the prototype thresholds.

## Operational boundaries

Code/configuration/tests/docs stay on the code branch. Raw rasters, credentials,
full diagnostics and local environments stay outside Git. Small report JSON/PNGs
are committed only to `monitor-results`; the complete static site is deployed from
an allow-listed output directory. Preserve earlier reports when one location fails.
No-change or failed-data checks create no news item. Automatic publication of
possible changes is the owner's new requested policy; it does not authorize merging
code PRs without review.

See [MVP execution and validation](ground-change-mvp.md) and
[ADR 0004](adr/0004-ground-change-mvp.md). The [first manual publication](https://github.com/Savvyboi/AllYourBase/actions/runs/38756679440)
and [live page](https://savvyboi.github.io/AllYourBase/) are verified. The subsequent
unattended weekly run and real historical ground truth remain unverified. Do not
mark the MVP complete while those checks remain open.
