from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .frontmatter import parse_note
from .hashbow import DIM, extract, l2
from .models import Edge, Note
from .schema import migrate
from .storage import Vault

__all__ = ["DIM", "extract", "hashbow_features", "index_all", "index_note", "project_edge", "project_proposal", "rebuild"]
hashbow_features = extract


def index_note(conn: sqlite3.Connection, note: Note, body: str) -> None:
    frontmatter = note.model_dump_json(exclude={"body"})
    tags = json.dumps(note.tags, sort_keys=True)
    conn.execute(
        "insert into notes(id,kind,type,title,body,tags_json,frontmatter_json,status,supersedes,source_sha256,created,updated) "
        "values(?,?,?,?,?,?,?,?,?,?,?,?) on conflict(id) do update set "
        "kind=excluded.kind,type=excluded.type,title=excluded.title,body=excluded.body,tags_json=excluded.tags_json,"
        "frontmatter_json=excluded.frontmatter_json,status=excluded.status,supersedes=excluded.supersedes,"
        "source_sha256=excluded.source_sha256,created=excluded.created,updated=excluded.updated",
        (note.id, note.kind, note.type, note.title, body, tags, frontmatter, note.status, note.supersedes, note.source_sha256, note.created, note.updated),
    )
    conn.execute("delete from vec_features where note_id=?", (note.id,))
    conn.execute("delete from doc_norms where note_id=?", (note.id,))
    values = extract(note.title + " " + body)
    norm = l2(values)
    conn.executemany(
        "insert into vec_features(feature,note_id,weight) values(?,?,?)",
        ((feature, note.id, value) for feature, value in values.items()),
    )
    conn.execute("insert into doc_norms(note_id,l2) values(?,?)", (note.id, norm))
    if note.status in {"tombstone", "superseded"}:
        conn.execute(
            "insert into deleted_notes(id,reason,diff_id,ts) values(?,?,?,?) on conflict(id) do update set reason=excluded.reason,ts=excluded.ts",
            (note.id, note.status, None, note.updated),
        )
    else:
        conn.execute("delete from deleted_notes where id=?", (note.id,))


def project_edge(conn: sqlite3.Connection, edge: Edge) -> None:
    conn.execute(
        "insert into edges(src,dst,relation,confidence,evidence) values(?,?,?,?,?) "
        "on conflict(src,relation,dst) do update set confidence=excluded.confidence,evidence=excluded.evidence",
        (edge.src, edge.dst, edge.relation, edge.confidence, edge.evidence),
    )


def _note_paths(vault: Vault) -> list[Path]:
    brain = vault.brain
    assert brain is not None
    return sorted((brain / "notes").glob("*/*.md"))


def index_all(vault: Vault, conn: sqlite3.Connection) -> int:
    migrate(conn)
    brain = vault.brain
    assert brain is not None
    error_path = brain / ".kg" / "index-errors.jsonl"
    error_path.parent.mkdir(parents=True, exist_ok=True)
    errors = 0
    paths = _note_paths(vault)
    # Plain kg index must converge: purge projection rows for canonical notes that
    # were removed or are currently malformed before re-inserting the survivors.
    conn.execute("delete from vec_features")
    conn.execute("delete from doc_norms")
    conn.execute("delete from deleted_notes")
    conn.execute("delete from notes")
    with error_path.open("w", encoding="utf-8") as log:
        for path in paths:
            try:
                note, body = parse_note(path.read_text(encoding="utf-8"))
                index_note(conn, note, body)
            except (UnicodeDecodeError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
                errors += 1
                log.write(json.dumps({"code": "parse_error", "path": str(path), "message": str(exc)}, sort_keys=True) + "\n")
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return errors


def rebuild(vault: Vault) -> dict[str, int]:
    brain = vault.brain
    assert brain is not None
    db = brain / ".kg" / "brain.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    migrate(conn)
    # Drop in dependency order, then reset schema metadata so migration recreates tables.
    conn.executescript(
        """
        DROP TRIGGER IF EXISTS notes_ai;
        DROP TRIGGER IF EXISTS notes_ad;
        DROP TRIGGER IF EXISTS notes_au;
        DROP TABLE IF EXISTS notes_fts;
        DROP TABLE IF EXISTS vec_features;
        DROP TABLE IF EXISTS doc_norms;
        DROP TABLE IF EXISTS deleted_notes;
        DROP TABLE IF EXISTS edges;
        DROP TABLE IF EXISTS notes;
        DELETE FROM meta WHERE key = 'schema_version';
        """
    )
    conn.commit()
    migrate(conn)
    errors = index_all(vault, conn)
    conn.close()
    total = len(_note_paths(vault))
    return {"errors": errors, "notes": total - errors}


def project_proposal(conn: sqlite3.Connection, proposal: object, bodies: dict[str, str]) -> None:
    from .models import Proposal

    validated = Proposal.model_validate(proposal)
    for note in validated.notes:
        index_note(conn, note, bodies[note.id])
    for edge in validated.edges:
        project_edge(conn, edge)
