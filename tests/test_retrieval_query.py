import sqlite3

from kg import projection, retrieval, schema
from kg.models import Edge, Note


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    schema.migrate(conn)
    return conn


def _note(conn: sqlite3.Connection, nid: str, title: str, body: str = "") -> None:
    projection.index_note(
        conn,
        Note(
            id=nid,
            kind="fact",
            title=title,
            source_sha256="x" * 64,
            created="2026-01-01T00:00:00Z",
            updated="2026-01-01T00:00:00Z",
        ),
        body,
    )
    conn.commit()


def test_adaptive_query_returns_exact_result_fields() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa", "Postgres primary", "Postgres is the primary store")
    _note(conn, "nt_bbbbbbbbbbbbbbbb", "Failover", "failover to replica")
    projection.project_edge(conn, Edge(src="nt_aaaaaaaaaaaaaaaa", relation="causes", dst="nt_bbbbbbbbbbbbbbbb", confidence=1.0))
    conn.commit()
    result = retrieval.query(conn, None, "Postgres", strategy="adaptive", hops=2, relations=("causes",), direction="out", limit=10)
    assert result["strategy_used"] == "adaptive"
    assert "seed_counts" in result and "visited_count" in result
    top = result["results"][0]
    assert set(top) == {
        "id", "title", "kind", "score", "ppr_score", "seed_ranks", "depth", "paths", "sources", "evidence", "snippet", "path"
    }


def test_lexical_strategy_does_not_use_vector_or_graph() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa", "Postgres", "primary store")
    result = retrieval.query(conn, None, "Postgres", strategy="lexical", hops=2, relations=("causes",), direction="both", limit=1)
    assert result["strategy_used"] == "lexical"
    assert result["seed_counts"]["vector"] == 0
    assert result["seed_counts"]["graph"] == 0


def test_context_pack_respects_budget() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa", "Long", "x" * 200000)
    result = retrieval.query(conn, None, "Long", strategy="lexical", hops=0, relations=(), direction="both", limit=1)
    packed = retrieval.pack_context(conn, result["results"], token_budget=1000)
    assert "[truncated]" in packed


def test_context_pack_single_oversized_result_stays_under_budget() -> None:
    import math

    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa", "Huge", "x" * 130000)
    result = retrieval.query(conn, None, "Huge", strategy="lexical", hops=0, relations=(), direction="both", limit=1)
    packed = retrieval.pack_context(conn, result["results"])  # default 32,000-token budget
    assert "…[truncated]" in packed
    assert math.ceil(len(packed) / 4) <= 32000


def test_query_validates_strategy_relations_and_direction() -> None:
    conn = _conn()
    for kwargs in (
        {"strategy": "vector"},
        {"relations": ("bogus",)},
        {"direction": "sideways"},
        {"hops": 5},
    ):
        try:
            retrieval.query(conn, None, "x", **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(kwargs)
