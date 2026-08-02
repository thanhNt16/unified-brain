"""M6.3 benchmark runner tests.

Fake-mode only: no live Claude/Cursor/Pi model is ever invoked. When the
external FAKE_BENCH_HARNESS env var is set, the real runner swaps in a
deterministic local fake harness instead of any real binary.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from bench.runner import run_manifest

HARNESSES: dict[str, list[str]] = {
    "claude-code": ["/usr/local/bin/fake-cc", "--print", "--output-format", "json", "--model", "haiku"],
    "cursor": ["/usr/local/bin/fake-cur", "-p", "--output-format", "json"],
    "pi": ["/usr/local/bin/fake-node", "/usr/local/bin/cli.js", "--print", "--mode", "json"],
    "no-tool": ["python", "-m", "bench.harness_no_tool"],
}


class FakeProc:
    def __init__(self, argv: list[str], **kwargs: object) -> None:
        self.argv = argv
        self.returncode: int | None = 0
        self.pid = 12345
        assert kwargs.get("shell") is False
        assert kwargs.get("start_new_session") is True
        assert kwargs.get("stdin") is subprocess.DEVNULL
        assert kwargs.get("cwd") == str(Path(__file__).resolve().parents[2])
        assert kwargs.get("stdout") is subprocess.PIPE
        assert kwargs.get("stderr") is subprocess.PIPE

    def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
        return b'{"pass": true, "tokens": 12, "cost": 0.02}', b""

    def wait(self, timeout: float | None = None) -> int | None:
        return None


def _manifest(tmp_path: Path) -> Path:
    p = tmp_path / "tasks.json"
    p.write_text(
        json.dumps(
            {
                "tasks": [
                    {"id": "t1", "prompt": "one", "expected": "ok", "timeout_s": 2},
                    {"id": "t2", "prompt": "two", "expected": "ok", "timeout_s": 2},
                ]
            }
        )
    )
    return p


def _fake_harness(tmp_path: Path) -> Path:
    """Deterministic fake harness: sleeps, then emits a valid pass payload."""
    script = tmp_path / "fake_harness.py"
    script.write_text(
        "import json, sys, time\n"
        "time.sleep(float(sys.argv[1]))\n"
        "print(json.dumps({'pass': True, 'tokens': None, 'cost': None}))\n"
    )
    return script


@pytest.fixture()
def no_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FAKE_BENCH_HARNESS", raising=False)


@pytest.fixture()
def fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_BENCH_HARNESS", "1")


def test_run_manifest_records_cells_and_writes_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_fake: None
) -> None:
    monkeypatch.setattr(subprocess, "Popen", FakeProc)
    report = tmp_path / "report.json"
    cells = run_manifest(_manifest(tmp_path), report, {"cc": ["tool", "x"]}, env={})
    assert cells[0]["status"] == "MEASURED"
    assert cells[0]["pass"] is True
    assert cells[0]["tokens"] == 12
    assert cells[0]["cost"] == 0.02
    assert cells[0]["harness"] == "cc"
    assert cells[0]["task"] == "t1"
    assert isinstance(cells[0]["time_s"], float)
    assert json.loads(report.read_text()) == cells


def test_run_manifest_marks_failed_on_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_fake: None) -> None:
    class FailProc(FakeProc):
        def __init__(self, argv: list[str], **kwargs: object) -> None:
            super().__init__(argv, **kwargs)
            self.returncode = 1

        def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
            return b"", b"boom"

    monkeypatch.setattr(subprocess, "Popen", FailProc)
    cells = run_manifest(_manifest(tmp_path), tmp_path / "report.json", {"cc": ["tool", "x"]}, env={})
    assert cells[0]["status"] == "FAILED"
    assert cells[0]["pass"] is False
    assert cells[0]["reason"] == "boom"


def test_run_manifest_marks_not_measured_when_credential_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_fake: None
) -> None:
    cells = run_manifest(_manifest(tmp_path), tmp_path / "report.json", {"claude-code": ["claude"]}, env={})
    assert cells[0]["status"] == "NOT_MEASURED"
    assert cells[0]["pass"] is None
    assert cells[0]["tokens"] is None
    assert cells[0]["cost"] is None
    assert cells[0]["reason"] == "missing credential: CLAUDE_API_KEY"


def test_fake_mode_bypasses_credential_requirement(tmp_path: Path, fake: None) -> None:
    """FAKE_BENCH_HARNESS skips credential probes and runs a deterministic local cell."""
    manifest = tmp_path / "tasks.json"
    manifest.write_text(json.dumps({"tasks": [{"id": "t1", "prompt": "one", "expected": "ok", "timeout_s": 30}]}))
    cells = run_manifest(manifest, tmp_path / "report.json", {"claude-code": ["claude", "--print"]}, env=None)
    assert cells[0]["status"] == "MEASURED"
    assert cells[0]["pass"] is True
    assert cells[0]["tokens"] is None
    assert cells[0]["cost"] is None


def test_timeout_kills_process_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_fake: None) -> None:
    """External timeout SIGTERMs the group, waits a grace, then SIGKILLs."""

    class HangingProc(FakeProc):
        _waits = 0

        def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
            raise subprocess.TimeoutExpired(cmd=self.argv, timeout=timeout)

        def wait(self, timeout: float | None = None) -> int | None:
            HangingProc._waits += 1
            if HangingProc._waits == 1:
                raise subprocess.TimeoutExpired(cmd=self.argv, timeout=timeout or 0)
            return None

    kills: list[tuple[int, int]] = []
    monkeypatch.setattr(subprocess, "Popen", HangingProc)
    monkeypatch.setattr(os, "killpg", lambda pid, sig: kills.append((pid, sig)))
    manifest = tmp_path / "tasks.json"
    manifest.write_text(json.dumps({"tasks": [{"id": "t1", "prompt": "one", "expected": "ok", "timeout_s": 2}]}))
    cells = run_manifest(manifest, tmp_path / "report.json", {"cc": ["tool", "x"]}, env={})
    assert cells[0]["status"] == "FAILED"
    assert cells[0]["pass"] is False
    assert cells[0]["reason"] == "timeout: task exceeded 2s"
    assert kills == [(12345, signal.SIGTERM), (12345, signal.SIGKILL)]


def test_launch_error_maps_to_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_fake: None) -> None:
    def missing(argv: list[str], **kwargs: object) -> FakeProc:
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(subprocess, "Popen", missing)
    cells = run_manifest(_manifest(tmp_path), tmp_path / "report.json", {"cc": ["/nope/missing"]}, env={})
    assert cells[0]["status"] == "FAILED"
    assert cells[0]["pass"] is False
    assert "nope/missing" in cells[0]["reason"]


def test_fake_mode_deterministic_success(tmp_path: Path, fake: None) -> None:
    """Real subprocess fake harness reports a genuine MEASURED cell."""
    harness = _fake_harness(tmp_path)
    manifest = tmp_path / "tasks.json"
    manifest.write_text(json.dumps({"tasks": [{"id": "t1", "prompt": "one", "expected": "ok", "timeout_s": 30}]}))
    cells = run_manifest(manifest, tmp_path / "report.json", {"no-tool": [sys.executable, str(harness), "0"]}, env={})
    assert cells[0]["status"] == "MEASURED"
    assert cells[0]["pass"] is True
    assert cells[0]["tokens"] is None
    assert cells[0]["cost"] is None


def test_fake_mode_deterministic_failure(tmp_path: Path, fake: None) -> None:
    """Fake harness exiting nonzero maps to FAILED, not a fabricated pass."""
    script = tmp_path / "fail.py"
    script.write_text("import sys\nsys.exit(3)\n")
    manifest = tmp_path / "tasks.json"
    manifest.write_text(json.dumps({"tasks": [{"id": "t1", "prompt": "one", "expected": "ok", "timeout_s": 30}]}))
    cells = run_manifest(manifest, tmp_path / "report.json", {"no-tool": [sys.executable, str(script)]}, env={})
    assert cells[0]["status"] == "FAILED"
    assert cells[0]["pass"] is False
