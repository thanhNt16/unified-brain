import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def run_cli(*args):
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
    return subprocess.run(
        [sys.executable, "-m", "kg.viz.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_vendor_no_args_prints_help():
    p = run_cli("vendor")
    assert p.returncode == 0, p.stderr
    assert "--pin" in p.stdout


def test_viz_group_has_two_commands():
    p = run_cli("--help")
    assert p.returncode == 0
    assert "serve" in p.stdout and "vendor" in p.stdout


def test_root_cli_exposes_viz_group():
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
    p = subprocess.run(
        [sys.executable, "-m", "kg.cli", "--help"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert p.returncode == 0
    assert "viz" in p.stdout


def test_vendor_verify_reports_bundle():
    p = run_cli("vendor", "--version")
    assert p.returncode == 0
    assert "commit: d6be58ef9d43c574a2d1b0827ecc1e3c4846f0fe" in p.stdout
    assert "built:" in p.stdout


def test_vendor_nondefault_pin_rejected_before_work():
    import tempfile

    workdir = Path(tempfile.gettempdir()) / "kg-viz-vendor"
    before = (workdir / "PINNED_COMMIT").exists()
    p = run_cli("vendor", "--pin", "deadbeef", "--apply")
    assert p.returncode != 0
    assert "immutable" in p.stderr
    assert (workdir / "PINNED_COMMIT").exists() == before
