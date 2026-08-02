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
        target = "entities" if note.kind == "entity" else "summaries" if note.kind == "summary" else "concepts"
        rows.append(f"- [{note.title}]({target}/{note.id}.md) — `{note.id}` — {note.status.value}")
        target_dir = wiki / target
        atomic_write(target_dir / f"{note.id}.md", f"# {note.title}\n\nID: `{note.id}`\n\nStatus: {note.status.value}\n".encode())
    atomic_write(wiki / "index.md", ("\n".join(rows) + "\n").encode())
    # log.md derives from the canonical status history: current statuses and
    # supersedes chains, not an external journal.
    history = ["# Change Log", "", "Status history derived from canonical notes:", ""]
    for note, _ in notes:
        line = f"- {note.updated} `{note.id}` — {note.status.value}"
        if note.supersedes:
            line += f" (supersedes {note.supersedes})"
        history.append(line)
    atomic_write(wiki / "log.md", ("\n".join(history) + "\n").encode())
    return {"notes": len(notes)}
