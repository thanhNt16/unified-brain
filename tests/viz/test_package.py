import os
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _wheel():
    env = dict(os.environ)
    proc = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(REPO / "dist")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    wheels = sorted((REPO / "dist").glob("*.whl"))
    assert wheels
    return wheels[-1]


def test_wheel_contains_assets_and_licenses():
    whl = _wheel()
    with zipfile.ZipFile(whl) as z:
        names = z.namelist()
        assert any("viz/assets/index.html" in n for n in names), names
        assert any("viz/assets/LICENSE.upstream" in n for n in names), names
        assert any("viz/assets/PROVENANCE.md" in n for n in names), names
        assert any(n.endswith(".js") and "viz/assets/assets/" in n for n in names)


def test_wheel_no_cdn_urls():
    whl = _wheel()
    with zipfile.ZipFile(whl) as z:
        for n in z.namelist():
            # Executable UI assets only; the LICENSE/PROVENANCE/THIRD_PARTY
            # notices legitimately cite the upstream URL as attribution.
            if "viz/assets/assets/" in n and n.endswith((".js", ".html", ".css")):
                data = z.read(n).decode(errors="replace")
                assert "http://" not in data and "https://" not in data, n


def test_wheel_cli_smoke():
    _wheel()
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
    p = subprocess.run(
        [sys.executable, "-m", "kg.viz.cli", "--help"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert p.returncode == 0, p.stderr
    assert "serve" in p.stdout
