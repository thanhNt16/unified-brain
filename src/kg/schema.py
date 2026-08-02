import sqlite3
from collections import OrderedDict

_FTS5_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts(rowid,title,body) VALUES (new.rowid,new.title,new.body);
END;
CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts,rowid,title,body) VALUES ('delete',old.rowid,old.title,old.body);
END;
CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
    INSERT INTO notes_fts(notes_fts,rowid,title,body) VALUES ('delete',old.rowid,old.title,old.body);
    INSERT INTO notes_fts(rowid,title,body) VALUES (new.rowid,new.title,new.body);
END;
"""

CURRENT_VERSION = 2
MIGRATIONS = OrderedDict(
    [
        (
            1,
            """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, kind TEXT NOT NULL, type TEXT, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', tags_json TEXT NOT NULL, frontmatter_json TEXT NOT NULL, status TEXT NOT NULL, supersedes TEXT, source_sha256 TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS edges(src TEXT NOT NULL, dst TEXT NOT NULL, relation TEXT NOT NULL, confidence REAL NOT NULL, evidence TEXT, PRIMARY KEY(src, relation, dst));
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(title, body, content='notes', content_rowid='rowid');
CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN INSERT INTO notes_fts(rowid,title,body) VALUES (new.rowid,new.title,new.body); END;
CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN INSERT INTO notes_fts(notes_fts,rowid,title,body) VALUES ('delete',old.rowid,old.title,old.body); END;
CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN INSERT INTO notes_fts(notes_fts,rowid,title,body) VALUES ('delete',old.rowid,old.title,old.body); INSERT INTO notes_fts(rowid,title,body) VALUES (new.rowid,new.title,new.body); END;
CREATE TABLE IF NOT EXISTS vec_features(feature INTEGER NOT NULL, note_id TEXT NOT NULL, weight REAL NOT NULL, PRIMARY KEY(feature, note_id));
CREATE TABLE IF NOT EXISTS doc_norms(note_id TEXT PRIMARY KEY, l2 REAL NOT NULL);
CREATE TABLE IF NOT EXISTS deleted_notes(id TEXT PRIMARY KEY, reason TEXT NOT NULL, diff_id TEXT, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS notes_status_idx ON notes(status);
CREATE INDEX IF NOT EXISTS notes_source_idx ON notes(source_sha256);
CREATE INDEX IF NOT EXISTS edges_src_idx ON edges(src);
CREATE INDEX IF NOT EXISTS edges_dst_idx ON edges(dst);
CREATE INDEX IF NOT EXISTS edges_relation_idx ON edges(relation);
""",
        ),
        (
            2,
            """-- M2 durable core: the v1 migration already creates the complete projection
-- (notes, edges, notes_fts, vec_features, doc_norms, deleted_notes); step 2
-- only advances the schema version to 2.
""",
        ),
    ]
)


def _repair_legacy_fts(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT type FROM sqlite_master WHERE name='notes_fts'").fetchone()
    if row and row[0] == "table":
        conn.execute("DROP TABLE notes_fts")
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(title, body, content='notes', content_rowid='rowid')"
    )
    conn.executescript(_FTS5_TRIGGERS)
    conn.execute("INSERT INTO notes_fts(notes_fts) VALUES ('rebuild')")


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("BEGIN")
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        current = int(row[0]) if row else 0
        if current > CURRENT_VERSION:
            raise RuntimeError("db_schema_newer")
        for version, sql in MIGRATIONS.items():
            if version > current:
                conn.executescript(sql)
                conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)", (str(version),))
        _repair_legacy_fts(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
