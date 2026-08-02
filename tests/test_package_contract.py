from importlib.metadata import version
from pathlib import Path
import tomllib


def test_package_contract() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text())
    assert data["project"]["requires-python"] == ">=3.11"
    assert "numpy" not in str(data).lower()
    dev = data["dependency-groups"]["dev"]
    names = {item.split("[", 1)[0].split(">", 1)[0].split("<", 1)[0].split("=", 1)[0] for item in dev}
    assert {"pytest", "ruff", "mypy"} <= names
    assert version("unified-brain-kg") == __import__("kg").__version__
