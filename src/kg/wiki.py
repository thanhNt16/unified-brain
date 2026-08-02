from __future__ import annotations

import logging

from .frontmatter import FrontmatterError, parse_note
from .storage import Vault, atomic_write

_LOG = logging.getLogger(__name__)


def generate(vault: Vault) -> dict[str, int]:
    brain = vault.brain
    assert brain is not None
    notes = []
    for path in sorted((brain / "notes").glob("*/*.md")):
        try:
            note, body = parse_note(path.read_text(encoding="utf-8"))
        except (FrontmatterError, UnicodeDecodeError) as exc:
            _LOG.warning("skipping malformed note %s: %s", path, exc)
            continue
        notes.append((note, body))
    wiki = brain / "wiki"
    for directory in (wiki, wiki / "entities", wiki / "concepts", wiki / "summaries"):
        directory.mkdir(parents=True, exist_ok=True)
    rows = ["# Knowledge Graph", "", "## Notes", ""]
    for note, _ in notes:
        rows.append(f"- [{note.title}]({note.kind}s/{note.id}.md) — `{note.id}` — {note.status}")
        target_dir = wiki / ("entities" if note.kind == "entity" else "summaries" if note.kind == "summary" else "concepts")
        atomic_write(target_dir / f"{note.id}.md", f"# {note.title}\n\nID: `{note.id}`\n\nStatus: {note.status}\n".encode())
    atomic_write(wiki / "index.md", ("\n".join(rows) + "\n").encode())
    atomic_write(wiki / "log.md", b"# Change Log\n\nGenerated from canonical status history.\n")
    return {"notes": len(notes)}
