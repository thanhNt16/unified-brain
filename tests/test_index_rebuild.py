import json
import sqlite3
from pathlib import Path

from kg.projection import index_all, rebuild
from kg.schema import migrate
from kg.storage import Vault


def test_index_skips_corrupt_notes_and_rebuild_restores_projection(tmp_path: Path) -> None:
    vault = Vault(tmp_path)
    note_dir = tmp_path / ".brain" / "notes" / "concept"
    note_dir.mkdir(parents=True)
    (note_dir / "bad.md").write_text("not valid frontmatter", encoding="utf-8")
    (tmp_path / ".brain" / ".kg").mkdir(parents=True)
    conn = sqlite3.connect(tmp_path / ".brain" / ".kg" / "brain.sqlite")
    migrate(conn)
    assert index_all(vault, conn) == 1
    errors = (tmp_path / ".brain" / ".kg" / "index-errors.jsonl").read_text()
    assert json.loads(errors)["code"] == "parse_error"
    conn.close()
    rebuilt = rebuild(vault)
    assert rebuilt["errors"] == 1
    assert (tmp_path / ".brain" / ".kg" / "brain.sqlite").exists()


def test_index_all_skips_sqlite_error_note_and_logs(tmp_path: Path) -> None:
    vault = Vault(tmp_path)
    note_dir = tmp_path / ".brain" / "notes" / "concept"
    note_dir.mkdir(parents=True)
    template = "---\nid: {nid}\nkind: concept\ntitle: {title}\nstatus: verified\nsource_sha256: {sha}\ncreated: 2026-01-01\nupdated: 2026-01-01\nrefs: []\ntags: []\nprovenance: []\n---\nBody\n"
    (note_dir / "a.md").write_text(template.format(nid="nt_aaaaaaaaaaaaaaaa", title="Alpha", sha="a" * 64), encoding="utf-8")
    # Unmatched double quote makes the FTS5 trigger raise sqlite3.OperationalError.
    bad = template.replace("title: {title}", 'title: "broken').format(nid="nt_bbbbbbbbbbbbbbbb", title="x", sha="b" * 64)
    (note_dir / "b.md").write_text(bad, encoding="utf-8")
    (tmp_path / ".brain" / ".kg").mkdir(parents=True)
    conn = sqlite3.connect(tmp_path / ".brain" / ".kg" / "brain.sqlite")
    migrate(conn)
    errors = index_all(vault, conn)
    assert errors == 1
    assert {row[0] for row in conn.execute("select id from notes").fetchall()} == {"nt_aaaaaaaaaaaaaaaa"}
    conn.close()
    lines = (tmp_path / ".brain" / ".kg" / "index-errors.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["code"] == "parse_error"
    assert json.loads(lines[0])["path"].endswith("b.md")


def test_index_all_prunes_removed_notes(tmp_path: Path) -> None:
    vault = Vault(tmp_path)
    note_dir = tmp_path / ".brain" / "notes" / "concept"
    note_dir.mkdir(parents=True)
    template = "---\nid: {nid}\nkind: concept\ntitle: {title}\nstatus: verified\nsource_sha256: {sha}\ncreated: 2026-01-01\nupdated: 2026-01-01\nrefs: []\ntags: []\nprovenance: []\n---\nBody\n"
    (note_dir / "a.md").write_text(template.format(nid="nt_aaaaaaaaaaaaaaaa", title="Alpha", sha="a" * 64), encoding="utf-8")
    (note_dir / "b.md").write_text(template.format(nid="nt_bbbbbbbbbbbbbbbb", title="Beta", sha="b" * 64), encoding="utf-8")
    (tmp_path / ".brain" / ".kg").mkdir(parents=True)
    conn = sqlite3.connect(tmp_path / ".brain" / ".kg" / "brain.sqlite")
    migrate(conn)
    assert index_all(vault, conn) == 0
    (note_dir / "b.md").unlink()
    assert index_all(vault, conn) == 0
    assert conn.execute("select id from notes order by id").fetchall() == [("nt_aaaaaaaaaaaaaaaa",)]
    assert conn.execute("select count(*) from notes_fts").fetchone()[0] == 1
    conn.close()
