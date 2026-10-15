# ADR 0004: Coordinate-based ground-change MVP

Date: 2026-10-15. Status: accepted scope, implementation in progress.

The owner supplied a replacement coding-agent plan and asked to change scope and
goals. The large review-first catalogue, Colab processing and later Hugo site
required evidence unrelated to the smaller immediate goal. The replacement plan
is authoritative; earlier source records, approval decisions and provider evidence
remain retained historical work.

Use a coordinate list, a fixed metric 1 km square, seven complete UTC target days
and a strictly earlier 28-day baseline. Reuse existing CDSE authentication,
transport, discovery and geometry validation. Use numerical Sentinel Hub Process
cutouts for both sensors, with exact returned-scene/grid checks. This also removes
the MVP's dependency on separate optical S3 credentials. Keep radar relative-orbit
metadata mandatory. Deduplicate alternate products from one acquisition before
counting baseline observations.

A small Python package computes configurable prototype optical/radar differences
and connected patches. It emits possible-ground-change reports, explicit coverage
and data-gap/error statuses, with no equipment/activity/cause inference or invented
confidence. Reports retain source scene IDs, version, thresholds and separate
sensor areas. Raw data stays local; small JSON and PNG history is durable in a
dedicated Git results branch. No database is introduced.

Use GitHub Actions for weekly/manual analysis, persistent history, locking and the
complete static build; deploy through official GitHub Pages actions. Plain
HTML/CSS/JavaScript is sufficient. The owner's requested automatic publication
policy supersedes the legacy catalogue's review-only policy for this MVP. Code
still goes through draft PRs; merging is not implicitly authorized.

This deliberately defers Colab integration, Hugo, taxonomy/catalogue completion,
unit/equipment provenance, object recognition, web coordinate input and complex
frontend work. The active acceptance checks are numerical fixtures, real example
inspection, a manual workflow publishing a working page, and the next unattended
scheduled run. Prototype thresholds remain unvalidated until independent historical
ground truth supports them. Retain all older results and documentation.
