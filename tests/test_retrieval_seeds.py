import sqlite3

from kg import projection, retrieval, schema
from kg.models import Note


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    schema.migrate(conn)
    return conn


def _note(nid: str, title: str, body: str = "") -> Note:
    return Note(
        id=nid,
        kind="fact",
        title=title,
        source_sha256="x" * 64,
        created="2026-01-01T00:00:00Z",
        updated="2026-01-01T00:00:00Z",
    )


def test_lexical_seed_handles_fts_punctuation() -> None:
    conn = _conn()
    projection.index_note(conn, _note("nt_aaaaaaaaaaaaaaaa", "Postgres (primary) store"), "Postgres primary")
    conn.commit()
    ids = retrieval.lexical_seed(conn, '"foo: (', limit=10)
    assert isinstance(ids, list)


def test_lexical_seed_ranks_relevant_note_first() -> None:
    conn = _conn()
    projection.index_note(conn, _note("nt_aaaaaaaaaaaaaaaa", "Postgres", "Postgres is the primary store"), "Postgres store")
    projection.index_note(conn, _note("nt_bbbbbbbbbbbbbbbb", "Garden", "tomatoes and basil in the garden"), "garden")
    conn.commit()
    ids = retrieval.lexical_seed(conn, "Postgres", limit=5)
    assert ids[0][0] == "nt_aaaaaaaaaaaaaaaa"


def test_vector_seed_ranks_relevant_note_first() -> None:
    conn = _conn()
    projection.index_note(conn, _note("nt_aaaaaaaaaaaaaaaa", "Postgres primary store", "Postgres"), "Postgres is the primary store")
    projection.index_note(conn, _note("nt_bbbbbbbbbbbbbbbb", "Garden", "tomatoes"), "tomatoes and basil in the garden")
    conn.commit()
    ids = retrieval.vector_seed(conn, "Postgres primary store", limit=5)
    assert ids[0][0] == "nt_aaaaaaaaaaaaaaaa"


def test_vector_seed_matches_independent_hashbow() -> None:
    from kg import hashbow

    conn = _conn()
    projection.index_note(conn, _note("nt_aaaaaaaaaaaaaaaa", "Postgres store", "Postgres"), "Postgres is the store")
    conn.commit()
    ids = retrieval.vector_seed(conn, "Postgres store", limit=5)
    assert ids
    qv = hashbow.extract("Postgres store")
    row = conn.execute(
        "select vf.feature, vf.weight from vec_features vf where vf.note_id='nt_aaaaaaaaaaaaaaaa'"
    ).fetchall()
    expected = hashbow.cosine(qv, dict(row))
    assert abs(ids[0][1] - expected) < 1e-9
