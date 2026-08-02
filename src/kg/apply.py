from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .extract import validate_proposal
from .frontmatter import render_note
from .models import Proposal
from .projection import index_note, project_edge
from .schema import migrate
from .storage import Lock, Vault, atomic_write, contract_log


def project_proposal(conn: sqlite3.Connection, proposal: Proposal, bodies: dict[str, str]) -> None:
    for note in proposal.notes:
        index_note(conn, note, bodies[note.id])
    for edge in proposal.edges:
        project_edge(conn, edge)


def apply_proposal(vault: Vault, proposal_path: Path) -> dict[str, object]:
    try:
        proposal = Proposal.model_validate_json(proposal_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"schema_validation: {exc}") from exc
    brain = vault.brain
    assert brain is not None
    with Lock(vault):
        validate_proposal(vault, proposal)
        staged: dict[str, tuple[Path, bytes]] = {}
        bodies = {note.id: note.body for note in proposal.notes}
        for note in proposal.notes:
            target = brain / "notes" / note.kind / f"{note.id}.md"
            staged[note.id] = (target, render_note(note, bodies[note.id]).encode("utf-8"))
        for target, data in staged.values():
            atomic_write(target, data)
        db = brain / ".kg" / "brain.sqlite"
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db)
        migrate(conn)
        try:
            conn.execute("BEGIN")
            project_proposal(conn, proposal, bodies)
            conn.commit()
        except Exception:
            conn.rollback()
            conn.close()
            raise
        conn.close()
        result = {"notes": len(proposal.notes), "edges": len(proposal.edges), "source_sha256": proposal.source_sha256}
        atomic_write(
            brain / ".kg" / "manifest.json",
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode(),
        )
        envelope = {"ok": True, "data": result}
        contract_log(vault, "kg", "apply", {"proposal": str(proposal_path)}, envelope, result)
        return result
