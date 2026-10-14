"""Content-addressed immutable inputs with bounded import-only downloading."""

import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from allyourbase import __version__
from allyourbase.loading import InputError, load_data, load_model
from allyourbase.sources.contracts import PARSER_VERSION, Snapshot, SourceSpec


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_snapshot(workspace: Path, spec: SourceSpec, input_path: Path) -> Path:
    sha = digest_file(input_path)
    identity = canonical(
        {
            "spec": spec.model_dump(mode="json"),
            "sha256": sha,
            "parser_version": PARSER_VERSION,
            "name": input_path.name,
        }
    )
    identifier = hashlib.sha256(identity.encode()).hexdigest()
    directory = workspace / "sources" / spec.source.id / identifier
    manifest_path = directory / "manifest.json"
    if directory.exists():
        verify_snapshot(manifest_path)
        return manifest_path
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory.parent) as temporary:
        staging = Path(temporary) / "snapshot"
        staging.mkdir()
        target = staging / "payload"
        with input_path.open("rb") as source, target.open("xb") as destination:
            while block := source.read(1024 * 1024):
                destination.write(block)
        if digest_file(target) != sha:
            raise InputError("source changed while snapshotting; retry with a stable file")
        manifest = Snapshot(
            id=identifier,
            sha256=sha,
            size_bytes=target.stat().st_size,
            retrieved_at=datetime.now(UTC),
            original_name=input_path.name,
            spec=spec,
        )
        (staging / "manifest.json").write_text(
            manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        try:
            staging.rename(directory)
        except FileExistsError:
            verify_snapshot(manifest_path)
    return manifest_path


def verify_snapshot(manifest_path: Path) -> tuple[Snapshot, Path]:
    manifest = load_model(manifest_path, Snapshot)
    payload = manifest_path.parent / "payload"
    identity = canonical(
        {
            "spec": load_data(manifest_path)["spec"],
            "sha256": manifest.sha256,
            "parser_version": manifest.parser_version,
            "name": manifest.original_name,
        }
    )
    if hashlib.sha256(identity.encode()).hexdigest() != manifest.id:
        raise InputError("snapshot manifest identity mismatch")
    if payload.stat().st_size != manifest.size_bytes or digest_file(payload) != manifest.sha256:
        raise InputError("snapshot payload hash or size mismatch")
    if manifest.parser_version != PARSER_VERSION:
        raise InputError("snapshot parser version is unsupported")
    return manifest, payload


def fetch_snapshot(
    workspace: Path, spec: SourceSpec, max_bytes: int = 256_000_000, query: str | None = None
) -> Path:
    if spec.source.reuse_class != "import":
        raise InputError("only import-class sources allow automated retrieval")
    if spec.download_url is None:
        raise InputError("source spec needs download_url")
    url = str(spec.download_url)
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.username or parts.password or parts.query:
        raise InputError("use a public HTTPS download URL without credentials or query parameters")
    if max_bytes <= 0:
        raise InputError("max_bytes must be positive")
    workspace.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=workspace) as temporary:
        name = Path(parts.path).name or "query.json"
        if spec.connector == "wikidata":
            if not query:
                raise InputError("Wikidata fetch requires an explicit bounded SPARQL query")
            name = "query.json"
        path = Path(temporary) / name
        headers = {
            "User-Agent": f"AllYourBase/{__version__} source-ingestion (review-first)",
            "Accept": "application/sparql-results+json" if query else "*/*",
        }
        try:
            with httpx.Client(timeout=60, follow_redirects=False) as client:
                params = {"query": query, "format": "json"} if query else None
                with client.stream("GET", url, headers=headers, params=params) as response:
                    response.raise_for_status()
                    size = 0
                    with path.open("xb") as output:
                        for block in response.iter_bytes():
                            size += len(block)
                            if size > max_bytes:
                                raise InputError(
                                    "source exceeds the configured download byte limit"
                                )
                            output.write(block)
        except httpx.HTTPError:
            raise InputError("source download failed; check endpoint and network") from None
        # Query text is part of the pinned input, so result provenance remains reproducible.
        if query:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["allyourbase_query"] = query
            path.write_text(canonical(data), encoding="utf-8")
        return save_snapshot(workspace, spec, path)
