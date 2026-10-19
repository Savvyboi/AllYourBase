# ADR 0005: Sentinel-2 only, with site categories

Date: 2026-10-20. Status: accepted scope; implementation prepared for review.

The owner removed Sentinel-1 from the active monitor and requested category
grouping in the local tool and category views online. This supersedes the sensor
choice and combined-sensor reporting in ADR 0004 and the October 15 owner plan.
The fixed grid, optical masks, UTC windows, prototype optical threshold and
history/publication architecture remain applicable.

The active monitor accepts only Sentinel-2 at discovery, Process and comparison
boundaries. Remove radar processing/configuration from this package and increment
the analysis version to `ground-change-0.2.0`. Keep legacy provider/catalogue code
and archived reports as historical evidence. The static builder excludes radar
records/previews, removes obsolete generated radar previews, and projects older
combined checks to their optical status. It does not rewrite archived reports.

Each site has one optional display category, defaulting to `Uncategorized`.
Category/name edits do not change grid identity or detection IDs. Current
`sites.yaml` categories override display metadata during a build, so regrouping
retained history needs no imagery requests. Use labels rather than category paths;
escape labels in HTML and encode category links in URLs.

Provide bulk category editing through the local monitor UI, also linked from the
existing catalogue review UI, and CLI listing/assignment commands. Preserve YAML
comments/coordinates, write atomically under a file lock, and reject stale
revisions. Reuse loopback, same-origin and session-token protection.

The online viewer groups site checks by category and combines category selection
with status filters. Category filtering also applies to recent detections. The
manual workflow can rebuild/publish retained history without CDSE requests.

The old radar threshold/control limitation is historical. Optical thresholds
remain prototypes; removing radar does not calibrate optical change detection.
