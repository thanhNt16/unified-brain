import os
import subprocess
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path


def test_package_contract() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text())
    assert data["project"]["requires-python"] == ">=3.11"
    assert "numpy" not in str(data).lower()
    dev = data["dependency-groups"]["dev"]
    names = {item.split("[", 1)[0].split(">", 1)[0].split("<", 1)[0].split("=", 1)[0] for item in dev}
    assert {"pytest", "ruff", "mypy"} <= names
    assert version("unified-brain-kg") == __import__("kg").__version__


def test_wheel_installs_claude_skills(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(dist)], check=True)
    wheel = next(dist.glob("*.whl"))
    tool_dir = tmp_path / "tools"
    bin_dir = tmp_path / "bin"
    env = os.environ | {"UV_TOOL_DIR": str(tool_dir), "UV_TOOL_BIN_DIR": str(bin_dir)}
    subprocess.run(
        ["uv", "tool", "install", "--from", str(wheel), "unified-brain-kg"],
        env=env,
        check=True,
    )
    root = tmp_path / "home"
    result = subprocess.run(
        [str(bin_dir / ("kg.exe" if sys.platform == "win32" else "kg")), "install", "--root", str(root), "--apply"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert sorted(p.stem for p in (root / ".claude" / "commands" / "kg").glob("*.md")) == [
        "apply",
        "dream",
        "extract",
        "ingest",
        "init",
        "query",
    ]
