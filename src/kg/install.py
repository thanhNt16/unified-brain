from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .harness import render_all


class InstallError(Exception):
    pass


def _owned(existing: str, generated: str) -> bool:
    marker = next((line for line in generated.splitlines() if line.startswith("<!-- unified-brain:managed ")), "")
    return bool(marker) and marker in existing


@dataclass(frozen=True)
class InstallItem:
    path: Path
    content: str
    action: Literal["create", "replace", "skip"]


@dataclass(frozen=True)
class InstallPlan:
    root: Path
    items: tuple[InstallItem, ...]


def plan_install(root: Path, force: bool = False) -> InstallPlan:
    root = Path(root).resolve()
    items = []
    for path, content in render_all(root).items():
        action: Literal["create", "replace", "skip"]
        if not path.exists():
            action = "create"
        else:
            existing = path.read_text(encoding="utf-8")
            if existing == content:
                action = "skip"
            elif not _owned(existing, content):
                raise InstallError(f"refusing unowned overwrite: {path}; --force does not apply to unowned files")
            elif not force:
                raise InstallError(f"overwrite requires --force: {path}")
            else:
                action = "replace"
        items.append(InstallItem(path, content, action))
    return InstallPlan(root, tuple(items))


def _stage(item: InstallItem) -> Path:
    item.path.parent.mkdir(parents=True, exist_ok=True)
    name: str | None = None
    try:
        fd, name = tempfile.mkstemp(prefix=".kg-stage-", dir=item.path.parent)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(item.content)
            stream.flush()
            os.fsync(stream.fileno())
        return Path(name)
    except BaseException:
        if name is not None:
            try:
                os.unlink(name)
            except OSError:
                pass
        raise


def apply_install(plan: InstallPlan) -> dict[str, int]:
    active = [item for item in plan.items if item.action != "skip"]
    staged: list[tuple[InstallItem, Path]] = []
    created_backups: list[Path] = []
    backups: list[tuple[Path, Path]] = []
    replaced: list[Path] = []
    restored: set[Path] = set()
    try:
        for item in active:
            staged.append((item, _stage(item)))
        for item, _ in staged:
            if item.path.exists():
                fd, name = tempfile.mkstemp(prefix=".kg-backup-", dir=item.path.parent)
                os.close(fd)
                backup = Path(name)
                created_backups.append(backup)
                os.replace(item.path, backup)
                backups.append((item.path, backup))
        for item, stage in staged:
            os.replace(stage, item.path)
            replaced.append(item.path)
    except Exception:
        for path in replaced:
            path.unlink(missing_ok=True)
        restored = set()
        for path, backup in reversed(backups):
            if backup.exists():
                os.replace(backup, path)
                restored.add(backup)
        raise
    finally:
        for _, stage in staged:
            stage.unlink(missing_ok=True)
        for backup in created_backups:
            if backup not in restored:
                backup.unlink(missing_ok=True)
    return {"created": sum(i.action == "create" for i in active), "replaced": sum(i.action == "replace" for i in active), "skipped": len(plan.items) - len(active)}


def uninstall(root: Path) -> dict[str, int]:
    moved: list[tuple[Path, Path]] = []
    created_backups: list[Path] = []
    restored: set[Path] = set()
    rendered = render_all(Path(root))
    try:
        for path in rendered:
            if not path.is_file():
                continue
            existing = path.read_text(encoding="utf-8")
            if existing != rendered[path]:
                continue
            fd, name = tempfile.mkstemp(prefix=".kg-backup-", dir=path.parent)
            os.close(fd)
            backup = Path(name)
            created_backups.append(backup)
            os.replace(path, backup)
            moved.append((path, backup))
    except Exception:
        for path, backup in reversed(moved):
            if backup.exists() and not path.exists():
                try:
                    os.replace(backup, path)
                    restored.add(backup)
                except OSError:
                    pass
        raise
    finally:
        for backup in created_backups:
            if backup not in restored:
                backup.unlink(missing_ok=True)
    for path, _ in moved:
        try:
            path.parent.rmdir()
            path.parent.parent.rmdir()
        except OSError:
            pass
    return {"removed": len(moved)}


def format_plan(plan: InstallPlan) -> dict[str, object]:
    return {"root": str(plan.root), "targets": ["claude", "cursor", "pi"], "files": [{"path": str(i.path), "action": i.action} for i in plan.items]}