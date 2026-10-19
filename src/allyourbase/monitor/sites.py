"""Category edits to sites.yaml with optimistic concurrency and preserved YAML text."""

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import yaml
from filelock import FileLock
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

from allyourbase.loading import InputError
from allyourbase.monitor.config import Location, Locations


class SitesChanged(InputError):
    pass


class SiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()

    def snapshot(self) -> dict[str, Any]:
        content = self.path.read_bytes()
        sites = Locations.model_validate(yaml.safe_load(content))
        return {
            "revision": hashlib.sha256(content).hexdigest(),
            "sites": [s.model_dump(mode="json") for s in sites.sites],
            "categories": sorted({s.category for s in sites.sites}, key=str.casefold),
        }

    def categorize(self, assignments: dict[str, str], revision: str) -> dict[str, Any]:
        lock_name = hashlib.sha256(str(self.path).encode()).hexdigest()
        with FileLock(str(Path(tempfile.gettempdir()) / f"allyourbase-sites-{lock_name}.lock")):
            content = self.path.read_bytes()
            if hashlib.sha256(content).hexdigest() != revision:
                raise SitesChanged("sites.yaml changed; reload the sites before saving")
            sites = Locations.model_validate(yaml.safe_load(content))
            indexed = {s.id: s for s in sites.sites}
            if not assignments or assignments.keys() - indexed.keys():
                raise InputError("select existing monitor sites to categorize")
            updated = {
                identifier: Location.model_validate(
                    indexed[identifier].model_dump() | {"category": label}
                )
                for identifier, label in assignments.items()
            }
            text = content.decode("utf-8-sig")
            tree = yaml.compose(text)
            if not isinstance(tree, MappingNode):
                raise InputError("invalid sites mapping")
            sequence = next(value for key, value in tree.value if key.value == "sites")
            if not isinstance(sequence, SequenceNode):
                raise InputError("invalid sites sequence")
            newline = "\r\n" if "\r\n" in text else "\n"
            edits = []
            for node in sequence.value:
                if not isinstance(node, MappingNode):
                    raise InputError("invalid site mapping")
                fields = {key.value: (key, value) for key, value in node.value}
                key, identifier = fields["id"]
                if identifier.value not in updated:
                    continue
                label = json.dumps(updated[identifier.value].category, ensure_ascii=False)
                if "category" in fields:
                    _, value = fields["category"]
                    if not isinstance(value, ScalarNode):
                        raise InputError("invalid category")
                    edits.append((value.start_mark.index, value.end_mark.index, label))
                elif node.flow_style:
                    position = node.end_mark.index - 1
                    edits.append((position, position, ", category: " + label))
                else:
                    position = text.find("\n", identifier.end_mark.index)
                    prefix = ""
                    if position < 0:
                        position = len(text)
                        prefix = newline
                    else:
                        position += 1
                    edits.append(
                        (
                            position,
                            position,
                            prefix + " " * key.start_mark.column + "category: " + label + newline,
                        )
                    )
            for start, end, replacement in sorted(edits, reverse=True):
                text = text[:start] + replacement + text[end:]
            expected = Locations(sites=[updated.get(s.id, s) for s in sites.sites])
            if Locations.model_validate(yaml.safe_load(text)) != expected:
                raise InputError("cannot safely edit this YAML layout")
            encoding = "utf-8-sig" if content.startswith(b"\xef\xbb\xbf") else "utf-8"
            with tempfile.NamedTemporaryFile(
                dir=self.path.parent, prefix=".sites-", suffix=".tmp", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(text.encode(encoding))
            try:
                temporary.replace(self.path)
            finally:
                temporary.unlink(missing_ok=True)
            return self.snapshot()
