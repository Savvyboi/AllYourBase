# Phase 0 pull request draft

Title: Establish the AllYourBase local pipeline foundation

AllYourBase needs a validated, reproducible local foundation before imagery
processing begins. This change adds the Python 3.12/uv project, sourced catalogue
and settings contracts, offline integrity checks, generated JSON Schemas, and
the required CLI surface. Planning produces UTC site/week windows; unimplemented
processing, review and publication commands fail without side effects.

Validation: `make check` runs Ruff, formatting, strict mypy, pytest/Hypothesis,
settings validation, catalogue validation and schema drift checking. The
production catalogue is empty; fixtures are clearly synthetic.

No live provider access, scored imagery, review app or website is included in
this milestone. Provider coverage and costs are the next measured spike.
