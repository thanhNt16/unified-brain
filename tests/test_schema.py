import sqlite3

import pytest

from kg.schema import CURRENT_VERSION, migrate


def test_fresh_migration_and_idempotency() -> None:
    c = sqlite3.connect(":memory:")
    migrate(c)
    first = c.execute("select value from meta where key='schema_version'").fetchone()[0]
    migrate(c)
    assert int(first) == CURRENT_VERSION
    assert c.execute("select name from sqlite_master where type='table' and name='notes'").fetchone()


def test_newer_database_refused() -> None:
    c = sqlite3.connect(":memory:")
    c.execute("create table meta(key text primary key,value text)")
    c.execute("insert into meta values('schema_version','999')")
    c.commit()
    with pytest.raises(RuntimeError, match="db_schema_newer"):
        migrate(c)


def test_notes_fts_is_external_content_fts5_with_triggers() -> None:
    c = sqlite3.connect(":memory:")
    migrate(c)
    sql = c.execute("select sql from sqlite_master where name='notes_fts'").fetchone()[0]
    assert sql.startswith("CREATE VIRTUAL TABLE")
    assert "USING fts5(" in sql and "content='notes'" in sql and "content_rowid='rowid'" in sql
    triggers = {row[0] for row in c.execute("select name from sqlite_master where type='trigger'")}
    assert {"notes_ai", "notes_ad", "notes_au"} <= triggers
    c.execute(
        "insert into notes(id,kind,title,body,tags_json,frontmatter_json,status,source_sha256,created,updated) "
        "values(?,?,?,?,?,?,?,?,?,?)",
        (
            "nt_0000000000000000",
            "concept",
            "Alpha",
            "beta body",
            "[]",
            "{}",
            "draft",
            "a" * 64,
            "2026-01-01",
            "2026-01-01",
        ),
    )
    assert c.execute("select title from notes_fts where notes_fts match 'beta'").fetchone()[0] == "Alpha"


def test_legacy_plain_fts_is_repaired_on_migration() -> None:
    c = sqlite3.connect(":memory:")
    c.executescript(
        """
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta VALUES ('schema_version', '1');
        CREATE TABLE notes(
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, type TEXT, title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '', tags_json TEXT NOT NULL,
            frontmatter_json TEXT NOT NULL, status TEXT NOT NULL, supersedes TEXT,
            source_sha256 TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL
        );
        CREATE TABLE notes_fts(rowid INTEGER PRIMARY KEY, title, body);
        INSERT INTO notes VALUES(
            'nt_0000000000000000', 'concept', NULL, 'Legacy', 'legacy beta', '[]', '{}',
            'draft', NULL, 'a' || printf('%064d', 0), '2026-01-01', '2026-01-01'
        );
        """
    )
    migrate(c)
    sql = c.execute("select sql from sqlite_master where name='notes_fts'").fetchone()[0]
    assert sql.startswith("CREATE VIRTUAL TABLE")
    assert c.execute("select title from notes_fts where notes_fts match 'beta'").fetchone()[0] == "Legacy"


def test_deleted_notes_diff_id_nullable() -> None:
    c = sqlite3.connect(":memory:")
    migrate(c)
    column = next(col for col in c.execute("pragma table_info(deleted_notes)") if col[1] == "diff_id")
    assert column[3] == 0
    c.execute("insert into deleted_notes(id,reason,diff_id,ts) values('nt_0000000000000000','x',NULL,'2026-01-01')")
    assert c.execute("select diff_id from deleted_notes").fetchone()[0] is None
