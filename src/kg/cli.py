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
from .release import VERSION
from .storage import Vault, discover_vault
from .viz.cli import viz_group

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
    "not_found": ErrorCodes.not_found,
    "unsupported_format": ErrorCodes.unsupported_format,
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


def _existing(path: Path | None, label: str) -> Path:
    if path is None or not path.exists():
        raise ValueError(f"not_found: {label} does not exist")
    return path


def _install_code(exc: install_module.InstallError) -> ErrorCodes:
    message = str(exc)
    if message.startswith("refusing unowned overwrite"):
        return ErrorCodes.forbidden
    if message.startswith("overwrite requires --force"):
        return ErrorCodes.limit_error
    return ErrorCodes.path_forbidden


@click.group()
@click.version_option(version=VERSION, prog_name="kg", message="%(prog)s %(version)s")
def main() -> None:
    """Local-first knowledge graph toolkit."""


main.add_command(viz_group)


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
@click.argument("files", nargs=-1, type=click.Path(path_type=Path))
@click.option("--json", "as_json", is_flag=True)
def ingest_command(files: tuple[Path, ...], as_json: bool) -> None:
    try:
        if not files:
            raise ValueError("limit_error: at least one file is required")
        files = tuple(_existing(path, "file") for path in files)
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
@click.argument("proposal", type=click.Path(path_type=Path))
@click.option("--json", "as_json", is_flag=True)
def extract_command(proposal: Path, as_json: bool) -> None:
    try:
        proposal = _existing(proposal, "proposal")
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
@click.option("--strategy", default="adaptive")
@click.option("--hops", default="2", type=str)
@click.option("--relations", default="causes,depends_on,related_to")
@click.option("--direction", default="both")
@click.option("--limit", default="20", type=str)
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
        try:
            hops = int(hops)
        except ValueError:
            raise ValueError("limit_error: hops must be an integer") from None
        try:
            limit = int(limit)
        except ValueError:
            raise ValueError("limit_error: limit must be an integer") from None
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
        args: dict[str, object] = {
            "query": query,
            "strategy": strategy,
            "hops": hops,
            "relations": relations,
            "direction": direction,
            "limit": limit,
            "context": context,
        }
        from .storage import contract_log

        contract_log(vault, "kg", "query", args, envelope, data)
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

        contract_log(
            vault,
            "kg",
            "dream",
            {"passes": list(requested), "out": str(out_path) if out_path is not None else None},
            envelope,
            data,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
        envelope = error(_code_of(exc), str(exc))
        status = 1
    _emit(as_json, envelope, status)


@main.command("review")
@click.argument("diff", type=click.Path(path_type=Path))
@click.option("--approve", is_flag=True)
@click.option("--reject", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
def review_command(diff: Path, approve: bool, reject: bool, as_json: bool) -> None:
    try:
        if approve and reject:
            raise ValueError("limit_error: --approve and --reject are mutually exclusive")
        diff = _existing(diff, "diff")
        action = "approve" if approve else ("reject" if reject else None)
        vault = _require_vault(anchor=diff)
        data = review_module.review(vault, diff, action=action)
        envelope = ok(data)
        status = 0
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
        envelope = error(_install_code(exc), str(exc))
        status = 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
        envelope = error(_code_of(exc), str(exc))
        status = 1
    _emit(as_json, envelope, status)


@main.command("apply")
@click.argument("proposal", type=click.Path(path_type=Path))
@click.option("--json", "as_json", is_flag=True)
def apply_command(proposal: Path, as_json: bool) -> None:
    try:
        proposal = _existing(proposal, "proposal")
        vault = _require_vault(anchor=proposal)
        from .apply import apply_proposal

        data = apply_proposal(vault, proposal)
        envelope = ok(data)
        status = 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
        envelope = error(_code_of(exc), str(exc))
        status = 1
    _emit(as_json, envelope, status)


@main.command("graph")
@click.option("--format", "format_name", default="mermaid")
@click.option("--json", "as_json", is_flag=True)
def graph_command(format_name: str, as_json: bool) -> None:
    """Export a bounded static graph (max 500 edges)."""
    try:
        if format_name not in ("mermaid", "dot"):
            raise ValueError("unsupported_format")
        vault = _require_vault()
        assert vault.kg is not None
        db = vault.kg / "brain.sqlite"
        if not db.exists():
            raise ValueError("not_initialized: run kg index first")
        conn = sqlite3.connect(db)
        try:
            rows = conn.execute(
                "SELECT n.id, n.kind, n.type, n.title, e.src, e.dst, e.relation "
                "FROM notes n LEFT JOIN edges e ON n.id IN (e.src, e.dst) "
                "WHERE n.status NOT IN ('tombstone','superseded') "
                "ORDER BY n.id, e.src, e.dst, e.relation LIMIT 500"
            ).fetchall()
        finally:
            conn.close()
        nodes: dict[str, tuple[str, str | None, str]] = {}
        edges: list[tuple[str, str, str]] = []
        for note_id, kind, note_type, title, src, dst, relation in rows:
            nodes.setdefault(note_id, (kind, note_type, title))
            if src is not None:
                edge = (src, dst, relation)
                if edge not in edges:
                    edges.append(edge)
        if format_name == "mermaid":
            lines = ["graph LR"]
            for node_id in sorted(nodes):
                _kind, _type, title = nodes[node_id]
                label = (title or node_id).replace('"', "'")
                lines.append(f'  {node_id}["{label}"]')
            for src, dst, relation in edges:
                lines.append(f"  {src} -->|{relation}| {dst}")
            data: dict[str, object] = {
                "format": "mermaid",
                "notes": len(nodes),
                "edges": len(edges),
                "truncated": len(rows) >= 500,
                "graph": "\n".join(lines),
            }
        else:
            lines = ["digraph kg {"]
            for node_id in sorted(nodes):
                _kind, _type, title = nodes[node_id]
                label = (title or node_id).replace('"', "'")
                lines.append(f'  "{node_id}" [label="{label}"];')
            for src, dst, relation in edges:
                lines.append(f'  "{src}" -> "{dst}" [label="{relation}"];')
            lines.append("}")
            data = {
                "format": "dot",
                "notes": len(nodes),
                "edges": len(edges),
                "truncated": len(rows) >= 500,
                "graph": "\n".join(lines),
            }
        envelope = ok(data)
        status = 0
        from .storage import contract_log

        contract_log(
            vault,
            "kg",
            "graph",
            {"format": format_name},
            envelope,
            data,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary must emit structured failures
        envelope = error(_code_of(exc), str(exc))
        status = 1
    _emit(as_json, envelope, status)


@main.command("cron-print")
@click.option("--json", "as_json", is_flag=True)
def cron_print_command(as_json: bool) -> None:
    """Print safe scheduler instructions; never schedules or starts a daemon."""
    vault = _require_vault()
    root = str(vault.brain)
    instructions = (
        "# kg cron-print: scheduler instructions only (kg never schedules or runs a daemon).\n"
        "\n"
        "# Cron (every day at 03:15 local time):\n"
        '15 3 * * * cd "' + root + '" && kg index --rebuild --json\n'
        "\n"
        "# launchd (macOS) - place a plist under ~/Library/LaunchAgents/ and `launchctl load`:\n"
        "#   Label: com.example.kg-index\n"
        "#   ProgramArguments: [\"/usr/local/bin/kg\", \"index\", \"--rebuild\", \"--json\"]\n"
        "#   StartCalendarInterval: {\"Hour\": 3, \"Minute\": 15}\n"
        "#   WorkingDirectory: " + root + "\n"
        "\n"
        "# systemd (Linux) - timer unit pair under ~/.config/systemd/user/:\n"
        "#   kg-index.service:\n"
        "#     [Service]\n"
        "#     WorkingDirectory=" + root + "\n"
        "#     ExecStart=/usr/local/bin/kg index --rebuild --json\n"
        "#   kg-index.timer:\n"
        "#     [Timer]\n"
        "#     OnCalendar=*-*-* 03:15:00\n"
        "#     Persistent=true\n"
        "#   then: systemctl --user daemon-reload && systemctl --user enable --now kg-index.timer\n"
        "\n"
        "# Task Scheduler (Windows) - via PowerShell:\n"
        "#   New-ScheduledTaskAction -Execute 'kg' -Argument 'index --rebuild --json' -WorkingDirectory '" + root + "'\n"
        "#   New-ScheduledTaskTrigger -Daily -At 3:15AM\n"
        "#   Register-ScheduledTask -TaskName 'kg-index' -Action $action -Trigger $trigger\n"
    )
    envelope = ok({"instructions": instructions})
    _emit(as_json, envelope, 0)


if __name__ == "__main__":
    main()
