from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import NoReturn

import click

from .envelope import ErrorCodes, error, ok
from .storage import Vault, discover_vault

# Exception message prefixes produced by the provenance modules; the CLI boundary
# maps each prefix to the structured error code the spec's section 13 defines.
_CODE_PREFIXES: dict[str, ErrorCodes] = {
    "schema_validation": ErrorCodes.schema_validation,
    "unknown_source": ErrorCodes.unknown_source,
    "dangling_edge": ErrorCodes.dangling_edge,
    "lock_busy": ErrorCodes.lock_busy,
    "path_forbidden": ErrorCodes.path_forbidden,
    "limit_error": ErrorCodes.limit_error,
    "db_schema_newer": ErrorCodes.db_schema_newer,
    "vault_exists": ErrorCodes.vault_exists,
    "not_initialized": ErrorCodes.not_initialized,
}


def _require_vault(root: Path | None = None, anchor: Path | None = None) -> Vault:
    if root is not None:
        return discover_vault(root)
    start = (anchor or Path.cwd()).resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".brain").is_dir():
            return discover_vault(candidate, create=False)
    raise ValueError("not_initialized: no .brain found from this directory")


def _emit(as_json: bool, envelope: dict[str, object], status: int) -> NoReturn:
    if as_json:
        click.echo(json.dumps(envelope, allow_nan=False, separators=(",", ":")))
    else:
        data = envelope.get("data") if envelope.get("ok") else envelope.get("error")
        click.echo(json.dumps(data, allow_nan=False, separators=(",", ":")))
    raise click.exceptions.Exit(status)


def _code_of(exc: Exception) -> ErrorCodes:
    if isinstance(exc, sqlite3.Error):
        return ErrorCodes.index_errors
    message = str(exc)
    prefix = message.split(":", 1)[0]
    return _CODE_PREFIXES.get(prefix, ErrorCodes.internal_error)


@click.group()
@click.version_option(version="1.0.0", prog_name="kg")
def main() -> None:
    """Local-first knowledge graph toolkit."""


def _init_contract(vault: Vault) -> None:
    from .storage import contract_log

    contract_log(vault, "kg", "init", {"root": str(vault.brain)}, {"ok": True})


def _index_contract(vault: Vault, args: dict[str, object], envelope: dict[str, object]) -> None:
    from .storage import contract_log

    contract_log(vault, "kg", "index", args, envelope, envelope.get("data") if envelope.get("ok") else None)


def _ingest_contract(vault: Vault, files: tuple[Path, ...], envelope: dict[str, object]) -> None:
    from .storage import contract_log

    contract_log(vault, "kg", "ingest", {"files": [str(f) for f in files]}, envelope, envelope.get("data"))


def _extract_contract(vault: Vault, proposal: Path, envelope: dict[str, object]) -> None:
    from .storage import contract_log

    contract_log(vault, "kg", "extract", {"proposal": str(proposal)}, envelope, envelope.get("data"))


@main.command("init")
@click.argument("root", type=click.Path(path_type=Path))
@click.option("--json", "as_json", is_flag=True)
def init_command(root: Path, as_json: bool) -> None:
    try:
        vault = _require_vault(root)
        envelope: dict[str, object] = ok({"root": str(vault.brain)})
        status = 0
        _init_contract(vault)
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
        envelope = error(_code_of(exc), str(exc))
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
        _index_contract(vault, {"rebuild": rebuild}, envelope)
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
        envelope = error(_code_of(exc), str(exc))
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
        _ingest_contract(vault, files, envelope)
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
        envelope = error(_code_of(exc), str(exc))
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
        _extract_contract(vault, proposal, envelope)
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
        envelope = error(_code_of(exc), str(exc))
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
        envelope = error(_code_of(exc), str(exc))
        status = 1
    _emit(as_json, envelope, status)
