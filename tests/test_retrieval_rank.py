import sqlite3

from kg import projection, retrieval, schema
from kg.models import Edge


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    schema.migrate(conn)
    return conn


def test_rrf_fuses_rankings() -> None:
    scores = retrieval.rrf([["a", "b", "c"], ["c", "a", "b"]])
    # 'a' ranks 1 in both; 'c' ranks 3 then 1
    assert scores["a"] > scores["c"]
    assert scores["a"] > scores["b"]


def test_rrf_exact_weights() -> None:
    scores = retrieval.rrf([["x", "y"]])
    assert abs(scores["x"] - 1.0 / 61.0) < 1e-9
    assert abs(scores["y"] - 1.0 / 62.0) < 1e-9


def test_ppr_concentrates_on_well_connected() -> None:
    conn = _conn()
    from kg.models import Note

    for i, nid in enumerate(("nt_aaaaaaaaaaaaaaaa", "nt_bbbbbbbbbbbbbbbb", "nt_cccccccccccccccc")):
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
    projection.project_edge(conn, Edge(src="nt_aaaaaaaaaaaaaaaa", relation="causes", dst="nt_bbbbbbbbbbbbbbbb", confidence=1.0))
    projection.project_edge(conn, Edge(src="nt_bbbbbbbbbbbbbbbb", relation="causes", dst="nt_cccccccccccccccc", confidence=1.0))
    conn.commit()
    prior = {"nt_aaaaaaaaaaaaaaaa": 1.0}
    nodes = ["nt_aaaaaaaaaaaaaaaa", "nt_bbbbbbbbbbbbbbbb", "nt_cccccccccccccccc"]
    scores = retrieval.ppr(conn, nodes, prior)
    assert scores["nt_aaaaaaaaaaaaaaaa"] >= scores["nt_bbbbbbbbbbbbbbbb"]
    assert scores["nt_bbbbbbbbbbbbbbbb"] >= scores["nt_cccccccccccccccc"]


def test_ppr_deterministic() -> None:
    conn = _conn()
    prior = {"nt_aaaaaaaaaaaaaaaa": 1.0, "nt_bbbbbbbbbbbbbbbb": 0.0, "nt_cccccccccccccccc": 0.0}
    nodes = ["nt_aaaaaaaaaaaaaaaa", "nt_bbbbbbbbbbbbbbbb", "nt_cccccccccccccccc"]
    assert retrieval.ppr(conn, nodes, prior) == retrieval.ppr(conn, nodes, prior)


def test_ppr_relation_weights_scale() -> None:
    conn = _conn()
    from kg.models import Note

    for nid in ("nt_aaaaaaaaaaaaaaaa", "nt_bbbbbbbbbbbbbbbb", "nt_cccccccccccccccc", "nt_dddddddddddddddd"):
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
    projection.project_edge(conn, Edge(src="nt_aaaaaaaaaaaaaaaa", relation="causes", dst="nt_bbbbbbbbbbbbbbbb", confidence=1.0))
    projection.project_edge(conn, Edge(src="nt_aaaaaaaaaaaaaaaa", relation="contradicts", dst="nt_cccccccccccccccc", confidence=1.0))
    projection.project_edge(conn, Edge(src="nt_aaaaaaaaaaaaaaaa", relation="mentions", dst="nt_dddddddddddddddd", confidence=1.0))
    conn.commit()
    nodes = ["nt_aaaaaaaaaaaaaaaa", "nt_bbbbbbbbbbbbbbbb", "nt_cccccccccccccccc", "nt_dddddddddddddddd"]
    scores = retrieval.ppr(conn, nodes, {"nt_aaaaaaaaaaaaaaaa": 1.0})
    assert scores["nt_bbbbbbbbbbbbbbbb"] > scores["nt_cccccccccccccccc"]
    assert scores["nt_cccccccccccccccc"] > scores["nt_dddddddddddddddd"]
