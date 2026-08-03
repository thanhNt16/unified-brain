"""Pinned source installer: verifies published SHA256 checksums before uv tool install.

No external network in tests; a local fake source server (file:// fixtures) and
fake curl/uv shims drive the script. A hash mismatch must refuse and clean temp.
"""

import hashlib
import os
import platform
import stat
import subprocess
from pathlib import Path

import pytest

_SKIP_WIN = pytest.mark.skipif(platform.system() == "Windows", reason="install.sh is a POSIX sh script")

INSTALLER = Path(__file__).parents[1] / "install.sh"

SOURCE_TARBALL = b"fake-source-tarball-bytes"
ARTIFACT_WHEEL = b"fake-artifact-wheel-bytes"


def _real_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _render_fixture_installer(tmp_path: Path, *, bad_source_hash: bool) -> Path:
    source = tmp_path / "source.tar.gz"
    artifact = tmp_path / "artifact.whl"
    checksums = tmp_path / "SHA256SUMS"
    source.write_bytes(SOURCE_TARBALL)
    artifact.write_bytes(ARTIFACT_WHEEL)
    source_hash = "0" * 64 if bad_source_hash else _real_hash(SOURCE_TARBALL)
    checksums.write_text(
        f"{source_hash}  source.tar.gz\n{_real_hash(ARTIFACT_WHEEL)}  artifact.whl\n",
        encoding="utf-8",
    )

    script = INSTALLER.read_text()
    source_line = next(line for line in script.splitlines() if line.startswith("SOURCE_URL="))
    artifact_line = next(line for line in script.splitlines() if line.startswith("ARTIFACT_URL="))
    checksum_line = next(line for line in script.splitlines() if line.startswith("CHECKSUM_URL="))
    script = script.replace(source_line, f'SOURCE_URL="file://{source}"')
    script = script.replace(artifact_line, f'ARTIFACT_URL="file://{artifact}"')
    script = script.replace(checksum_line, f'CHECKSUM_URL="file://{checksums}"')

    out = tmp_path / "install.sh"
    out.write_text(script, encoding="utf-8")
    out.chmod(out.stat().st_mode | stat.S_IXUSR)
    return out


def _fake_tools(tmp_path: Path) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "curl").write_text(
        "#!/bin/sh\n"
        'src=""; dst=""\n'
        'while [ "$#" -gt 0 ]; do\n'
        '  case "$1" in -fsSL|-f|-s|-S|-L|-o) ;; file://*) src="${1#file://}" ;; *) dst="$1" ;; esac\n'
        "  shift\n"
        "done\n"
        '[ -n "$src" ] && [ -n "$dst" ] || exit 1\n'
        'cp "$src" "$dst"\n'
    )
    (bindir / "uv").write_text(
        "#!/bin/sh\n"
        'mkdir -p "$HOME/.local/bin"\n'
        'printf "#!/bin/sh\\nprintf \\"kg 1.0.0\\\\n\\"\\n" > "$HOME/.local/bin/kg"\n'
        'chmod +x "$HOME/.local/bin/kg"\n'
    )
    for p in bindir.iterdir():
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return bindir


def _run(tmp_path: Path, script: Path) -> subprocess.CompletedProcess:
    work = tmp_path / "work"
    work.mkdir()
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    env = os.environ | {
        "PATH": f"{_fake_tools(tmp_path)}:{os.environ['PATH']}",
        "HOME": str(work / "home"),
        "TMPDIR": str(temp_root),
    }
    (work / "home").mkdir()
    return subprocess.run([str(script)], env=env, text=True, capture_output=True, check=False)


@_SKIP_WIN
def test_hash_mismatch_fails_and_cleans_temp(tmp_path):
    script = _render_fixture_installer(tmp_path, bad_source_hash=True)
    result = _run(tmp_path, script)
    assert result.returncode != 0
    assert "sha256" in (result.stdout + result.stderr).lower() or "sha" in (result.stdout + result.stderr).lower()
    assert not list((tmp_path / "tmp").glob("kg-install-*"))
    assert not (tmp_path / "work" / "home" / ".local" / "bin" / "kg").exists()


@_SKIP_WIN
def test_verified_install_succeeds_without_harness_mutation(tmp_path):
    script = _render_fixture_installer(tmp_path, bad_source_hash=False)
    work = tmp_path / "work"
    home = work / "home"
    harness = home / ".claude" / "skills"
    harness.mkdir(parents=True)
    marker = harness / "keep.md"
    marker.write_text("unchanged")
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    env = os.environ | {
        "PATH": f"{_fake_tools(tmp_path)}:{os.environ['PATH']}",
        "HOME": str(home),
        "TMPDIR": str(temp_root),
    }
    result = subprocess.run([str(script)], env=env, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "kg 1.0.0" in result.stdout
    assert marker.read_text() == "unchanged"
    assert "node" not in script.read_text().lower()
    assert not list(temp_root.glob("kg-install-*"))


def test_installer_embeds_pinned_commit_and_checksums_contract():
    script = INSTALLER.read_text()
    assert "2b4a37a3f2c143dd237bd0855ac81f97b638a1c1" in script
    assert "SOURCE_COMMIT=" in script
    assert "https://github.com/thanhNt16/unified-brain/" in script
    assert "github.com/harrynguyen/" not in script
    assert "shasum -a 256 -c" in script
    assert "uv tool install --from" in script
    assert "SOURCE_SHA256=" not in script  # no embedded placeholder hash
