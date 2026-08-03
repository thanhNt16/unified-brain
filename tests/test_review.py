import json
import sqlite3
from pathlib import Path

import pytest

from kg import dream, review, schema
from kg.models import Note
from kg.storage import Vault


def _seed(vault: Vault) -> None:
    vault.kg.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(vault.kg / "brain.sqlite")
    schema.migrate(conn)
    from kg import projection

    projection.index_note(
        conn,
        Note(
            id="nt_aaaaaaaaaaaaaaaa",
            kind="fact",
            title="Old",
            status="verified",
            source_sha256="x" * 64,
            created="2026-01-01T00:00:00Z",
            updated="2026-01-01T00:00:00Z",
        ),
        "old body",
    )
    conn.commit()
    conn.close()
    note_dir = vault.brain / "notes" / "fact"
    note_dir.mkdir(parents=True)
    (note_dir / "nt_aaaaaaaaaaaaaaaa.md").write_text(
        "---\nid: nt_aaaaaaaaaaaaaaaa\nkind: fact\ntitle: Old\nstatus: verified\nsource_sha256: "
        + "x" * 64
        + "\ncreated: 2026-01-01T00:00:00Z\nupdated: 2026-01-01T00:00:00Z\nrefs: []\ntags: []\nprovenance: []\n---\nold body\n",
        encoding="utf-8",
    )


def _write_diff(root: Path, diff) -> Path:
    data = {
        "id": diff.id,
        "status": "proposed",
        "operations": [
            {
                "op": op.op,
                "id": op.id,
                "reason": op.reason,
                "evidence": op.evidence,
                "pass_name": op.pass_name,
            }
            for op in diff.operations
        ],
    }
    path = root / ".brain" / ".kg" / "dreams" / f"{diff.id}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    return path


def test_default_review_is_read_only(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir(parents=True)
    vault = Vault(root)
    _seed(vault)
    conn = sqlite3.connect(vault.kg / "brain.sqlite")
    diff = dream.run(conn, None, passes=("orphan",))
    conn.close()
    diff_path = _write_diff(root, diff)
    out = review.review(root, diff_path)
    assert out["status"] == "proposed"
    assert out["applied"] == 0
    assert json.loads(diff_path.read_text())["status"] == "proposed"


def test_approve_reject_are_mutually_exclusive(tmp_path: Path) -> None:
    diff_path = tmp_path / "d.json"
    diff_path.write_text('{"id":"df_0000000000000000","status":"proposed","operations":[]}')
    with pytest.raises(ValueError):
        review.review(tmp_path, diff_path, action="approve-reject")


def test_approve_applies_ops_transactionally(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir(parents=True)
    vault = Vault(root)
    _seed(vault)
    conn = sqlite3.connect(vault.kg / "brain.sqlite")
    from kg import projection

    projection.index_note(
        conn,
        Note(
            id="nt_bbbbbbbbbbbbbbbb",
            kind="fact",
            title="New",
            supersedes="nt_aaaaaaaaaaaaaaaa",
            source_sha256="x" * 64,
            created="2026-01-01T00:00:00Z",
            updated="2026-01-01T00:00:00Z",
        ),
        "new body",
    )
    projection.project_edge(conn, __import__("kg.models", fromlist=["Edge"]).Edge(
        src="nt_bbbbbbbbbbbbbbbb", relation="causes", dst="nt_aaaaaaaaaaaaaaaa", confidence=1.0
    ))
    conn.commit()
    conn.close()
    diff = dream.run(conn2 := sqlite3.connect(vault.kg / "brain.sqlite"), None, passes=("supersede",))
    conn2.close()
    diff_path = _write_diff(root, diff)
    out = review.review(root, diff_path, action="approve")
    assert out["status"] == "approved"
    assert out["applied"] >= 1
    conn = sqlite3.connect(vault.kg / "brain.sqlite")
    status = conn.execute("SELECT status FROM notes WHERE id='nt_aaaaaaaaaaaaaaaa'").fetchone()[0]
    assert status in {"superseded", "tombstone"}
    assert conn.execute("SELECT count(*) FROM deleted_notes WHERE id='nt_aaaaaaaaaaaaaaaa'").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM edges WHERE src='nt_aaaaaaaaaaaaaaaa' OR dst='nt_aaaaaaaaaaaaaaaa'").fetchone()[0] == 0
    conn.close()
    frontmatter_text = (root / ".brain" / "notes" / "fact" / "nt_aaaaaaaaaaaaaaaa.md").read_text()
    assert "status: superseded" in frontmatter_text or "status: tombstone" in frontmatter_text
    assert json.loads(diff_path.read_text())["status"] == "approved"


def test_reject_sets_status_and_never_touches_notes(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir(parents=True)
    vault = Vault(root)
    _seed(vault)
    conn = sqlite3.connect(vault.kg / "brain.sqlite")
    diff = dream.run(conn, None, passes=("orphan",))
    conn.close()
    diff_path = _write_diff(root, diff)
    out = review.review(root, diff_path, action="reject")
    assert out["status"] == "rejected"
    assert json.loads(diff_path.read_text())["status"] == "rejected"
    conn = sqlite3.connect(vault.kg / "brain.sqlite")
    assert conn.execute("SELECT status FROM notes WHERE id='nt_aaaaaaaaaaaaaaaa'").fetchone()[0] == "verified"
    conn.close()


def test_repeat_decisions_are_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir(parents=True)
    vault = Vault(root)
    _seed(vault)
    conn = sqlite3.connect(vault.kg / "brain.sqlite")
    diff = dream.run(conn, None, passes=("orphan",))
    conn.close()
    diff_path = _write_diff(root, diff)
    first = review.review(root, diff_path, action="reject")
    second = review.review(root, diff_path, action="reject")
    assert first["status"] == "rejected"
    assert second["status"] == "rejected"
    assert second["applied"] == 0


def test_review_rejects_outside_vault_and_hash_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir(parents=True)
    vault = Vault(root)
    _seed(vault)
    conn = sqlite3.connect(vault.kg / "brain.sqlite")
    diff = dream.run(conn, None, passes=("orphan",))
    conn.close()
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"id": diff.id, "status": "proposed", "operations": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        review.review(root, outside)
    diff_path = _write_diff(root, diff)
    tampered = json.loads(diff_path.read_text())
    tampered["operations"] = []
    diff_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError):
        review.review(root, diff_path)


def test_approve_db_failure_leaves_canonical_files_intact(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir(parents=True)
    vault = Vault(root)
    _seed(vault)
    conn = sqlite3.connect(vault.kg / "brain.sqlite")
    conn.execute(
        "CREATE TRIGGER fail_review_update BEFORE UPDATE OF status ON notes "
        "BEGIN SELECT RAISE(ABORT, 'db failure'); END"
    )
    conn.commit()
    conn.close()
    conn = sqlite3.connect(vault.kg / "brain.sqlite")
    diff = dream.run(conn, None, passes=("orphan",))
    conn.close()
    diff_path = _write_diff(root, diff)
    note_file = root / ".brain" / "notes" / "fact" / "nt_aaaaaaaaaaaaaaaa.md"
    original = note_file.read_text()
    with pytest.raises(sqlite3.Error, match="db failure"):
        review.review(root, diff_path, action="approve")
    assert note_file.read_text() == original
    conn = sqlite3.connect(vault.kg / "brain.sqlite")
    status = conn.execute("SELECT status FROM notes WHERE id='nt_aaaaaaaaaaaaaaaa'").fetchone()[0]
    assert status == "verified"
    conn.close()
    assert json.loads(diff_path.read_text())["status"] == "proposed"


def test_approve_canonical_failure_converges_via_rebuild(tmp_path: Path, monkeypatch) -> None:
    from kg import projection

    root = tmp_path / "vault"
    root.mkdir(parents=True)
    vault = Vault(root)
    _seed(vault)
    conn = sqlite3.connect(vault.kg / "brain.sqlite")
    diff = dream.run(conn, None, passes=("orphan",))
    conn.close()
    diff_path = _write_diff(root, diff)
    real_write = review.atomic_write

    def failing_note_write(path, data):
        if str(path).endswith(".md"):
            raise RuntimeError("canonical write failed")
        return real_write(path, data)

    monkeypatch.setattr(review, "atomic_write", failing_note_write)
    with pytest.raises(RuntimeError):
        review.review(root, diff_path, action="approve")
    monkeypatch.setattr(review, "atomic_write", real_write)
    # Canonical-file-first: a canonical write failure happens before the DB/diff
    # decision, so every surface remains proposed/verified and rebuild is a no-op.
    assert json.loads(diff_path.read_text())["status"] == "proposed"
    conn = sqlite3.connect(vault.kg / "brain.sqlite")
    assert conn.execute("SELECT status FROM notes WHERE id='nt_aaaaaaaaaaaaaaaa'").fetchone()[0] == "verified"
    conn.close()
    projection.rebuild(vault)
    conn = sqlite3.connect(vault.kg / "brain.sqlite")
    assert conn.execute("SELECT status FROM notes WHERE id='nt_aaaaaaaaaaaaaaaa'").fetchone()[0] == "verified"
    assert conn.execute("SELECT count(*) FROM deleted_notes WHERE id='nt_aaaaaaaaaaaaaaaa'").fetchone()[0] == 0
    conn.close()
