import pytest

from kg.frontmatter import FrontmatterError, parse_frontmatter, render_frontmatter, parse_note, render_note
from kg.models import Note

DATA = {
    "id": "nt_1234567890abcdef",
    "kind": "concept",
    "title": "A/B",
    "created": "2026-08-02T00:00:00Z",
    "updated": "2026-08-02T00:00:00Z",
    "status": "draft",
    "source_sha256": "a" * 64,
    "refs": [],
    "tags": [],
    "provenance": [],
}


def test_round_trip_sorted_lf_trailing_newline() -> None:
    rendered = render_frontmatter(DATA, "Body\r\n")
    assert rendered.startswith("---\n") and rendered.endswith("\n") and "\r" not in rendered
    assert rendered.index("created:") < rendered.index("title:")
    parsed, body = parse_frontmatter(rendered)
    assert parsed == DATA and body == "Body\n"


def test_three_note_kinds_round_trip() -> None:
    for kind in ("entity", "fact", "summary"):
        note = DATA | {"kind": kind}
        assert parse_note(render_note(Note(**note), "x"))[0].kind == kind


def test_malformed_or_missing_keys_rejected() -> None:
    with pytest.raises(FrontmatterError):
        parse_frontmatter("not markdown")
    with pytest.raises(FrontmatterError):
        parse_frontmatter("---\nid: nt_1234567890abcdef\n---\n")
