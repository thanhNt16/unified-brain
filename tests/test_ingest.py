from pathlib import Path

import pytest

from kg.ingest import capture
from kg.storage import discover_vault


def test_capture_deduplicates_bytes_and_rejects_symlink(tmp_path: Path) -> None:
    vault = discover_vault(tmp_path)
    source = tmp_path / "source.txt"
    source.write_bytes(b"same bytes")
    first = capture(vault, [source])
    second = capture(vault, [source])
    assert first[0]["source_sha256"] == second[0]["source_sha256"]
    assert first[0]["status"] == "captured"
    assert second[0]["status"] == "deduped"
    assert len(list((tmp_path / ".brain" / "raw").iterdir())) == 1
    link = tmp_path / "link.txt"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="path_forbidden"):
        capture(vault, [link])
