import json
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


_HELD_LOCKS: set[Path] = set()


@dataclass(frozen=True)
class VaultPaths:
    root: Path
    brain: Path | None = None
    raw: Path | None = None
    notes: Path | None = None
    kg: Path | None = None
    registry: Path | None = None
    contract: Path | None = None
    lock: Path | None = None

    def __post_init__(self) -> None:
        root = Path(self.root)
        brain = Path(self.brain or root / ".brain")
        values = {
            "root": root,
            "brain": brain,
            "raw": Path(self.raw or brain / "raw"),
            "notes": Path(self.notes or brain / "notes"),
            "kg": Path(self.kg or brain / ".kg"),
            "registry": Path(self.registry or brain / ".kg" / "registry.jsonl"),
            "contract": Path(self.contract or brain / ".kg" / "contract.jsonl"),
            "lock": Path(self.lock or brain / ".kg" / "writer.lock"),
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)

    @property
    def contract_log(self) -> Path:
        return self.contract  # type: ignore[return-value]

    def live_note_ids(self) -> set[str]:
        """All non-tombstone, non-superseded note IDs from canonical Markdown."""
        ids: set[str] = set()
        notes = self.notes
        assert notes is not None
        for path in notes.glob("*/*.md"):
            line = path.read_text(encoding="utf-8").splitlines()
            status = next((s.split(": ", 1)[1].strip() for s in line if s.startswith("status:")), "draft")
            if status in {"tombstone", "superseded"}:
                continue
            for s in line:
                if s.startswith("id:"):
                    ids.add(s.split(": ", 1)[1].strip())
                    break
        return ids


Vault = VaultPaths


def discover_vault(root: Path, *, create: bool = True) -> VaultPaths:
    root = Path(root)
    brain = root / ".brain"
    if root.exists() and not root.is_dir():
        raise ValueError("vault_exists")
    if root.exists() and any(root.iterdir()) and not brain.exists():
        raise ValueError("vault_exists")
    if not create:
        return VaultPaths(root)
    root.mkdir(parents=True, exist_ok=True)
    for path in (brain, brain / "raw", brain / "notes", brain / ".kg"):
        path.mkdir(parents=True, exist_ok=True)
    return VaultPaths(root)


def _canonical_lock(path: Path) -> Path:
    return Path(path).resolve()


@contextmanager
def writer_lock(path: Path, *, blocking: bool = False) -> Iterator[None]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    key = _canonical_lock(path)
    if key in _HELD_LOCKS:
        if blocking:
            yield
            return
        raise LockBusy("lock_busy")
    with path.open("a+b") as handle:
        try:
            if fcntl is not None:
                flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
                fcntl.flock(handle, flags)
            elif msvcrt is not None:
                handle.seek(0)
                mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
                msvcrt.locking(handle.fileno(), mode, 1)
            else:
                raise LockBusy("lock_busy")
        except (BlockingIOError, OSError) as exc:
            raise LockBusy("lock_busy") from exc
        _HELD_LOCKS.add(key)
        try:
            yield
        finally:
            _HELD_LOCKS.discard(key)
            if fcntl is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)
            elif msvcrt is not None:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def Lock(vault: VaultPaths) -> Iterator[None]:
    lock = vault.lock
    assert lock is not None
    with writer_lock(lock):
        yield


def _lock_for_file(path: Path) -> Path:
    return Path(path).parent / "writer.lock"


@contextmanager
def _mutation_lock(path: Path) -> Iterator[None]:
    lock_path = _canonical_lock(_lock_for_file(path))
    if lock_path in _HELD_LOCKS:
        yield
    else:
        with writer_lock(lock_path, blocking=True):
            yield


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
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Registry:
    def __init__(self, path: Path | VaultPaths):
        source = path.registry if isinstance(path, VaultPaths) else path
        assert source is not None
        self.path = Path(source)

    def append(
        self,
        source_sha256: str | dict[str, object] | None = None,
        raw_path: str | None = None,
        original_name: str | None = None,
        status: str | None = None,
        **kwargs: object,
    ) -> dict[str, object]:
        if isinstance(source_sha256, dict):
            row = dict(source_sha256)
        else:
            row = {
                "source_sha256": source_sha256,
                "raw_path": raw_path,
                "original_name": original_name,
                "status": status,
            }
            row.update(kwargs)
        row.setdefault("ts", time.time())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _mutation_lock(self.path):
            self._ensure_trailing_newline()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        return row

    def contains(self, source_sha256: str) -> bool:
        return any(row.get("source_sha256") == source_sha256 for row in self.read())

    def read(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, object]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
        return rows

    def _ensure_trailing_newline(self) -> None:
        if self.path.exists() and self.path.stat().st_size and not self.path.read_bytes().endswith(b"\n"):
            with self.path.open("ab") as handle:
                handle.write(b"\n")
                handle.flush()
                os.fsync(handle.fileno())


class ContractLog:
    def __init__(self, path: Path | VaultPaths):
        source = path.contract if isinstance(path, VaultPaths) else path
        assert source is not None
        self.path = Path(source)

    def append(
        self,
        tool: str,
        cmd: str,
        args: object,
        envelope: dict[str, object],
        data: object = None,
        error: object = None,
    ) -> dict[str, object]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _mutation_lock(self.path):
            seq = self._next_seq()
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
            self._ensure_trailing_newline()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return row

    def _next_seq(self) -> int:
        maximum = 0
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    value: Any = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict) and isinstance(value.get("seq"), int):
                    maximum = max(maximum, value["seq"])
        return maximum + 1

    def _ensure_trailing_newline(self) -> None:
        if self.path.exists() and self.path.stat().st_size and not self.path.read_bytes().endswith(b"\n"):
            with self.path.open("ab") as handle:
                handle.write(b"\n")
                handle.flush()
                os.fsync(handle.fileno())


def contract_log(
    vault: VaultPaths,
    tool: str,
    cmd: str,
    args: object,
    envelope: dict[str, object],
    data: object = None,
    error: object = None,
) -> dict[str, object]:
    return ContractLog(vault).append(tool, cmd, args, envelope, data, error)
