import sqlite3

import pytest

from kg import projection, retrieval, schema
from kg.models import Edge


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    schema.migrate(conn)
    return conn


def _note(conn: sqlite3.Connection, nid: str) -> None:
    from kg.models import Note

    projection.index_note(
        conn,
        Note(
            id=nid,
            kind="fact",
            title=nid,
            source_sha256="x" * 64,
            created="2026-01-01T00:00:00Z",
            updated="2026-01-01T00:00:00Z",
        ),
        nid,
    )


def _edge(conn: sqlite3.Connection, src: str, rel: str, dst: str, confidence: float = 1.0) -> None:
    projection.project_edge(conn, Edge(src=src, relation=rel, dst=dst, confidence=confidence))
    conn.commit()


def test_validate_rejects_bad_params() -> None:
    with pytest.raises(ValueError):
        retrieval.validate_query_params(hops=5, direction="both", limit=10)
    with pytest.raises(ValueError):
        retrieval.validate_query_params(hops=2, direction="sideways", limit=10)
    with pytest.raises(ValueError):
        retrieval.validate_query_params(hops=2, direction="both", limit=0)
    with pytest.raises(ValueError):
        retrieval.validate_query_params(hops=2, direction="both", limit=10, relations=("teleport",))
    with pytest.raises(ValueError):
        retrieval.validate_query_params(hops=2, direction="both", limit=10, strategy="sneaky")


def test_traverse_respects_hops_and_direction() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa")
    _note(conn, "nt_bbbbbbbbbbbbbbbb")
    _note(conn, "nt_cccccccccccccccc")
    _edge(conn, "nt_aaaaaaaaaaaaaaaa", "causes", "nt_bbbbbbbbbbbbbbbb")
    _edge(conn, "nt_bbbbbbbbbbbbbbbb", "causes", "nt_cccccccccccccccc")
    out = retrieval.traverse(conn, ["nt_aaaaaaaaaaaaaaaa"], hops=1, relations=("causes",), direction="out", cap=100)
    assert "nt_bbbbbbbbbbbbbbbb" in out
    assert "nt_cccccccccccccccc" not in out
    out = retrieval.traverse(conn, ["nt_aaaaaaaaaaaaaaaa"], hops=2, relations=("causes",), direction="out", cap=100)
    assert "nt_cccccccccccccccc" in out
    assert out["nt_cccccccccccccccc"][0] == 2


def test_traverse_in_direction_follows_inbound_edges() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa")
    _note(conn, "nt_bbbbbbbbbbbbbbbb")
    _note(conn, "nt_cccccccccccccccc")
    _edge(conn, "nt_aaaaaaaaaaaaaaaa", "causes", "nt_bbbbbbbbbbbbbbbb")
    _edge(conn, "nt_bbbbbbbbbbbbbbbb", "causes", "nt_cccccccccccccccc")
    out = retrieval.traverse(conn, ["nt_cccccccccccccccc"], hops=1, relations=("causes",), direction="in", cap=100)
    assert "nt_bbbbbbbbbbbbbbbb" in out
    assert "nt_aaaaaaaaaaaaaaaa" not in out
    out = retrieval.traverse(conn, ["nt_cccccccccccccccc"], hops=2, relations=("causes",), direction="in", cap=100)
    assert "nt_aaaaaaaaaaaaaaaa" in out
    assert out["nt_aaaaaaaaaaaaaaaa"][0] == 2


def test_traverse_both_direction_and_cycle_bounded() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa")
    _note(conn, "nt_bbbbbbbbbbbbbbbb")
    _note(conn, "nt_cccccccccccccccc")
    _edge(conn, "nt_aaaaaaaaaaaaaaaa", "causes", "nt_bbbbbbbbbbbbbbbb")
    _edge(conn, "nt_bbbbbbbbbbbbbbbb", "causes", "nt_aaaaaaaaaaaaaaaa")  # cycle
    _edge(conn, "nt_bbbbbbbbbbbbbbbb", "causes", "nt_cccccccccccccccc")
    out = retrieval.traverse(conn, ["nt_aaaaaaaaaaaaaaaa"], hops=3, relations=("causes",), direction="both", cap=100)
    assert "nt_cccccccccccccccc" in out
    assert out["nt_cccccccccccccccc"][0] == 2
    # cycle must not starve expansion
    assert len(out) == 3


def test_traverse_cap_enforced() -> None:
    conn = _conn()
    _note(conn, "nt_ffff000000000000")
    for i in range(50):
        nid = f"nt_{i:016x}"
        _note(conn, nid)
        _edge(conn, "nt_ffff000000000000", "mentions", nid)
    out = retrieval.traverse(conn, ["nt_ffff000000000000"], hops=1, relations=("mentions",), direction="out", cap=10)
    assert len(out) <= 10


def test_traverse_unknown_seed_is_empty() -> None:
    conn = _conn()
    assert retrieval.traverse(conn, ["nt_9999999999999999"], hops=1, relations=("causes",), direction="out") == {}


def test_traverse_cap_bounds_recursive_work_on_hub() -> None:
    conn = _conn()
    root = "nt_ffffffffffffffff"
    _note(conn, root)
    for i in range(10_000):
        nid = f"nt_{i:016x}"
        _note(conn, nid)
        _edge(conn, root, "mentions", nid)
    callbacks = 0

    def progress() -> int:
        nonlocal callbacks
        callbacks += 1
        return 0

    conn.set_progress_handler(progress, 1_000)
    out = retrieval.traverse(conn, [root], hops=1, relations=("mentions",), direction="out", cap=10)
    conn.set_progress_handler(None, 0)
    assert len(out) == 10
    # The recursive CTE cap must stop expansion; the old post-GROUP BY LIMIT
    # expanded all 10,000 leaves (>500,000 callbacks at this interval).
    assert callbacks < 10_000


def test_traverse_cap_counts_unique_nodes_after_duplicate_depth_rows() -> None:
    conn = _conn()
    ids = [f"nt_{i:016x}" for i in range(5)]
    for nid in ids:
        _note(conn, nid)
    _edge(conn, ids[0], "mentions", ids[1])
    _edge(conn, ids[0], "mentions", ids[2])
    _edge(conn, ids[1], "mentions", ids[2])
    _edge(conn, ids[1], "mentions", ids[3])
    _edge(conn, ids[2], "mentions", ids[4])
    out = retrieval.traverse(conn, [ids[0]], hops=3, relations=("mentions",), direction="out", cap=5)
    assert list(out) == ids
    assert len(out) == 5


def test_traverse_multi_seed_deduplicates_before_cap() -> None:
    conn = _conn()
    seed_a, seed_b, target = "nt_0000000000000001", "nt_0000000000000002", "nt_0000000000000003"
    for nid in (seed_a, seed_b, target):
        _note(conn, nid)
    _edge(conn, seed_a, "mentions", target)
    _edge(conn, seed_b, "mentions", target)
    out = retrieval.traverse(conn, [seed_a, seed_b], hops=1, relations=("mentions",), direction="out", cap=3)
    assert set(out) == {seed_a, seed_b, target}
    assert out[seed_a][0] == 0 and out[seed_b][0] == 0 and out[target][0] == 1
