from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path

from .storage import Lock, Registry, Vault, atomic_write


def _safe_suffix(suffix: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "", suffix.lower().lstrip("."))[:24] or "bin"


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
            try:
                data = source.read_bytes()
            except OSError as exc:
                raise ValueError(f"path_forbidden: unreadable: {source}") from exc
            digest = hashlib.sha256(data).hexdigest()
            suffix = _safe_suffix(source.suffix)
            raw = brain / "raw" / f"sha256.{digest}.{suffix}"
            if raw.exists() and raw.read_bytes() != data:
                raise ValueError("path_forbidden: raw object corrupted; refused to rewrite")
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
