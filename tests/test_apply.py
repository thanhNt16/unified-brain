import json
import sqlite3
from pathlib import Path

import pytest

from kg.apply import apply_proposal
from kg.ingest import capture
from kg.storage import Vault


def _proposal(digest: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_sha256": digest,
        "notes": [
            {
                "id": "nt_aaaaaaaaaaaaaaaa",
                "kind": "concept",
                "type": None,
                "title": "Alpha",
                "status": "verified",
                "source_sha256": digest,
                "created": "2026-01-01",
                "updated": "2026-01-01",
                "refs": [],
                "tags": [],
                "provenance": [],
            }
        ],
        "edges": [],
    }


def test_apply_writes_note_and_projection(tmp_path: Path) -> None:
    vault = Vault(tmp_path)
    source = tmp_path / "source.txt"
    source.write_bytes(b"raw")
    digest = capture(vault, [source])[0]["source_sha256"]
    path = tmp_path / "proposal.json"
    path.write_text(json.dumps(_proposal(str(digest))), encoding="utf-8")
    result = apply_proposal(vault, path)
    assert result["notes"] == 1
    assert (tmp_path / ".brain" / "notes" / "concept" / "nt_aaaaaaaaaaaaaaaa.md").exists()
    conn = sqlite3.connect(tmp_path / ".brain" / ".kg" / "brain.sqlite")
    assert conn.execute("select title from notes where id='nt_aaaaaaaaaaaaaaaa'").fetchone()[0] == "Alpha"


def test_projection_failure_leaves_canonical_note_for_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = Vault(tmp_path)
    source = tmp_path / "source.txt"
    source.write_bytes(b"raw")
    digest = capture(vault, [source])[0]["source_sha256"]
    path = tmp_path / "proposal.json"
    path.write_text(json.dumps(_proposal(str(digest))), encoding="utf-8")
    import kg.apply

    monkeypatch.setattr(
        kg.apply,
        "project_proposal",
        lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError("injected")),
    )
    with pytest.raises(ValueError, match="index_errors: run kg index --rebuild"):
        apply_proposal(vault, path)
    assert (tmp_path / ".brain" / "notes" / "concept" / "nt_aaaaaaaaaaaaaaaa.md").exists()
    assert sqlite3.connect(tmp_path / ".brain" / ".kg" / "brain.sqlite").execute(
        "select count(*) from notes where id='nt_aaaaaaaaaaaaaaaa'"
    ).fetchone()[0] == 0
    assert __import__("kg.projection", fromlist=["rebuild"]).rebuild(vault)["notes"] == 1
