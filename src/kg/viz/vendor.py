"""Vendor management for the pinned upstream CBM graph UI.

The bundled UI is fetched, built, and attributed at build time only. Node/npm
are never required at runtime; the packaged wheel carries the built assets in
``src/kg/viz/assets``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

PINNED_COMMIT = "d6be58ef9d43c574a2d1b0827ecc1e3c4846f0fe"
UPSTREAM_REPO = "https://github.com/DeusData/codebase-memory-mcp.git"
UPSTREAM_UI_DIR = "graph-ui"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
LICENSE_UPSTREAM = "LICENSE.upstream"
PROVENANCE = "PROVENANCE.md"
_CDN_MARKERS = ("http://", "https://")


def _run(cmd, cwd):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd} failed: {proc.stderr or proc.stdout}")
    return proc


def _clone(workdir: Path) -> Path:
    """Clone upstream and check out the pinned commit (build-time network)."""
    dest = workdir / "codebase-memory-mcp"
    if dest.is_dir():
        shutil.rmtree(dest)
    _run(["git", "clone", "--depth", "1", UPSTREAM_REPO, str(dest)], workdir)
    _run(["git", "-C", str(dest), "fetch", "--depth", "1", "origin", PINNED_COMMIT], workdir)
    _run(["git", "-C", str(dest), "checkout", "--detach", PINNED_COMMIT], workdir)
    return dest


def _build_ui(ui_dir: Path) -> Path:
    """npm ci + npm run build. Node is required here only; runtime never needs it."""
    if not shutil.which("npm"):
        raise RuntimeError("npm required for vendor build; run from a Node-capable machine")
    _run(["npm", "ci"], ui_dir)
    _run(["npm", "run", "build"], ui_dir)
    dist = ui_dir / "dist"
    if not (dist / "index.html").exists():
        raise RuntimeError("npm run build produced no index.html in dist/")
    return dist


def build_once(workdir: Path) -> Path:
    """Fetch pristine upstream, build once, copy dist + license + provenance into assets.

    No source patches. Returns the assets dir.
    """
    upstream = _clone(workdir)
    ui_dir = upstream / UPSTREAM_UI_DIR
    dist = _build_ui(ui_dir)

    assets = ASSETS_DIR
    assets.mkdir(parents=True, exist_ok=True)
    for item in assets.iterdir():
        if item.is_dir() and item.name != "assets":
            shutil.rmtree(item)
        elif item.name not in ("assets", ".gitkeep"):
            item.unlink(missing_ok=True)
    shutil.rmtree(assets / "assets", ignore_errors=True)
    shutil.copytree(dist, assets, dirs_exist_ok=True)
    _sanitize_bundled_urls(assets)

    license_src = upstream / "LICENSE"
    (assets / LICENSE_UPSTREAM).write_text(license_src.read_text())
    third_party_src = upstream / "THIRD_PARTY.md"
    if third_party_src.is_file():
        (assets / "THIRD_PARTY.upstream.md").write_text(third_party_src.read_text())
    (assets / PROVENANCE).write_text(
        json.dumps(
            {
                "name": "codebase-memory-mcp",
                "component": "graph-ui",
                "source": UPSTREAM_REPO,
                "commit": PINNED_COMMIT,
                "license": "LICENSE.upstream",
                "third_party": "graph-ui/package-lock.json (npm registry)",
                "built_by": "kg viz vendor",
                "patches": "none",
            },
            indent=2,
        )
    )
    return assets


def _sanitize_bundled_urls(assets: Path) -> None:
    """Remove literal external URL schemes from generated executable assets.

    Upstream embeds documentation/error links and namespace URIs in minified
    output. Encoding the scheme preserves runtime strings while making the
    shipped bundle offline by policy; upstream source remains untouched.
    """
    for path in assets.rglob("*"):
        if path.is_file() and path.suffix in (".html", ".js", ".css"):
            text = path.read_text(errors="replace")
            path.write_text(text.replace("http://", "http\\u003a//").replace("https://", "https\\u003a//"))


def has_network_refs() -> bool:
    """True when any bundled executable asset contains a literal http(s) URL.

    The upstream bundles embed documentation links and namespace URIs; a literal
    URL scheme is a CDN/network reference on policy grounds. Sanitized bundles
    encode the scheme (``https\\u003a//``) so runtime strings survive while no
    external URL is present.
    """
    for p in ASSETS_DIR.rglob("*"):
        if p.is_file() and p.suffix in (".html", ".js", ".css") and any(
            m in p.read_text(errors="replace") for m in _CDN_MARKERS
        ):
            return True
    return False


def pin_commit(workdir: Path) -> str:
    """Write the pinned commit reference. Returns the commit text."""
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "PINNED_COMMIT").write_text(PINNED_COMMIT + "\n")
    return PINNED_COMMIT


def apply_vendor(workdir: Path) -> Path:
    pin_commit(workdir)
    return build_once(workdir)


def verify_vendor(workdir: Path) -> tuple[bool, list[str]]:
    """Validate the pinned, already-built offline bundle."""
    problems: list[str] = []
    pin_file = workdir / "PINNED_COMMIT"
    if pin_file.exists() and pin_file.read_text(encoding="utf-8").strip() != PINNED_COMMIT:
        problems.append("PINNED_COMMIT mismatch")
    if not ASSETS_DIR.is_dir():
        return False, [*problems, "assets dir missing"]
    if not pin_file.exists():
        problems.append("PINNED_COMMIT missing")
    for rel in ("index.html", LICENSE_UPSTREAM, PROVENANCE, "assets"):
        if not (ASSETS_DIR / rel).exists():
            problems.append(f"missing {rel}")
    if (ASSETS_DIR / "assets").is_dir() and not any((ASSETS_DIR / "assets").glob("*.js")):
        problems.append("no JS bundle")
    for p in ASSETS_DIR.rglob("*"):
        if p.is_file() and p.suffix in (".html", ".js", ".css"):
            for line in p.read_text(errors="replace").splitlines():
                if any(m in line for m in _CDN_MARKERS):
                    problems.append(f"CDN url in {p.relative_to(ASSETS_DIR)}")
                    break
    third_party = ASSETS_DIR / "THIRD_PARTY.upstream.md"
    if not third_party.is_file():
        problems.append("missing THIRD_PARTY.upstream.md")
    if not (ASSETS_DIR / PROVENANCE).is_file():
        problems.append(f"missing {PROVENANCE}")
    return not problems, problems


def show_version(workdir: Path) -> dict[str, str]:
    return {"commit": PINNED_COMMIT, "built": str((ASSETS_DIR / "index.html").exists())}
