"""Shared benchmark runner with honest result statuses."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path

ReportCell = dict[str, object]
STATUSES = {"MEASURED", "FAILED", "NOT_MEASURED"}
ABSOLUTE_WORKSPACE = Path(__file__).resolve().parent.parent
_CREDENTIALS = {"claude-code": "CLAUDE_API_KEY", "cursor": "CURSOR_API_KEY", "pi": "PI_API_KEY"}
_FAKE = [sys.executable, "-c", "import json; print(json.dumps({'pass': True, 'tokens': None, 'cost': None}))"]


def _cell(
    harness: str,
    task: str,
    *,
    passed: bool | None,
    elapsed: float,
    status: str,
    reason: str = "",
    tokens: object = None,
    cost: object = None,
) -> ReportCell:
    return {
        "harness": harness,
        "task": task,
        "pass": passed,
        "time_s": round(elapsed, 3),
        "tokens": tokens,
        "cost": cost,
        "status": status,
        "reason": reason,
    }


def _terminate_group(proc: subprocess.Popen[bytes], grace: float = 0.25) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()


def _run(
    argv: list[str], prompt: str, timeout: float, env: Mapping[str, str]
) -> tuple[ReportCell | None, subprocess.CompletedProcess[bytes] | None, float]:
    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            argv + [prompt],
            cwd=str(ABSOLUTE_WORKSPACE),
            env=dict(env),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate_group(proc)
            return None, None, time.monotonic() - started
    except OSError as exc:
        return None, subprocess.CompletedProcess(argv, 127, b"", str(exc).encode()), time.monotonic() - started
    return None, subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr), time.monotonic() - started


def run_manifest(
    manifest_path: Path, report_path: Path, harness_commands: dict[str, list[str]], env: Mapping[str, str] | None = None
) -> list[ReportCell]:
    manifest = json.loads(manifest_path.read_text())
    current_env = dict(os.environ if env is None else env)
    cells: list[ReportCell] = []
    fake = current_env.get("FAKE_BENCH_HARNESS")
    for harness, command in harness_commands.items():
        credential = _CREDENTIALS.get(harness)
        for task in manifest["tasks"]:
            task_id = str(task["id"])
            timeout = float(task["timeout_s"])
            if credential and not fake and not current_env.get(credential):
                cells.append(
                    _cell(
                        harness,
                        task_id,
                        passed=None,
                        elapsed=0.0,
                        status="NOT_MEASURED",
                        reason=f"missing credential: {credential}",
                    )
                )
                continue
            argv = _FAKE if fake else list(command)
            _, result, elapsed = _run(argv, str(task["prompt"]), timeout, current_env)
            if result is None:
                cells.append(
                    _cell(
                        harness,
                        task_id,
                        passed=False,
                        elapsed=elapsed,
                        status="FAILED",
                        reason=f"timeout: task exceeded {timeout:g}s",
                    )
                )
                continue
            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                payload = None
            if result.returncode != 0:
                reason = stderr or f"exit code {result.returncode}"
                cells.append(_cell(harness, task_id, passed=False, elapsed=elapsed, status="FAILED", reason=reason))
            elif not isinstance(payload, dict) or not isinstance(payload.get("pass"), bool):
                cells.append(
                    _cell(
                        harness, task_id, passed=False, elapsed=elapsed, status="FAILED", reason="malformed JSON result"
                    )
                )
            else:
                tokens = payload.get("tokens") if isinstance(payload.get("tokens"), (int, float)) else None
                cost = payload.get("cost") if isinstance(payload.get("cost"), (int, float)) else None
                cells.append(
                    _cell(
                        harness,
                        task_id,
                        passed=payload["pass"],
                        elapsed=elapsed,
                        status="MEASURED",
                        tokens=tokens,
                        cost=cost,
                    )
                )
    report_path.write_text(json.dumps(cells, sort_keys=True, indent=2) + "\n")
    return cells


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("bench/tasks.json"))
    parser.add_argument("--report", type=Path, default=Path("bench/report.json"))
    args = parser.parse_args()
    from bench.harness_claude_code import COMMAND as claude
    from bench.harness_cursor import COMMAND as cursor
    from bench.harness_no_tool import COMMAND as no_tool
    from bench.harness_pi import COMMAND as pi

    run_manifest(args.manifest, args.report, {"claude-code": claude, "cursor": cursor, "pi": pi, "no-tool": no_tool})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
