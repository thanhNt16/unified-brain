import json
import sqlite3
from pathlib import Path

from click.testing import CliRunner

from kg.cli import main


def test_m2_flow_and_rebuild_recovery(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    assert runner.invoke(main, ["init", str(tmp_path), "--json"]).exit_code == 0
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "source.md"
    source.write_text("source", encoding="utf-8")
    ingest = runner.invoke(main, ["ingest", str(source), "--json"])
    assert ingest.exit_code == 0
    digest = json.loads(ingest.output)["data"][0]["source_sha256"]
    proposal = {
        "schema_version": 1,
        "source_sha256": digest,
        "notes": [
            {
                "id": "nt_bbbbbbbbbbbbbbbb",
                "kind": "concept",
                "type": None,
                "title": "Beta",
                "status": "verified",
                "source_sha256": digest,
                "created": "2026-01-01",
                "updated": "2026-01-01",
                "refs": [],
                "tags": [],
                "provenance": [],
            }
        ],
        "edges": [],
    }
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
    assert runner.invoke(main, ["extract", str(proposal_path), "--json"]).exit_code == 0
    assert runner.invoke(main, ["apply", str(proposal_path), "--json"]).exit_code == 0
    db = tmp_path / ".brain" / ".kg" / "brain.sqlite"
    conn = sqlite3.connect(db)
    assert conn.execute("select count(*) from notes where id='nt_bbbbbbbbbbbbbbbb'").fetchone()[0] == 1
    conn.close()
    db.unlink()
    monkeypatch.chdir(tmp_path)
    rebuilt = runner.invoke(main, ["index", "--rebuild", "--json"])
    assert rebuilt.exit_code == 0
    assert json.loads(rebuilt.output)["ok"] is True
    assert (tmp_path / ".brain" / ".kg" / "contract.jsonl").exists()
