import hashlib
import json
import multiprocessing
from pathlib import Path


def _append_contract(path: str) -> None:
    ContractLog(Path(path)).append("kg", "test", {}, {"ok": True})


import pytest

from kg.storage import (
    ContractLog,
    Lock,
    LockBusy,
    Registry,
    Vault,
    VaultPaths,
    atomic_write,
    contract_log,
    discover_vault,
    writer_lock,
)


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


def test_nonempty_root_allowed(tmp_path: Path) -> None:
    (tmp_path / "existing.txt").write_text("x")
    paths = discover_vault(tmp_path)
    assert paths.brain == tmp_path / ".brain"
    assert paths.brain.is_dir()
    assert (tmp_path / "existing.txt").read_text() == "x"


def test_regular_file_root_refused(tmp_path: Path) -> None:
    root = tmp_path / "file.txt"
    root.write_text("x")
    with pytest.raises(ValueError, match="vault_exists"):
        discover_vault(root)


def test_missing_root_created(tmp_path: Path) -> None:
    root = tmp_path / "new-vault"
    paths = discover_vault(root)
    assert root.is_dir() and paths.brain.is_dir()


def test_vault_alias_and_lock(tmp_path: Path) -> None:
    vault = Vault(tmp_path)
    assert isinstance(vault, VaultPaths)
    assert vault.brain == tmp_path / ".brain"
    assert vault.lock == tmp_path / ".brain" / ".kg" / "writer.lock"
    with Lock(vault):
        pass
    assert vault.contract_log == tmp_path / ".brain" / ".kg" / "contract.jsonl"


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


def test_registry_vault_dict_row_and_contains(tmp_path: Path) -> None:
    vault = Vault(tmp_path)
    r = Registry(vault)
    digest = hashlib.sha256(b"x").hexdigest()
    row = {"source_sha256": digest, "raw_path": "raw/sha256.txt", "status": "captured"}
    assert r.append(row)["status"] == "captured"
    assert r.contains(digest)
    assert not r.contains(hashlib.sha256(b"y").hexdigest())


def test_registry_read_after_partial_write(tmp_path: Path) -> None:
    p = tmp_path / "registry.jsonl"
    h = hashlib.sha256(b"x").hexdigest()
    p.write_text(json.dumps({"source_sha256": h, "status": "captured"}), encoding="utf-8")
    r = Registry(p)
    r.append(h, "raw/x.txt", "x.txt", "deduped")
    rows = r.read()
    assert len(rows) == 2
    assert rows[0]["status"] == "captured"
    assert rows[1]["status"] == "deduped"


def test_contract_log_seq_continuity_and_partial_line(tmp_path: Path) -> None:
    p = tmp_path / "contract.jsonl"
    c = ContractLog(p)
    p.write_text('{"seq": 42, "tool": "kg"}\n', encoding="utf-8")
    assert c.append("kg", "init", {}, {"ok": True})["seq"] == 43
    assert c.append("kg", "init", {}, {"ok": True})["seq"] == 44
    assert [json.loads(line)["seq"] for line in p.read_text().splitlines()] == [42, 43, 44]


def test_contract_log_helper(tmp_path: Path) -> None:
    vault = Vault(tmp_path)
    row = contract_log(vault, "kg", "init", {}, {"ok": True})
    assert row["seq"] == 1
    assert row["ok"] is True


def test_contract_log_concurrent_sequences(tmp_path: Path) -> None:
    path = tmp_path / "contract.jsonl"
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(8) as pool:
        pool.map(_append_contract, [str(path)] * 8)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert sorted(row["seq"] for row in rows) == list(range(1, 9))


def test_lock_contention(tmp_path: Path) -> None:
    p = tmp_path / "writer.lock"
    with writer_lock(p), pytest.raises(LockBusy), writer_lock(p):
        pass


def _append_contract(path: str) -> None:
    ContractLog(Path(path)).append("kg", "test", {}, {"ok": True})


def test_contract_seq_monotonic_over_existing_content(tmp_path: Path) -> None:
    p = tmp_path / "contract.jsonl"
    p.write_text('{"seq": 42}\n', encoding="utf-8")
    assert ContractLog(p).append("kg", "test", {}, {"ok": True})["seq"] == 43


def test_registry_survives_missing_trailing_newline(tmp_path: Path) -> None:
    p = tmp_path / "registry.jsonl"
    p.write_text('{"source_sha256": "' + "a" * 64 + '", "status": "captured"}', encoding="utf-8")
    r = Registry(p)
    row = r.append({"source_sha256": "b" * 64, "status": "captured"})
    assert row["status"] == "captured"
    rows = r.read()
    assert len(rows) == 2 and rows[0]["source_sha256"] == "a" * 64
    assert r.contains("a" * 64) and not r.contains("c" * 64)


def test_contract_seq_serialized_across_processes(tmp_path: Path) -> None:
    path = tmp_path / "contract.jsonl"
    workers = [multiprocessing.Process(target=_append_contract, args=(str(path),)) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(30)
    assert all(worker.exitcode == 0 for worker in workers)
    seqs = [json.loads(line)["seq"] for line in path.read_text().splitlines() if line.strip()]
    assert seqs == sorted(seqs) and len(seqs) == len(set(seqs)) == 4
