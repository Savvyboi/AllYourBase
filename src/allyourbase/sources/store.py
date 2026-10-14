"""Transactional DuckDB staging and durable, content-addressed review proposals."""

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from allyourbase.loading import InputError
from allyourbase.sources.connectors import parse_records
from allyourbase.sources.contracts import Record
from allyourbase.sources.matching import (
    MatchSettings,
    designation,
    distance,
    geocode,
    site_match,
    unit_match,
)
from allyourbase.sources.snapshots import canonical, verify_snapshot

_WORKFLOW_LOCKS: dict[Path, Any] = {}


def workflow_lock(workspace: Path) -> Any:
    from filelock import FileLock

    path = workspace.resolve() / "db" / "catalogue-workflow.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    return _WORKFLOW_LOCKS.setdefault(path, FileLock(str(path), timeout=0))


class Store:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.path = workspace / "db" / "catalogue.duckdb"

    @contextmanager
    def connect(self) -> Iterator[Any]:
        import duckdb
        from filelock import FileLock

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with workflow_lock(self.workspace), FileLock(str(self.path) + ".lock", timeout=0):
            connection = duckdb.connect(str(self.path))
            try:
                connection.execute("""CREATE TABLE IF NOT EXISTS snapshots
                    (id VARCHAR PRIMARY KEY, manifest VARCHAR NOT NULL);
                    CREATE TABLE IF NOT EXISTS records
                    (id VARCHAR PRIMARY KEY, source_id VARCHAR, kind VARCHAR, external_id VARCHAR,
                     content VARCHAR, match_key VARCHAR);
                    CREATE TABLE IF NOT EXISTS evidence
                    (record_id VARCHAR, snapshot_id VARCHAR, locator VARCHAR,
                     PRIMARY KEY(record_id, snapshot_id, locator));
                    CREATE TABLE IF NOT EXISTS proposals
                    (id VARCHAR PRIMARY KEY, kind VARCHAR, content VARCHAR,
                     state VARCHAR DEFAULT 'pending');
                    CREATE TABLE IF NOT EXISTS decisions
                    (proposal_id VARCHAR PRIMARY KEY, decision VARCHAR, reviewer VARCHAR,
                     note VARCHAR, decided_at TIMESTAMPTZ DEFAULT current_timestamp,
                     bundle VARCHAR);
                    CREATE TABLE IF NOT EXISTS heads
                    (scope VARCHAR PRIMARY KEY, snapshot_id VARCHAR);
                    CREATE VIEW IF NOT EXISTS active_records AS SELECT DISTINCT r.* FROM records r
                    JOIN evidence e ON e.record_id=r.id JOIN heads h ON h.snapshot_id=e.snapshot_id;
                    CREATE VIEW IF NOT EXISTS stg_site AS
                    SELECT * FROM active_records WHERE kind='site';
                    CREATE VIEW IF NOT EXISTS stg_unit AS
                    SELECT * FROM active_records WHERE kind='unit';
                    CREATE VIEW IF NOT EXISTS stg_equipment AS
                    SELECT * FROM active_records WHERE kind='equipment';
                    CREATE VIEW IF NOT EXISTS stg_link AS
                    SELECT * FROM proposals WHERE kind='link';""")
                yield connection
            finally:
                connection.close()

    def stage(self, manifest_path: Path, settings: MatchSettings) -> dict[str, int]:
        manifest, payload = verify_snapshot(manifest_path)
        created = 0
        count = 0
        with self.connect() as connection:
            connection.execute("BEGIN")
            try:
                connection.execute(
                    "INSERT INTO snapshots VALUES (?, ?) ON CONFLICT DO NOTHING",
                    [manifest.id, manifest.model_dump_json()],
                )
                scope = canonical(
                    [
                        manifest.spec.source.id,
                        manifest.spec.connector,
                        manifest.spec.country,
                        sorted(manifest.spec.record_ids),
                    ]
                )
                connection.execute(
                    "INSERT INTO heads VALUES (?, ?) ON CONFLICT(scope) "
                    "DO UPDATE SET snapshot_id=excluded.snapshot_id",
                    [scope, manifest.id],
                )
                selected = set(manifest.spec.record_ids)
                found: set[str] = set()
                for record in parse_records(manifest, payload):
                    if selected and record.external_id not in selected:
                        continue
                    found.add(record.external_id)
                    content = record.model_dump(mode="json")
                    semantic = {k: v for k, v in content.items() if k != "locator"}
                    identifier = hashlib.sha256(
                        canonical({"source": manifest.spec.source.id, "record": semantic}).encode()
                    ).hexdigest()
                    key, honors = designation(
                        str(record.attributes.get("designation", record.name)), settings
                    )
                    existed = connection.execute(
                        "SELECT 1 FROM records WHERE id=?", [identifier]
                    ).fetchone()
                    connection.execute(
                        "INSERT INTO records VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                        [
                            identifier,
                            manifest.spec.source.id,
                            record.kind,
                            record.external_id,
                            canonical(content),
                            key,
                        ],
                    )
                    connection.execute(
                        "INSERT INTO evidence VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                        [identifier, manifest.id, record.locator],
                    )
                    if record.kind not in {"place", "runway"} and not existed:
                        proposal = {
                            "record_ids": [identifier],
                            "record": content,
                            "honorifics": honors,
                            "match_key": key,
                            "notice": "Unapproved source claim; geometry and facts need review.",
                        }
                        created += self.insert_proposal(connection, "record", proposal)
                    count += 1
                if selected - found:
                    raise InputError("selected source record IDs were not found in this country")
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        return {"parsed_records": count, "new_proposals": created}

    @staticmethod
    def insert_proposal(connection: Any, kind: str, content: dict[str, Any]) -> int:
        identifier = hashlib.sha256(
            canonical({"kind": kind, "content": content}).encode()
        ).hexdigest()
        if connection.execute("SELECT 1 FROM proposals WHERE id=?", [identifier]).fetchone():
            return 0
        connection.execute(
            "INSERT INTO proposals(id, kind, content) VALUES (?, ?, ?)",
            [identifier, kind, canonical(content)],
        )
        return 1

    def proposals(self, state: str = "pending") -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.connect() as connection:
            active = {r[0] for r in connection.execute("SELECT id FROM active_records").fetchall()}
            rows = connection.execute(
                "SELECT id, kind, content, state FROM proposals WHERE state=? ORDER BY id",
                ["pending" if state == "superseded" else state],
            ).fetchall()
            result = []
            for identifier, kind, raw, status in rows:
                content = json.loads(raw)
                if status == "pending" and not set(content["record_ids"]).issubset(active):
                    status = "superseded"
                if status == state:
                    result.append(
                        {"id": identifier, "kind": kind, "content": content, "state": status}
                    )
            return result

    def proposal(self, identifier: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT kind, content, state FROM proposals WHERE id=?", [identifier]
            ).fetchone()
            if row is None:
                raise InputError("unknown proposal")
            content = json.loads(row[1])
            active_ids = {
                r[0] for r in connection.execute("SELECT id FROM active_records").fetchall()
            }
            source_records = [
                json.loads(
                    connection.execute(
                        "SELECT content FROM records WHERE id=?", [record_id]
                    ).fetchone()[0]
                )
                for record_id in content["record_ids"]
            ]
            evidence: list[dict[str, Any]] = []
            for record_id in content["record_ids"]:
                rows = connection.execute(
                    """SELECT s.manifest, e.locator FROM evidence e
                    JOIN snapshots s ON s.id=e.snapshot_id
                    WHERE e.record_id=? ORDER BY s.id, e.locator""",
                    [record_id],
                ).fetchall()
                evidence.extend(
                    {"record_id": record_id, "manifest": json.loads(m), "locator": loc}
                    for m, loc in rows
                )
            return {
                "id": identifier,
                "kind": row[0],
                "content": content,
                "state": row[2],
                "evidence": evidence,
                "records": source_records,
                "active": set(content["record_ids"]).issubset(active_ids),
            }

    def decide(
        self,
        identifier: str,
        decision: str,
        reviewer: str,
        note: str,
        bundle: dict[str, Any] | None = None,
    ) -> None:
        if decision not in {"accepted", "rejected"} or not reviewer.strip():
            raise InputError("decision and reviewer are required")
        with self.connect() as connection:
            connection.execute("BEGIN")
            try:
                current = connection.execute(
                    "SELECT state FROM proposals WHERE id=?", [identifier]
                ).fetchone()
                if current is None or current[0] != "pending":
                    raise InputError("proposal is absent or already decided")
                connection.execute(
                    "INSERT INTO decisions(proposal_id, decision, reviewer, note, bundle) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [identifier, decision, reviewer, note, canonical(bundle)],
                )
                connection.execute(
                    "UPDATE proposals SET state=? WHERE id=?", [decision, identifier]
                )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise

    def match(self, settings: MatchSettings) -> int:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, source_id, content FROM active_records ORDER BY id"
            ).fetchall()
            records = [
                (identifier, source, Record.model_validate_json(content))
                for identifier, source, content in rows
            ]
            sites = [r for r in records if r[2].kind == "site"]
            units = [r for r in records if r[2].kind == "unit"]
            places = [r for r in records if r[2].kind == "place"]
            created = 0
            connection.execute("BEGIN")
            try:
                for group in (sites, units):
                    for index, (left_id, left_source, left) in enumerate(group):
                        for right_id, right_source, right in group[index + 1 :]:
                            if left_source == right_source:
                                continue
                            result = (
                                site_match(left, right, settings)
                                if left.kind == "site"
                                else (
                                    {"reason": "unit_designation_or_id"}
                                    if unit_match(left, right, settings)
                                    else None
                                )
                            )
                            if result:
                                created += self.insert_proposal(
                                    connection,
                                    "match",
                                    {"record_ids": sorted([left_id, right_id]), **result},
                                )
                for unit_id, _, unit in units:
                    town = unit.attributes.get("town")
                    if not town:
                        continue
                    candidates = geocode(
                        str(town),
                        unit.country,
                        unit.attributes.get("region"),
                        [p[2] for p in places],
                    )
                    for place in candidates:
                        place_id = next(p[0] for p in places if p[2] == place)
                        for site_id, _, site in sites:
                            allowed = settings.branch_site_types.get(
                                str(unit.attributes.get("branch")), []
                            )
                            site_type = site.attributes.get(
                                "site_type"
                            ) or settings.osm_site_type_hints.get(
                                str(site.attributes.get("military"))
                            )
                            if not allowed or site_type not in allowed:
                                continue
                            separation = distance(place, site)
                            if (
                                site.country == unit.country
                                and separation <= settings.link_distance_km
                            ):
                                created += self.insert_proposal(
                                    connection,
                                    "link",
                                    {
                                        "record_ids": sorted([unit_id, place_id, site_id]),
                                        "unit_record": unit_id,
                                        "site_record": site_id,
                                        "place_record": place_id,
                                        "distance_km": separation,
                                        "notice": "Candidate home garrison; deployment is unknown.",
                                    },
                                )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            return created

    def runways(self, airport_ident: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT content FROM active_records WHERE kind='runway'"
            ).fetchall()
        return [
            json.loads(r[0])
            for r in rows
            if json.loads(r[0])["attributes"]["airport_ident"] == airport_ident
        ]
