"""kg viz command group: serve and vendor subcommands."""

from __future__ import annotations

import tempfile
from pathlib import Path

import click

from . import server, vendor


@click.group(name="viz")
def viz_group() -> None:
    """Graph visualization server and vendor tooling."""


@viz_group.command(name="serve")
@click.option("--port", default=9749, type=int, show_default=True)
@click.option("--wiki", default=None, type=click.Path(path_type=Path))
@click.option("--no-open", is_flag=True, help="Do not auto-open the browser")
def serve_command(port: int, wiki: Path | None, no_open: bool) -> None:
    """Serve the bundled graph UI on 127.0.0.1."""
    root = Path.cwd()
    brain = root / ".brain"
    if not brain.is_dir():
        raise click.ClickException("not a kg vault; run `kg init ROOT` first")
    db_path = brain / ".kg" / "brain.sqlite"
    if not db_path.is_file():
        raise click.ClickException("no brain.sqlite; run `kg index` first")
    server.serve(root, db_path, port=port, wiki=wiki, open_browser=not no_open)


@viz_group.command(name="vendor")
@click.option("--pin", "pin_value", default=vendor.PINNED_COMMIT, help="Commit to pin")
@click.option("--apply", is_flag=True, help="Fetch, build, and bundle upstream UI")
@click.option("--verify", is_flag=True, help="Check bundled assets and pin state")
@click.option("--version", "version_flag", is_flag=True, help="Show pinned commit and build state")
def vendor_command(pin_value: str, apply: bool, verify: bool, version_flag: bool) -> None:
    """Manage the pinned upstream graph UI at build time."""
    workdir = Path(tempfile.gettempdir()) / "kg-viz-vendor"
    if apply:
        assets = vendor.apply_vendor(workdir)
        click.echo(f"bundled assets -> {assets}")
        return
    if verify:
        ok, problems = vendor.verify_vendor(workdir)
        if ok:
            click.echo("vendor ok")
            return
        for problem in problems:
            click.echo(f"problem: {problem}")
        raise SystemExit(1)
    if version_flag:
        info = vendor.show_version(workdir)
        click.echo(f"commit: {info['commit']}")
        click.echo(f"built: {info['built']}")
        return
    click.echo(
        "kg viz vendor [--pin COMMIT] [--apply] [--verify] [--version]\n"
        "  --apply    fetch pristine upstream, build assets, bundle into src/kg/viz/assets\n"
        "  --verify   check bundled assets and pin state\n"
        "  --version  show pinned commit and build state"
    )


def main() -> None:
    """Standalone entrypoint: python -m kg.viz.cli viz ..."""
    viz_group()


if __name__ == "__main__":
    main()
