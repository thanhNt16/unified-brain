import sqlite3

from kg.schema import CURRENT_VERSION, migrate


def test_projection_schema_is_current_and_idempotent() -> None:
    assert CURRENT_VERSION == 2
    conn = sqlite3.connect(":memory:")
    migrate(conn)
    migrate(conn)
    assert conn.execute("select value from meta where key='schema_version'").fetchone()[0] == str(CURRENT_VERSION)
    names = {row[0] for row in conn.execute("select name from sqlite_master where type in ('table','view')")}
    assert {"meta", "notes", "edges", "notes_fts", "vec_features", "doc_norms", "deleted_notes"} <= names
    assert conn.execute("pragma foreign_keys").fetchone()[0] == 1
    assert conn.execute("pragma synchronous").fetchone()[0] == 2
