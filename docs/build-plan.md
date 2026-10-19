# AllYourBase build plan

Updated 2026-10-20. The owner narrowed the monitor to Sentinel-2 only and added
site category grouping. [ADR 0005](adr/0005-optical-only-categories.md) supersedes
the two-sensor portion of [the October 15 plan](ground-change-agent-plan.md).
Catalogue/Colab/Hugo milestones remain historical and do not gate this MVP.

| Area | Implementation | Remaining acceptance |
| --- | --- | --- |
| Inputs and grid | Stable IDs/coordinates, fixed 1 km square, 100x100 metric grid, 7-day target and earlier 28-day baseline | Coordinates/size changes require a new ID. |
| Optical imagery | Sentinel-2 Catalog/Process only, scene/grid verification, numerical reflectance and SCL/dataMask, conservative masks | Preserve explicit coverage/errors; no radar fetching. |
| Detection | Per-acquisition optical median comparison, >=2 independent baseline observations, >=70% coverage, >0.10 mean band difference, >=9 connected cells | Independent optical threshold validation remains open. |
| Categories | Optional category defaults to Uncategorized; protected local grouped editor, CLI assignment/listing; category-independent grid identity | Publish committed category edits through the normal workflow. |
| Online viewer | Category groups/filter, combined status filter, category links, optical-only news/history projection | Verify deployed category UI after merging this scope change. |
| History and automation | Persistent results archive, official Pages actions, concurrency/retries, manual rebuild-only mode | Older radar history remains archived and absent from active output. |
| Unattended operation | Previous two-sensor scheduled run succeeded on 2026-10-19 | Verify the following optical-only run; next configured trigger is 2026-10-26 06:23 UTC. |

296 tests and required checks pass. Cached optical validation and desktop/mobile
category QA pass without new imagery requests. See [execution details](ground-change-mvp.md).
The earlier [CEMS validation](historical-validation.md) exposed radar control flags;
those results are historical after radar removal and do not calibrate optical
thresholds. Keep those thresholds labelled prototypes.

Preserve source evidence, approvals, archived reports and legacy code. Only small
JSON/PNG history belongs on `monitor-results`; main holds code/config/docs/tests.
Raw imagery, credentials, usage journals and browser QA remain outside Git. Category
edits change display metadata without altering historical acquisitions or grids.
The [legacy roadmap](legacy-build-plan.md) is superseded. The MVP remains incomplete
until the new scope is published, runs unattended and its optical acceptance checks pass.
