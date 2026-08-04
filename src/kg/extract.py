from __future__ import annotations

from pathlib import Path

from .models import Proposal
from .storage import Lock, Registry, Vault, atomic_write


def prepare_sources(vault: Vault, source_path: Path) -> dict[str, object]:
    brain = vault.brain
    raw = vault.raw
    assert brain is not None and raw is not None
    source_path = Path(source_path).resolve()
    if source_path.is_symlink():
        raise ValueError("path_forbidden: symlink source")
    if source_path.is_dir():
        paths = sorted(path for path in source_path.rglob("*") if path.is_file() and not path.is_symlink())
    elif source_path.is_file():
        paths = [source_path]
    else:
        raise ValueError("not_found: source does not exist")
    registry = Registry(vault)
    rows = {str((brain / str(row["raw_path"])).resolve()): row for row in registry.read() if row.get("raw_path")}
    sources: list[dict[str, object]] = []
    for path in paths:
        row = rows.get(str(path.resolve()))
        if row is None:
            raise ValueError(f"unknown_source: raw source is not registered: {path}")
        digest = str(row["source_sha256"])
        sources.append(
            {
                "source_sha256": digest,
                "raw_path": str(row["raw_path"]),
                "original_name": row.get("original_name", path.name),
                "proposal_path": str(brain / ".kg" / "proposals" / f"{digest}.json"),
            }
        )
    if not sources:
        raise ValueError("limit_error: source contains no regular files")
    return {"sources": sources, "count": len(sources)}


def validate_proposal(vault: Vault, proposal: Proposal) -> Proposal:
    if not Registry(vault).contains(proposal.source_sha256):
        raise ValueError("unknown_source: source_sha256 is not registered")
    if len(proposal.notes) > 500 or len(proposal.edges) > 2000:
        raise ValueError("limit_error: proposal exceeds 500 notes or 2000 edges")
    ids = [note.id for note in proposal.notes]
    if len(ids) != len(set(ids)):
        raise ValueError("schema_validation: duplicate note id")
    existing = vault.live_note_ids()
    valid = set(ids) | existing
    for edge in proposal.edges:
        if edge.src not in valid or edge.dst not in valid:
            raise ValueError("dangling_edge: edge endpoint is not a proposal or live note")
    return proposal


def extract(vault: Vault, proposal_path: Path) -> dict[str, object]:
    try:
        proposal = Proposal.model_validate_json(proposal_path.read_text(encoding="utf-8"))
    except Exception as exc:
        if "too_long" in str(exc):
            raise ValueError("limit_error: proposal exceeds 500 notes or 2000 edges") from exc
        raise ValueError(f"schema_validation: {exc}") from exc
    validate_proposal(vault, proposal)
    brain = vault.brain
    assert brain is not None
    checkpoint = brain / ".kg" / "checkpoints" / f"{proposal.source_sha256}.json"
    preview = brain / ".kg" / "checkpoints" / f"{proposal.source_sha256}.preview.md"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with Lock(vault):
        atomic_write(checkpoint, proposal.model_dump_json(indent=2).encode())
        lines = [f"# Proposal {proposal.source_sha256}", "", f"Notes: {len(proposal.notes)}", f"Edges: {len(proposal.edges)}", ""]
        lines.extend(f"- {note.id}: {note.title}" for note in proposal.notes)
        atomic_write(preview, ("\n".join(lines) + "\n").encode())
    return {
        "source_sha256": proposal.source_sha256,
        "notes": len(proposal.notes),
        "edges": len(proposal.edges),
        "checkpoint": str(checkpoint),
    }
