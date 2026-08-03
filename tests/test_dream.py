import sqlite3

from kg import dream, projection, schema
from kg.models import Edge, Note


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    schema.migrate(conn)
    return conn


def _note(
    conn: sqlite3.Connection,
    nid: str,
    title: str,
    kind: str = "fact",
    body: str = "",
    status: str = "verified",
    updated: str = "2026-01-01T00:00:00Z",
    tags: list[str] | None = None,
    supersedes: str | None = None,
    source: str = "x",
) -> None:
    projection.index_note(
        conn,
        Note(
            id=nid,
            kind=kind,  # type: ignore[arg-type]
            title=title,
            body=body,
            status=status,  # type: ignore[arg-type]
            supersedes=supersedes,
            source_sha256=source * 64,
            created="2026-01-01T00:00:00Z",
            updated=updated,
            tags=tags or [],
        ),
        body,
    )
    conn.commit()


def test_dedup_finds_same_normalized_title() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa", "Postgres Primary Store")
    _note(conn, "nt_bbbbbbbbbbbbbbbb", "postgres  primary store")
    diff = dream.run(conn, None, passes=("dedup",))
    assert any(op.op == "supersede" for op in diff.operations)


def test_deterministic_diff_id() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa", "Duplicate Title")
    _note(conn, "nt_bbbbbbbbbbbbbbbb", "duplicate title")
    d1 = dream.run(conn, None, passes=("dedup",))
    d2 = dream.run(conn, None, passes=("dedup",))
    assert d1.id == d2.id
    assert d1.id.startswith("df_") and len(d1.id) == 19


def test_contradiction_pass_finds_negation_pair() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa", "Alpha", body="system is online", tags=["prod"])
    _note(conn, "nt_bbbbbbbbbbbbbbbb", "Beta", body="system is not online", tags=["prod"])
    diff = dream.run(conn, None, passes=("contradiction",))
    assert any(op.op == "drop" and op.pass_name == "contradiction" for op in diff.operations)


def test_supersede_pass_flags_target() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa", "Old")
    _note(conn, "nt_bbbbbbbbbbbbbbbb", "New", supersedes="nt_aaaaaaaaaaaaaaaa")
    diff = dream.run(conn, None, passes=("supersede",))
    assert any(op.id == "nt_aaaaaaaaaaaaaaaa" and op.op == "supersede" for op in diff.operations)


def test_stale_pass_flags_old_isolated_note() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa", "Old", updated="2000-01-01T00:00:00Z")
    _note(conn, "nt_bbbbbbbbbbbbbbbb", "Fresh", updated="2099-01-01T00:00:00Z")
    diff = dream.run(conn, None, passes=("stale",))
    flagged = {op.id for op in diff.operations if op.pass_name == "stale"}
    assert flagged == {"nt_aaaaaaaaaaaaaaaa"}


def test_orphan_pass_flags_disconnected_note() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa", "Isolated")
    _note(conn, "nt_bbbbbbbbbbbbbbbb", "Connected")
    projection.project_edge(conn, Edge(src="nt_bbbbbbbbbbbbbbbb", relation="causes", dst="nt_aaaaaaaaaaaaaaaa", confidence=1.0))
    projection.project_edge(conn, Edge(src="nt_cccccccccccccccc", relation="causes", dst="nt_bbbbbbbbbbbbbbbb", confidence=1.0))
    _note(conn, "nt_cccccccccccccccc", "Connector")
    _note(conn, "nt_dddddddddddddddd", "Isolated")
    conn.commit()
    diff = dream.run(conn, None, passes=("orphan",))
    orphaned = {op.id for op in diff.operations if op.pass_name == "orphan"}
    assert orphaned == {"nt_dddddddddddddddd"}


def test_open_question_pass_flags_question_signals() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa", "What is the answer?", body="question body")
    _note(conn, "nt_bbbbbbbbbbbbbbbb", "Normal")
    diff = dream.run(conn, None, passes=("open-q",))
    flagged = {op.id for op in diff.operations if op.pass_name == "open-q"}
    assert flagged == {"nt_aaaaaaaaaaaaaaaa"}


def test_open_question_pass_does_not_flag_plain_summary() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa", "Postgres Summary", kind="summary", body="summary body")
    diff = dream.run(conn, None, passes=("open-q",))
    assert diff.operations == []


def test_contradiction_pass_merges_duplicate_negation_evidence() -> None:
    conn = _conn()
    _note(conn, "nt_0000000000000001", "Negative one", body="system is not online", tags=["prod"])
    _note(conn, "nt_0000000000000002", "Negative two", body="system is not online", tags=["prod"])
    _note(conn, "nt_0000000000000003", "Positive", body="system is online", tags=["prod"])
    diff = dream.run(conn, None, passes=("contradiction",))
    ops = [op for op in diff.operations if op.pass_name == "contradiction"]
    assert len(ops) == 1
    assert ops[0].id == "nt_0000000000000003"
    assert ops[0].evidence == ["nt_0000000000000001", "nt_0000000000000002"]


def test_contradiction_pass_deduplicates_same_loser() -> None:
    conn = _conn()
    _note(conn, "nt_0000000000000001", "Negative one", body="system is not online", tags=["prod"])
    _note(conn, "nt_0000000000000002", "Negative two", body="system is not online", tags=["prod"])
    _note(conn, "nt_0000000000000003", "Positive", body="system is online", tags=["prod"])
    diff = dream.run(conn, None, passes=("contradiction",))
    ids = [op.id for op in diff.operations]
    assert len(ids) == len(set(ids))


def test_community_pass_flags_dense_cluster() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa", "A")
    _note(conn, "nt_bbbbbbbbbbbbbbbb", "B")
    _note(conn, "nt_cccccccccccccccc", "C")
    projection.project_edge(conn, Edge(src="nt_aaaaaaaaaaaaaaaa", relation="related_to", dst="nt_bbbbbbbbbbbbbbbb", confidence=0.9))
    projection.project_edge(conn, Edge(src="nt_bbbbbbbbbbbbbbbb", relation="related_to", dst="nt_cccccccccccccccc", confidence=0.9))
    conn.commit()
    diff = dream.run(conn, None, passes=("community",))
    flagged = {op.id for op in diff.operations if op.pass_name == "community"}
    assert "nt_bbbbbbbbbbbbbbbb" in flagged or "nt_cccccccccccccccc" in flagged


def test_all_passes_find_their_fixtures() -> None:
    conn = _conn()
    _note(conn, "nt_aaaaaaaaaaaaaaaa", "Duplicate Title")
    _note(conn, "nt_bbbbbbbbbbbbbbbb", "duplicate  title")
    _note(conn, "nt_cccccccccccccccc", "Old", updated="2000-01-01T00:00:00Z")
    _note(conn, "nt_dddddddddddddddd", "Question?", body="q")
    diff = dream.run(conn, None)
    pass_names = {op.pass_name for op in diff.operations}
    assert "dedup" in pass_names
    assert "orphan" in pass_names  # all four isolated => orphans
    assert "stale" in pass_names
    assert "open-q" in pass_names


def test_unknown_pass_rejected() -> None:
    conn = _conn()
    try:
        dream.run(conn, None, passes=("teleport",))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
