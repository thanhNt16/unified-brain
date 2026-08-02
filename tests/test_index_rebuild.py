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
