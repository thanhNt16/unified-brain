import re
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _text(name: str) -> str:
    path = ROOT / name
    assert path.is_file(), f"missing {name}"
    text = path.read_text()
    assert len(text.strip()) >= 100, f"{name} is nontrivial"
    assert not re.search(r"\b(?:TODO|TBD|FIXME|placeholder)\b", text, re.IGNORECASE)
    return text


def test_required_docs_have_release_contracts() -> None:
    license_text = _text("LICENSE")
    notice = _text("NOTICE")
    contributing = _text("CONTRIBUTING")
    readme = _text("README")
    assert "MIT License" in license_text
    assert "Permission is hereby granted" in license_text
    assert "d6be58ef9d43c574a2d1b0827ecc1e3c4846f0fe" in notice
    assert "LICENSE.upstream" in notice
    assert "PROVENANCE.md" in notice
    assert "uv sync" in contributing
    assert "uv run ruff" in contributing
    assert "uv run mypy" in contributing
    assert "uv run pytest" in contributing
    assert "uv build" in contributing
    assert "curl -fsSL" in readme
    assert "kg install --apply" in readme
    assert "NOT_MEASURED" in readme
    assert "no MCP layer" in readme
    assert "0.0.0.0" not in readme


def test_readme_documents_exact_command_tree() -> None:
    readme = _text("README")
    commands = (
        "init",
        "ingest",
        "extract",
        "apply",
        "query",
        "dream",
        "review",
        "index",
        "graph",
        "viz serve",
        "viz vendor",
        "install",
        "cron-print",
    )
    for command in commands:
        assert re.search(rf"`kg {re.escape(command)}(?:\s|`)", readme), command
    assert readme.count("`kg ") >= len(commands)


def test_readme_names_five_skills_and_full_flow() -> None:
    readme = _text("README")
    for skill in ("kg:init", "kg:ingest", "kg:extract", "kg:query", "kg:dream"):
        assert f"`{skill}`" in readme
    flow = ("kg init", "kg ingest", "kg extract", "kg apply", "kg query", "kg dream", "kg review", "kg viz serve")
    positions = [readme.index(f"`{command}") for command in flow]
    assert positions == sorted(positions)
