from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from .frontmatter import parse_frontmatter, render_frontmatter
from .ids import diff_id
from .storage import Lock, Vault, atomic_write

_VALID_ACTIONS = {None, "approve", "reject"}
_VALID_OPS = {"drop", "supersede"}


def review(vault: Vault | Path, diff_path: Path, *, action: str | None = None) -> dict[str, object]:
    if action not in _VALID_ACTIONS:
        raise ValueError("action must be approve, reject, or None")
    vault_obj = vault if isinstance(vault, Vault) else Vault(Path(vault))
    path = Path(diff_path)
    _validate_path(vault_obj, path)
    data = _read_diff(path)
    diff_id_value, status, operations = _validate_diff(data, path)
    if status != "proposed":
        return {"id": diff_id_value, "status": status, "applied": 0, "note": "already decided"}
    if action is None:
        return {"id": diff_id_value, "status": status, "operations": operations, "applied": 0}
    with Lock(vault_obj):
        # Re-read under the writer lock so concurrent decisions become idempotent.
        current = _read_diff(path)
        diff_id_value, status, operations = _validate_diff(current, path)
        if status != "proposed":
            return {"id": diff_id_value, "status": status, "applied": 0, "note": "already decided"}
        if action == "reject":
            _write_diff_status(path, current, "rejected")
            from .storage import ContractLog

            ContractLog(vault_obj.contract_log).append(  # type: ignore[arg-type]
                "kg", "review", {"diff": diff_id_value, "action": "reject"}, {"ok": True}
            )
            return {"id": diff_id_value, "status": "rejected", "applied": 0}
        applied = _approve(vault_obj, path, current, diff_id_value, operations)
        from .storage import ContractLog

        ContractLog(vault_obj.contract_log).append(  # type: ignore[arg-type]
            "kg", "review", {"diff": diff_id_value, "action": "approve"}, {"ok": True}
        )
        return {"id": diff_id_value, "status": "approved", "applied": applied}


def _validate_path(vault: Vault, path: Path) -> None:
    assert vault.kg is not None
    dreams = (vault.kg / "dreams").resolve()
    try:
        inside = path.resolve().is_relative_to(dreams)
    except OSError as exc:
        raise ValueError("diff_path") from exc
    if not inside or path.resolve() == dreams:
        raise ValueError("diff_path")


def _read_diff(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("diff_state") from exc
    if not isinstance(value, dict):
        raise TypeError("diff_state")
    return value


def _validate_diff(data: dict[str, Any], path: Path) -> tuple[str, str, list[dict[str, Any]]]:
    diff_value = data.get("id")
    status = data.get("status")
    operations = data.get("operations")
    if not isinstance(diff_value, str) or not isinstance(status, str) or not isinstance(operations, list):
        raise TypeError("diff_state")
    if path.stem != diff_value or re.fullmatch(r"df_[0-9a-f]{16}", diff_value) is None:
        raise ValueError("diff_state")
    if status not in {"proposed", "approved", "rejected"}:
        raise ValueError("diff_state")
    normalized: list[dict[str, Any]] = []
    for item in operations:
        if not isinstance(item, dict):
            raise TypeError("diff_state")
        op = item.get("op")
        nid = item.get("id")
        reason = item.get("reason")
        evidence = item.get("evidence", [])
        pass_name = item.get("pass_name")
        if op not in _VALID_OPS or not isinstance(nid, str) or not isinstance(reason, str):
            raise ValueError("diff_state")
        if not isinstance(evidence, list) or not all(isinstance(value, str) for value in evidence):
            raise ValueError("diff_state")
        if pass_name not in {"dedup", "contradiction", "supersede", "stale", "orphan", "open-q", "community"}:
            raise ValueError("diff_state")
        normalized.append(
            {"op": op, "id": nid, "reason": reason, "evidence": sorted(set(evidence)), "pass_name": pass_name}
        )
    normalized.sort(key=lambda item: (item["pass_name"], item["id"], item["op"], item["evidence"]))
    if diff_id(normalized) != diff_value:
        raise ValueError("diff_state")
    return diff_value, status, normalized


def _write_diff_status(path: Path, data: dict[str, Any], status: str) -> None:
    updated = dict(data)
    updated["status"] = status
    atomic_write(path, (json.dumps(updated, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))


def _approve(vault: Vault, path: Path, data: dict[str, Any], diff_value: str, operations: list[dict[str, Any]]) -> int:
    brain = vault.brain
    assert brain is not None
    db = brain / ".kg" / "brain.sqlite"
    conn = sqlite3.connect(db)
    staged: list[tuple[Path, bytes, bytes]] = []  # (note_path, original_bytes, new_bytes)
    applied = 0
    try:
        for operation in operations:
            note_id = operation["id"]
            row = conn.execute("SELECT kind FROM notes WHERE id=?", (note_id,)).fetchone()
            if row is None:
                raise ValueError("diff_state")
            note_path = brain / "notes" / str(row[0]) / f"{note_id}.md"
            try:
                original_bytes = note_path.read_bytes()
                metadata, body = parse_frontmatter(original_bytes.decode("utf-8"))
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                raise ValueError("diff_state") from exc
            metadata["status"] = "tombstone" if operation["op"] == "drop" else "superseded"
            staged.append((note_path, original_bytes, render_frontmatter(metadata, body).encode()))
            applied += 1
        # Canonical-file-first (spec §3): atomically replace every staged note,
        # then commit one SQLite projection transaction. A DB failure rolls every
        # canonical file back to its captured original so a rebuild cannot lose or
        # resurrect the approved decision. Diff status joins the same window.
        for note_path, _original, new_bytes in staged:
            atomic_write(note_path, new_bytes)
        try:
            conn.execute("BEGIN")
            for operation in operations:
                note_id = operation["id"]
                status = "tombstone" if operation["op"] == "drop" else "superseded"
                conn.execute("UPDATE notes SET status=? WHERE id=?", (status, note_id))
                conn.execute("DELETE FROM edges WHERE src=? OR dst=?", (note_id, note_id))
                conn.execute(
                    "INSERT OR REPLACE INTO deleted_notes(id,reason,diff_id,ts) VALUES(?,?,?,?)",
                    (note_id, operation["reason"], diff_value, time.time()),
                )
            _write_diff_status(path, data, "approved")
            conn.commit()
        except Exception:
            conn.rollback()
            # Restore canonical originals so DB and canonical truth stay aligned;
            # rebuild reads canonical and would otherwise resurrect the decision.
            for note_path, original, _new in staged:
                try:
                    atomic_write(note_path, original)
                except OSError:
                    pass
            raise
    finally:
        conn.close()
    return applied
