import pytest
from pydantic import ValidationError

from kg.models import DreamOp, Edge, Note, NoteStatus, Proposal, ProposedDiff, Relation

BASE = {
    "id": "nt_1234567890abcdef",
    "kind": "concept",
    "title": "Graph",
    "created": "2026-08-02T00:00:00Z",
    "updated": "2026-08-02T00:00:00Z",
    "status": "draft",
    "source_sha256": "a" * 64,
    "refs": [],
    "tags": [],
    "provenance": [],
}


def test_enums_and_strict_note() -> None:
    assert [x.value for x in Relation] == [
        "depends_on",
        "causes",
        "supports",
        "contradicts",
        "supersedes",
        "mentions",
        "related_to",
    ]
    assert [x.value for x in NoteStatus] == ["draft", "verified", "superseded", "tombstone"]
    assert Note(**BASE).kind == "concept"
    try:
        Note(**BASE, unexpected=True)
        raise AssertionError("extra field accepted")
    except ValidationError:
        pass


def test_proposal_caps_and_edge_types() -> None:
    edge = Edge(src=BASE["id"], dst="nt_fedcba9876543210", relation="causes", confidence=0.5)
    p = Proposal(schema_version=1, source_sha256="b" * 64, notes=[Note(**BASE)], edges=[edge])
    assert p.edges[0].relation is Relation.causes
    try:
        Edge(src="a", dst="b", relation="bad", confidence=2)
        raise AssertionError("invalid edge accepted")
    except ValidationError:
        pass


def test_dream_diff_strict_shape() -> None:
    op = DreamOp(op="drop", id=BASE["id"], reason="stale", evidence=["x"], pass_name="stale")
    diff = ProposedDiff(id="df_1234567890abcdef", status="proposed", operations=[op])
    assert diff.operations[0].pass_name == "stale"


def test_open_q_pass_name_and_operations_key_required() -> None:
    op = DreamOp(op="drop", id=BASE["id"], reason="question", evidence=[], pass_name="open-q")
    assert (
        ProposedDiff(id="df_1234567890abcdef", status="proposed", operations=[op]).operations[0].pass_name == "open-q"
    )
    with pytest.raises(ValidationError):
        ProposedDiff(id="df_1234567890abcdef", status="proposed", ops=[op])
