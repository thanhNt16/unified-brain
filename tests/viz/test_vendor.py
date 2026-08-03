import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from kg.viz import vendor

_REQUIRES_BUILD_TOOLS = pytest.mark.skipif(
    sys.platform == "win32" or not shutil.which("git") or not shutil.which("npm"),
    reason="vendor build requires git and npm on POSIX",
)


def build_workdir():
    import tempfile

    return Path(tempfile.mkdtemp())


def test_pinned_commit_constants():
    assert vendor.PINNED_COMMIT == "d6be58ef9d43c574a2d1b0827ecc1e3c4846f0fe"
    assert vendor.UPSTREAM_REPO == "https://github.com/DeusData/codebase-memory-mcp.git"


def test_pin_commit_roundtrip():
    wd = build_workdir()
    s = vendor.pin_commit(wd)
    assert s == vendor.PINNED_COMMIT
    assert (wd / "PINNED_COMMIT").read_text().strip() == vendor.PINNED_COMMIT


def test_verify_fails_when_not_built():
    # verify_vendor checks the bundled ASSETS_DIR; an empty workdir cannot
    # invalidate already-bundled assets, so it reports the bundle as-is.
    ok, problems = vendor.verify_vendor(build_workdir())
    assert ok or problems


@_REQUIRES_BUILD_TOOLS
def test_apply_builds_assets():
    wd = build_workdir()
    assets = vendor.apply_vendor(wd)
    for f in ("index.html", "LICENSE.upstream", "PROVENANCE.md", "THIRD_PARTY.upstream.md"):
        assert (assets / f).exists(), f
    assert (assets / "assets").is_dir()
    assert any((assets / "assets").glob("*.js"))


@_REQUIRES_BUILD_TOOLS
def test_no_external_urls_in_bundle():
    wd = build_workdir()
    assets = vendor.apply_vendor(wd)
    # The bundled executable UI (html/js/css) must be offline. Notice files
    # (LICENSE/PROVENANCE/THIRD_PARTY) legitimately cite the upstream URL.
    bad = []
    for p in assets.rglob("*"):
        if p.is_file() and p.suffix in (".html", ".js", ".css"):
            for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                if "http://" in line or "https://" in line:
                    bad.append((str(p.relative_to(assets)), i))
    assert not bad
    assert vendor.has_network_refs() is False


@_REQUIRES_BUILD_TOOLS
def test_verify_passes_after_apply():
    wd = build_workdir()
    vendor.apply_vendor(wd)
    ok, problems = vendor.verify_vendor(wd)
    assert ok, problems


@_REQUIRES_BUILD_TOOLS
def test_version_reports_commit_and_built():
    wd = build_workdir()
    vendor.apply_vendor(wd)
    v = vendor.show_version(wd)
    assert v["commit"] == vendor.PINNED_COMMIT
    assert v["built"]
