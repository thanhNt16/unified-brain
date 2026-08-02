"""Release metadata is a single source of truth across package, CLI, and installer."""

from kg import __version__
from kg.release import EXPECTED_CLI_VERSION, VERSION, metadata


def test_release_metadata_is_single_source_of_truth():
    assert VERSION == "1.0.0"
    assert EXPECTED_CLI_VERSION == "kg 1.0.0"
    assert __version__ == VERSION
    assert metadata() == {"version": "1.0.0", "cli_version": "kg 1.0.0"}
    assert "0.0.0.0" not in repr(metadata())


def test_pyproject_version_matches_release():
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert pyproject["project"]["version"] == VERSION
