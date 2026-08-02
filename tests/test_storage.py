import hashlib
from pathlib import Path

import pytest

from kg.storage import ContractLog, LockBusy, Registry, VaultPaths, atomic_write, discover_vault, writer_lock


def test_discovery_and_atomic_write(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    paths = discover_vault(root)
    assert isinstance(paths, VaultPaths)
    assert paths.brain == root / ".brain" and paths.raw == root / ".brain" / "raw"
    target = paths.brain / "x"
    atomic_write(target, b"abc")
    assert target.read_bytes() == b"abc"
    assert not list(paths.brain.glob(".x.*.tmp"))


def test_nonempty_root_refused(tmp_path: Path) -> None:
    (tmp_path / "x").write_text("x")
    with pytest.raises(ValueError, match="vault_exists"):
        discover_vault(tmp_path)


def test_registry_dedup_and_contract_sequence(tmp_path: Path) -> None:
    p = tmp_path / "registry.jsonl"
    r = Registry(p)
    h = hashlib.sha256(b"x").hexdigest()
    assert r.append(h, "raw/sha256.txt", "a.txt", "captured")["status"] == "captured"
    assert r.append(h, "raw/sha256.txt", "a.txt", "deduped")["status"] == "deduped"
    assert len(r.read()) == 2
    c = ContractLog(tmp_path / "contract.jsonl")
    assert c.append("kg", "init", {}, {"ok": True})["seq"] == 1
    assert c.append("kg", "init", {}, {"ok": True})["seq"] == 2


def test_lock_contention(tmp_path: Path) -> None:
    p = tmp_path / "writer.lock"
    with writer_lock(p), pytest.raises(LockBusy), writer_lock(p):
        pass
