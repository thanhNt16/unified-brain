import json
from pathlib import Path

from click.testing import CliRunner

from kg.cli import main


def _runner() -> CliRunner:
    return CliRunner()


def _proposal(digest: str, nid: str = "nt_cccccccccccccccc") -> dict:
    return {
        "schema_version": 1,
        "source_sha256": digest,
        "notes": [
            {
                "id": nid,
                "kind": "concept",
                "type": None,
                "title": "Contract",
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


def _env(output: str) -> dict:
    return json.loads(output)


def test_index_outside_vault_returns_not_initialized(tmp_path: Path) -> None:
    runner = _runner()
    result = runner.invoke(main, ["index", "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "not_initialized"
    assert not (tmp_path / ".brain").exists()


def test_unknown_source_maps_to_unknown_source_code(tmp_path: Path) -> None:
    runner = _runner()
    assert runner.invoke(main, ["init", str(tmp_path), "--json"]).exit_code == 0
    proposal = tmp_path / "p.json"
    proposal.write_text(json.dumps(_proposal("f" * 64)), encoding="utf-8")
    result = runner.invoke(main, ["extract", str(proposal), "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "unknown_source"
    result = runner.invoke(main, ["apply", str(proposal), "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "unknown_source"


def test_limit_error_code_via_cli(tmp_path: Path, monkeypatch) -> None:
    runner = _runner()
    assert runner.invoke(main, ["init", str(tmp_path), "--json"]).exit_code == 0
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "s.txt"
    source.write_bytes(b"x")
    ingested = runner.invoke(main, ["ingest", str(source), "--json"])
    digest = _env(ingested.output)["data"][0]["source_sha256"]
    proposal = _proposal(digest)
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
    path = tmp_path / "p.json"
    path.write_text(json.dumps(proposal), encoding="utf-8")
    result = runner.invoke(main, ["extract", str(path), "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "limit_error"
    assert not list((tmp_path / ".brain" / ".kg" / "checkpoints").glob("*"))


def test_dangling_edge_maps_to_dangling_edge_code(tmp_path: Path, monkeypatch) -> None:
    runner = _runner()
    assert runner.invoke(main, ["init", str(tmp_path), "--json"]).exit_code == 0
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "s.txt"
    source.write_bytes(b"x")
    digest = _env(runner.invoke(main, ["ingest", str(source), "--json"]).output)["data"][0]["source_sha256"]
    proposal = _proposal(digest)
    proposal["edges"] = [{"src": "nt_cccccccccccccccc", "dst": "nt_9999999999999999", "relation": "causes", "confidence": 1.0}]
    path = tmp_path / "p.json"
    path.write_text(json.dumps(proposal), encoding="utf-8")
    result = runner.invoke(main, ["extract", str(path), "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "dangling_edge"


def test_malformed_proposal_is_schema_validation(tmp_path: Path) -> None:
    runner = _runner()
    assert runner.invoke(main, ["init", str(tmp_path), "--json"]).exit_code == 0
    path = tmp_path / "p.json"
    path.write_text("not json", encoding="utf-8")
    result = runner.invoke(main, ["extract", str(path), "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "schema_validation"


def test_init_nonempty_root_creates_skeleton_alongside_content(tmp_path: Path) -> None:
    runner = _runner()
    (tmp_path / "existing.txt").write_text("x", encoding="utf-8")
    result = runner.invoke(main, ["init", str(tmp_path), "--json"])
    assert result.exit_code == 0
    assert _env(result.output)["ok"] is True
    assert (tmp_path / ".brain").is_dir()
    assert (tmp_path / "existing.txt").read_text() == "x"


def test_ingest_directory_expands_to_files_outside_vault(tmp_path: Path, monkeypatch) -> None:
    runner = _runner()
    vault = tmp_path / "vault"
    source_dir = tmp_path / "archive"
    (source_dir / "nested").mkdir(parents=True)
    (source_dir / "note.txt").write_text("archive note", encoding="utf-8")
    (source_dir / "nested" / "other.md").write_text("nested note", encoding="utf-8")
    assert runner.invoke(main, ["init", str(vault), "--json"]).exit_code == 0
    monkeypatch.chdir(vault)
    result = runner.invoke(main, ["ingest", str(source_dir), "--json"])
    assert result.exit_code == 0, result.output
    assert _env(result.output)["ok"] is True
    assert len(_env(result.output)["data"]) == 2



def test_version_option(tmp_path: Path) -> None:
    runner = _runner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert result.output == "kg 1.0.0\n"


def test_contract_log_rows_for_mutations(tmp_path: Path, monkeypatch) -> None:
    runner = _runner()
    assert runner.invoke(main, ["init", str(tmp_path), "--json"]).exit_code == 0
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "s.txt"
    source.write_bytes(b"x")
    assert runner.invoke(main, ["ingest", str(source), "--json"]).exit_code == 0
    digest = _env(runner.invoke(main, ["ingest", str(source), "--json"]).output)["data"][0]["source_sha256"]
    proposal = tmp_path / "p.json"
    proposal.write_text(json.dumps(_proposal(digest)), encoding="utf-8")
    assert runner.invoke(main, ["extract", str(proposal), "--json"]).exit_code == 0
    assert runner.invoke(main, ["apply", str(proposal), "--json"]).exit_code == 0
    assert runner.invoke(main, ["index", "--json"]).exit_code == 0
    rows = [
        json.loads(line)
        for line in (tmp_path / ".brain" / ".kg" / "contract.jsonl").read_text().strip().splitlines()
    ]
    cmds = [row["cmd"] for row in rows]
    assert cmds == ["init", "ingest", "ingest", "extract", "apply", "index"]
    for row in rows:
        assert row["ok"] is True
        assert row["envelope"]["ok"] is True
        assert "error" in row
        assert "data" in row
    seqs = [row["seq"] for row in rows]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
