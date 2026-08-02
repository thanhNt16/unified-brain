import json
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]
try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]


class LockBusy(RuntimeError):
    pass


@dataclass(frozen=True)
class VaultPaths:
    root: Path
    brain: Path
    raw: Path
    notes: Path
    kg: Path
    registry: Path
    contract: Path
    lock: Path


def discover_vault(root: Path) -> VaultPaths:
    root = Path(root)
    brain = root / ".brain"
    if root.exists() and any(root.iterdir()) and not brain.exists():
        raise ValueError("vault_exists")
    for p in (brain, brain / "raw", brain / "notes", brain / ".kg"):
        p.mkdir(parents=True, exist_ok=True)
    return VaultPaths(
        root,
        brain,
        brain / "raw",
        brain / "notes",
        brain / ".kg",
        brain / ".kg" / "registry.jsonl",
        brain / ".kg" / "contract.jsonl",
        brain / ".kg" / "writer.lock",
    )


def atomic_write(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def writer_lock(path: Path) -> Iterator[None]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+b") as handle:
        try:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            elif msvcrt is not None:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                raise LockBusy("lock_busy")
        except (BlockingIOError, OSError) as exc:
            raise LockBusy("lock_busy") from exc
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)
            elif msvcrt is not None:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


class Registry:
    def __init__(self, path: Path):
        self.path = Path(path)

    def append(self, source_sha256: str, raw_path: str, original_name: str, status: str) -> dict[str, object]:
        row = {
            "source_sha256": source_sha256,
            "raw_path": raw_path,
            "original_name": original_name,
            "status": status,
            "ts": time.time(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        return row

    def read(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line]


class ContractLog:
    def __init__(self, path: Path):
        self.path = Path(path)

    def append(
        self,
        tool: str,
        cmd: str,
        args: object,
        envelope: dict[str, object],
        data: object = None,
        error: object = None,
    ) -> dict[str, object]:
        seq = 1
        if self.path.exists():
            with self.path.open() as f:
                seq = sum(1 for line in f if line.strip()) + 1
        row = {
            "seq": seq,
            "ts": time.time(),
            "tool": tool,
            "cmd": cmd,
            "args": args,
            "ok": envelope.get("ok"),
            "envelope": envelope,
            "data": data,
            "error": error,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        return row
