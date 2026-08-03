"""Distribution policy checks for source scope and built wheels."""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPES = ("src", "tests", "bench", ".github")
UI_COMMIT = "d6be58ef9d43c574a2d1b0827ecc1e3c4846f0fe"
UI_SOURCE = "https://github.com/DeusData/codebase-memory-mcp.git"
GRAPH_FORMATS = {".graphml", ".gexf", ".graphson", ".gml"}


def _scoped_files() -> list[Path]:
    return [
        path
        for scope in SCOPES
        for path in (ROOT / scope).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]


def test_source_scope_has_no_forbidden_files_or_formats() -> None:
    files = _scoped_files()
    forbidden_names = re.compile(r"(?:^|[-_.])(mcp|config)(?:[-_.]|$)", re.IGNORECASE)
    assert not [p for p in files if forbidden_names.search(p.name)]
    assert not [p for p in files if p.suffix.lower() in GRAPH_FORMATS]

    text = "\n".join(
        p.read_text(errors="replace")
        for p in files
        if "tests" not in p.parts and p.suffix.lower() in {".py", ".toml", ".yml", ".yaml", ".sh", ".json"}
    )
    assert "0.0.0.0" not in text
    assert "shell=True" not in text
    assert "os.system(" not in text
    # Generated wiki pages must be explicitly derived from canonical notes,
    # never treated as canonical input themselves.
    assert "wiki" not in text.lower() or "derived from canonical" in text.lower()


def test_source_metadata_matches_pinned_ui() -> None:
    provenance = ROOT / "src/kg/viz/assets/PROVENANCE.md"
    license_file = ROOT / "src/kg/viz/assets/LICENSE.upstream"
    assert provenance.is_file()
    assert license_file.is_file()
    data = json.loads(provenance.read_text())
    assert data == {
        "name": "codebase-memory-mcp",
        "component": "graph-ui",
        "source": UI_SOURCE,
        "commit": UI_COMMIT,
        "license": "LICENSE.upstream",
        "third_party": "graph-ui/package-lock.json (npm registry)",
        "built_by": "kg viz vendor",
        "patches": "none",
    }
    assert "MIT License" in license_file.read_text()


def test_wheel_distribution_policy() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        result = subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", directory],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        wheels = sorted(Path(directory).glob("*.whl"))
        assert wheels
        with zipfile.ZipFile(wheels[-1]) as wheel:
            names = wheel.namelist()
            assert any(name.endswith("viz/assets/index.html") for name in names)
            assert any(name.endswith("viz/assets/LICENSE.upstream") for name in names)
            assert any(name.endswith("viz/assets/PROVENANCE.md") for name in names)
            assert any(name.endswith(".js") and "viz/assets/assets/" in name for name in names)
            assert not [name for name in names if Path(name).suffix.lower() in GRAPH_FORMATS]
            assert not [name for name in names if "mcp" in Path(name).name.lower()]
            assert all("0.0.0.0" not in wheel.read(name).decode(errors="replace") for name in names)
            executable = (".html", ".js", ".css")
            assert all(
                not any(url in wheel.read(name).decode(errors="replace") for url in ("http://", "https://"))
                for name in names
                if name.endswith(executable)
            )
            metadata = next(wheel.read(name).decode() for name in names if name.endswith("METADATA"))
            assert "Version: 1.0.0" in metadata
            assert "Requires-Python: >=3.11" in metadata
            assert "Requires-Dist: node" not in metadata.lower()


def test_package_metadata_contract() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["version"] == "1.0.0"
    assert project["requires-python"] == ">=3.11"
