from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import NoReturn

import click

from . import dream as dream_module
from . import install as install_module
from . import retrieval as retrieval_module
from . import review as review_module
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
    "diff_path": ErrorCodes.diff_path,
    "diff_state": ErrorCodes.diff_state,
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


@main.command("query")
@click.argument("query")
@click.option("--strategy", default="adaptive", type=click.Choice(["adaptive", "lexical"]))
@click.option("--hops", default=2, type=int)
@click.option("--relations", default="causes,depends_on,related_to")
@click.option("--direction", default="both", type=click.Choice(["both", "in", "out"]))
@click.option("--limit", default=20, type=int)
@click.option("--context", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
def query_command(
    query: str,
    strategy: str,
    hops: int,
    relations: str,
    direction: str,
    limit: int,
    context: bool,
    as_json: bool,
) -> None:
    try:
        rels = tuple(r.strip() for r in relations.split(",") if r.strip())
        try:
            retrieval_module.validate_query_params(hops, direction, limit, rels, strategy)
        except ValueError as exc:
            raise ValueError(f"limit_error: {exc}") from exc
        vault = _require_vault()
        assert vault.kg is not None
        db = vault.kg / "brain.sqlite"
        if not db.exists():
            raise ValueError("not_initialized: run kg index first")
        conn = sqlite3.connect(db)
        try:
            data = retrieval_module.query(
                conn,
                vault,
                query,
                strategy=strategy,
                hops=hops,
                relations=rels,
                direction=direction,
                limit=limit,
                context=context,
            )
        finally:
            conn.close()
        envelope = ok(data)
        status = 0
        from .storage import contract_log

        contract_log(vault, "kg", "query", {"query": query}, envelope, data)
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
        envelope = error(_code_of(exc), str(exc))
        status = 1
    _emit(as_json, envelope, status)


@main.command("dream")
@click.option("--passes", default=",".join(dream_module.PASSES))
@click.option("--out", "out_path", type=click.Path(path_type=Path))
@click.option("--json", "as_json", is_flag=True)
def dream_command(passes: str, out_path: Path | None, as_json: bool) -> None:
    try:
        requested = tuple(p.strip() for p in passes.split(",") if p.strip())
        unknown = set(requested) - set(dream_module.PASSES)
        if unknown:
            raise ValueError("limit_error: unknown dream pass")
        vault = _require_vault()
        assert vault.kg is not None
        db = vault.kg / "brain.sqlite"
        if not db.exists():
            raise ValueError("not_initialized: run kg index first")
        conn = sqlite3.connect(db)
        try:
            diff = dream_module.run(conn, vault, passes=requested)
        finally:
            conn.close()
        dreams_dir = vault.kg / "dreams"
        target = (out_path if out_path is not None else dreams_dir / f"{diff.id}.json").resolve()
        if target.parent != dreams_dir:
            raise ValueError("path_forbidden: --out must stay under .brain/.kg/dreams")
        payload = json.dumps(
            {
                "id": diff.id,
                "status": diff.status,
                "operations": [operation.model_dump() for operation in diff.operations],
            },
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"
        from .storage import atomic_write

        atomic_write(target, payload.encode("utf-8"))
        data: dict[str, object] = {
            "id": diff.id,
            "path": str(target),
            "operations": len(diff.operations),
        }
        envelope = ok(data)
        status = 0
        from .storage import contract_log

        contract_log(vault, "kg", "dream", {"passes": list(requested)}, envelope, data)
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
        envelope = error(_code_of(exc), str(exc))
        status = 1
    _emit(as_json, envelope, status)


@main.command("review")
@click.argument("diff", type=click.Path(path_type=Path, exists=True))
@click.option("--approve", is_flag=True)
@click.option("--reject", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
def review_command(diff: Path, approve: bool, reject: bool, as_json: bool) -> None:
    if approve and reject:
        envelope = error(ErrorCodes.limit_error, "--approve and --reject are mutually exclusive")
        _emit(as_json, envelope, 2)
        return
    try:
        action = "approve" if approve else ("reject" if reject else None)
        vault = _require_vault(anchor=diff)
        data = review_module.review(vault, diff, action=action)
        envelope = ok(data)
        status = 0
        from .storage import contract_log

        if action is not None:
            contract_log(vault, "kg", "review", {"diff": str(diff), "action": action}, envelope, data)
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
        envelope = error(_code_of(exc), str(exc))
        status = 1
    _emit(as_json, envelope, status)


@main.command("install")
@click.option("--root", "root_path", type=click.Path(path_type=Path), default=Path("."), show_default=True)
@click.option("--apply", "do_apply", is_flag=True)
@click.option("--uninstall", "do_uninstall", is_flag=True)
@click.option("--force", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
def install_command(root_path: Path, do_apply: bool, do_uninstall: bool, force: bool, as_json: bool) -> None:
    if do_apply and do_uninstall:
        envelope = error(ErrorCodes.limit_error, "--apply and --uninstall are mutually exclusive")
        _emit(as_json, envelope, 2)
        return
    try:
        data: object
        if do_uninstall:
            data = install_module.uninstall(root_path)
        elif do_apply:
            data = install_module.apply_install(install_module.plan_install(root_path, force=force))
        else:
            data = install_module.format_plan(install_module.plan_install(root_path, force=force))
        envelope = ok(data)
        status = 0
    except install_module.InstallError as exc:
        envelope = error(ErrorCodes.path_forbidden, str(exc))
        status = 1
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
