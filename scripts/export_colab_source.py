"""Export an allow-listed, hashed source ZIP outside the code repository."""

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.expanduser().resolve()
    if output.is_relative_to(root):
        parser.error("source archive must be outside the code repository")
    selected = (
        subprocess.check_output(
            [
                "git",
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
                "--",
                "src",
                "config",
                "schemas",
                "scripts",
                "docs/proposals",
                "README.md",
                "pyproject.toml",
                "uv.lock",
            ],
            cwd=root,
        )
        .decode()
        .split("\0")
    )
    files = sorted(
        {
            name
            for name in selected
            if name
            and Path(name).suffix
            in {
                ".py",
                ".yaml",
                ".json",
                ".geojson",
                ".md",
                ".toml",
                ".lock",
                ".html",
                ".rq",
                ".overpassql",
            }
        }
    )
    manifest = {
        "base_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root)
        .decode()
        .strip(),
        "files": {},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            content = (root / name).read_bytes()
            manifest["files"][name] = hashlib.sha256(content).hexdigest()
            archive.writestr(zipfile.ZipInfo(name), content)
        archive.writestr(
            zipfile.ZipInfo("source-manifest.json"), json.dumps(manifest, indent=2) + "\n"
        )
    temporary.replace(output)
    print(
        json.dumps(
            {
                "file": str(output),
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "source_files": len(files),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
