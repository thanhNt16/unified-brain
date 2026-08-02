from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

import click

from .envelope import error, ok
from .storage import Vault, discover_vault


def _require_vault(root: Path | None = None, anchor: Path | None = None) -> Vault:
    if root is not None:
        return discover_vault(root)
    start = (anchor or Path.cwd()).resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".brain").is_dir():
            return discover_vault(candidate)
    return discover_vault(Path.cwd())


def _emit(as_json: bool, envelope: dict[str, object], status: int) -> NoReturn:
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
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
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
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
        envelope = error("internal_error", str(exc))
        status = 1
    _emit(as_json, envelope, status)


@main.command("ingest")
@click.argument("files", nargs=-1, type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--json", "as_json", is_flag=True)
def ingest_command(files: tuple[Path, ...], as_json: bool) -> None:
    try:
        vault = _require_vault(anchor=files[0])
        from .ingest import capture

        data = capture(vault, list(files))
        envelope = ok(data)
        status = 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
        envelope = error("internal_error", str(exc))
        status = 1
    _emit(as_json, envelope, status)


@main.command("extract")
@click.argument("proposal", type=click.Path(path_type=Path, exists=True))
@click.option("--json", "as_json", is_flag=True)
def extract_command(proposal: Path, as_json: bool) -> None:
    try:
        vault = _require_vault(anchor=proposal)
        from .extract import extract

        data = extract(vault, proposal)
        envelope = ok(data)
        status = 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
        envelope = error("internal_error", str(exc))
        status = 1
    _emit(as_json, envelope, status)


@main.command("apply")
@click.argument("proposal", type=click.Path(path_type=Path, exists=True))
@click.option("--json", "as_json", is_flag=True)
def apply_command(proposal: Path, as_json: bool) -> None:
    try:
        vault = _require_vault(anchor=proposal)
        from .apply import apply_proposal

        data = apply_proposal(vault, proposal)
        envelope = ok(data)
        status = 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
        envelope = error("internal_error", str(exc))
        status = 1
    _emit(as_json, envelope, status)
