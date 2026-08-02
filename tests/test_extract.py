import hashlib
import json
from pathlib import Path

import pytest

from kg.extract import extract, validate_proposal
from kg.ingest import capture
from kg.models import Proposal
from kg.storage import Vault


def test_extract_rejects_unknown_source_and_dangling_edge(tmp_path: Path) -> None:
    vault = Vault(tmp_path)
    proposal = {
        "schema_version": 1,
        "source_sha256": "f" * 64,
        "notes": [],
        "edges": [{"src": "nt_aaaaaaaaaaaaaaaa", "dst": "nt_bbbbbbbbbbbbbbbb", "relation": "causes", "confidence": 1.0}],
    }
    with pytest.raises(ValueError, match="unknown_source"):
        validate_proposal(vault, Proposal.model_validate(proposal))
    (tmp_path / "proposal.json").write_text(json.dumps(proposal), encoding="utf-8")
    with pytest.raises(ValueError):
        extract(vault, tmp_path / "proposal.json")


def test_extract_caps_notes_before_checkpoint(tmp_path: Path) -> None:
    vault = Vault(tmp_path)
    source = b"raw"
    source_path = tmp_path / "source.txt"
    source_path.write_bytes(source)
    capture(vault, [source_path])
    digest = hashlib.sha256(source).hexdigest()
    proposal: dict[str, object] = {"schema_version": 1, "source_sha256": digest, "notes": [], "edges": []}
    proposal["notes"] = [
        {
            "id": f"nt_{i:016x}",
            "kind": "concept",
            "type": None,
            "title": str(i),
            "status": "draft",
            "source_sha256": digest,
            "created": "2026-01-01",
            "updated": "2026-01-01",
            "refs": [],
            "tags": [],
            "provenance": [],
        }
        for i in range(501)
    ]
    path = tmp_path / "proposal.json"
    path.write_text(json.dumps(proposal), encoding="utf-8")
    with pytest.raises(ValueError, match="limit_error"):
        extract(vault, path)
    assert not list((tmp_path / ".brain" / ".kg" / "checkpoints").glob("*"))
