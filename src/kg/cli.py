from __future__ import annotations

import json
from pathlib import Path

import click

from .envelope import error, ok
from .storage import Vault, discover_vault


def _require_vault(root: Path | None = None) -> Vault:
    vault = discover_vault(root) if root else discover_vault(Path.cwd())
    return vault


def _emit(as_json: bool, envelope: dict[str, object], status: int) -> None:
    if as_json:
        click.echo(json.dumps(envelope, allow_nan=False, separators=(",", ":")))
    else:
        data = envelope.get("data") if envelope.get("ok") else envelope.get("error")
        click.echo(json.dumps(data, allow_nan=False, separators=(",", ":")))
    raise click.exceptions.Exit(status)


@click.group()
def main() -> None:
    """Local-first knowledge graph toolkit."""


@main.command("init")
@click.argument("root", type=click.Path(path_type=Path))
@click.option("--json", "as_json", is_flag=True)
def init_command(root: Path, as_json: bool) -> None:
    try:
        vault = _require_vault(root)
        envelope: dict[str, object] = ok({"root": str(vault.brain)})
        status = 0
    except Exception as exc:
        envelope = error("internal_error", str(exc))
        status = 1
    _emit(as_json, envelope, status)


@main.command("index")
@click.option("--rebuild", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
def index_command(rebuild: bool, as_json: bool) -> None:
    try:
        vault = _require_vault()
        from .index import run

        data, status = run(vault, rebuild)
        if status == 0:
            envelope = ok(data)
        else:
            envelope = error("index_errors", f"{data['errors']} malformed notes", data)
    except Exception as exc:
        envelope = error("internal_error", str(exc))
        status = 1
    _emit(as_json, envelope, status)
