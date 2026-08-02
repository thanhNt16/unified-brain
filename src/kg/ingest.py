from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path

from .storage import Lock, Registry, Vault, atomic_write


def capture(vault: Vault, paths: Sequence[Path]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    brain = vault.brain
    assert brain is not None
    brain.mkdir(parents=True, exist_ok=True)
    with Lock(vault):
        registry = Registry(vault)
        for source in paths:
            source = Path(source)
            if source.is_symlink() or not source.is_file():
                raise ValueError("path_forbidden: regular files only")
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            suffix = re.sub(r"[^a-z0-9]+", "", source.suffix.lower().lstrip(".")) or "bin"
            raw = brain / "raw" / f"sha256.{digest}.{suffix}"
            deduped = registry.contains(digest)
            if not raw.exists():
                atomic_write(raw, data)
            row: dict[str, object] = {
                "source_sha256": digest,
                "raw_path": str(raw.relative_to(brain)),
                "original_name": source.name,
                "status": "deduped" if deduped else "captured",
            }
            registry.append(row)
            results.append(row)
    return results
