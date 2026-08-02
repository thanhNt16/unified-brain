from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from .models import Note


class FrontmatterError(ValueError):
    pass


_REQUIRED = {"id", "kind", "title", "created", "updated", "status", "source_sha256", "refs", "tags", "provenance"}


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: _UniqueKeyLoader, node: yaml.nodes.MappingNode, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError("while constructing a mapping", node.start_mark, "duplicate key", key_node.start_mark)
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("---\n"):
        raise FrontmatterError("missing frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise FrontmatterError("unterminated frontmatter")
    try:
        value = yaml.load(text[4:end], Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise FrontmatterError("invalid yaml") from exc
    if not isinstance(value, dict) or not _REQUIRED.issubset(value):
        raise FrontmatterError("missing required key")
    return value, text[end + 5 :]


def render_frontmatter(data: dict[str, object], body: str = "") -> str:
    if not isinstance(data, dict) or not _REQUIRED.issubset(data):
        raise FrontmatterError("missing required key")
    payload = yaml.safe_dump(
        dict(sorted(data.items())), sort_keys=True, allow_unicode=True, default_flow_style=False
    ).replace("\r\n", "\n")
    return "---\n" + payload + "---\n" + body.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"


def parse_note(text: str) -> tuple[Note, str]:
    data, body = parse_frontmatter(text)
    try:
        return Note.model_validate(data), body
    except ValidationError as exc:
        raise FrontmatterError("invalid note") from exc


def render_note(note: Note, body: str = "") -> str:
    return render_frontmatter(note.model_dump(mode="json", exclude={"body"}), body)
