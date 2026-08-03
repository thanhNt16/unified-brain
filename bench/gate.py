"""Benchmark release gate: require every mandatory cell MEASURED and passing."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

REQUIRED_HARNESSES: Sequence[str] = ("claude-code", "cursor", "pi", "no-tool")


def _required_tasks() -> list[str]:
    manifest = Path(__file__).resolve().parent / "tasks.json"
    return [str(task["id"]) for task in json.loads(manifest.read_text())["tasks"]]


def validate_release_cells(
    cells: Iterable[Mapping[str, object]], required_harnesses: Sequence[str], required_tasks: Sequence[str]
) -> None:
    indexed = {(str(cell.get("harness")), str(cell.get("task"))): cell for cell in cells}
    errors: list[str] = []
    for harness in required_harnesses:
        for task in required_tasks:
            key = (harness, task)
            cell = indexed.get(key)
            if cell is None:
                errors.append(f"absent: {harness}/{task}")
                continue
            if cell.get("status") == "NOT_MEASURED":
                errors.append(f"NOT_MEASURED: {harness}/{task}: {cell.get('reason', '')}".rstrip())
            elif cell.get("status") != "MEASURED" or cell.get("pass") is not True:
                errors.append(f"failed: {harness}/{task}")
    if errors:
        raise ValueError("; ".join(errors))


def gate_report(
    path: Path, required_harnesses: Sequence[str] | None = None, required_tasks: Sequence[str] | None = None
) -> None:
    validate_release_cells(
        json.loads(path.read_text()),
        required_harnesses or REQUIRED_HARNESSES,
        required_tasks or _required_tasks(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Benchmark release gate.")
    parser.add_argument("report", type=Path, nargs="?", default=Path("bench/report.json"))
    args = parser.parse_args(argv)
    try:
        gate_report(args.report)
    except ValueError as exc:
        print(f"benchmark gate FAILED:\n{exc}", file=sys.stderr)
        return 1
    print("benchmark gate PASSED: all required cells measured and passing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
