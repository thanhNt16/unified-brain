import sqlite3

from kg import hashbow
from kg.models import Note
from kg.projection import DIM, extract, hashbow_features, index_note
from kg.schema import migrate


def test_hashbow_is_sparse_deterministic_and_searchable() -> None:
    assert hashbow_features("Alpha beta") == hashbow_features("Alpha beta")
    assert set(hashbow_features("Alpha beta")) <= set(range(16384))
    assert all(value != 0 for value in hashbow_features("Alpha beta").values())
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    note = Note(
        id="nt_aaaaaaaaaaaaaaaa",
        kind="concept",
        type=None,
        title="Alpha",
        status="verified",
        source_sha256="a" * 64,
        created="2026-01-01",
        updated="2026-01-01",
        refs=[],
        tags=[],
        provenance=[],
    )
    index_note(conn, note, "beta body")
    assert conn.execute("select title from notes_fts where notes_fts match 'beta'").fetchone()[0] == "Alpha"
    assert conn.execute("select count(*) from vec_features where note_id=?", (note.id,)).fetchone()[0] > 0
    assert conn.execute("select l2 from doc_norms where note_id=?", (note.id,)).fetchone()[0] > 0


def test_projection_uses_shared_hashbow_module() -> None:
    assert DIM == hashbow.DIM == 16384
    text = "Postgres primary store"
    assert extract(text) == hashbow.extract(text)
    assert hashbow_features is hashbow.extract
