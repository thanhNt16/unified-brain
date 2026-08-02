from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.gate import gate_report, validate_release_cells

REQUIRED = [{"harness": h, "task": "t1", "pass": True, "status": "MEASURED"} for h in ("claude-code", "cursor")]


def test_gate_accepts_all_measured_passing_cells() -> None:
    validate_release_cells(REQUIRED, ["claude-code", "cursor"], ["t1"])


def test_gate_rejects_not_measured_cell() -> None:
    cells = REQUIRED[:-1] + [
        {"harness": "cursor", "task": "t1", "pass": None, "status": "NOT_MEASURED", "reason": "missing credential"}
    ]
    with pytest.raises(ValueError, match="NOT_MEASURED"):
        validate_release_cells(cells, ["claude-code", "cursor"], ["t1"])


def test_gate_rejects_failed_cell() -> None:
    cells = REQUIRED[:-1] + [{"harness": "cursor", "task": "t1", "pass": False, "status": "FAILED"}]
    with pytest.raises(ValueError, match="failed"):
        validate_release_cells(cells, ["claude-code", "cursor"], ["t1"])


def test_gate_rejects_absent_cell() -> None:
    with pytest.raises(ValueError, match="absent"):
        validate_release_cells(REQUIRED[:1], ["claude-code", "cursor"], ["t1"])


def test_gate_report_loads_results_file(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_text(json.dumps(REQUIRED))
    gate_report(path, ["claude-code", "cursor"], ["t1"])
