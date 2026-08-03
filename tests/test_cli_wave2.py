"""Serialized CLI wave 2: root-imported viz group, graph export, cron-print.

Covers the frozen envelope contract from spec section 5/13: success
`{ok:true,data:{...}}`, failure `{ok:false,error:{code,message}}`. The root
`kg` group must append the existing `kg.viz.cli` viz_group (serve/vendor, no
duplicate logic), `kg graph --format mermaid|dot` must be a bounded
deterministic read-only export capped at 500 edges with `unsupported_format`
rejected before DB work, and `kg cron-print` must print instructions only.
"""

import json
from pathlib import Path

from click.testing import CliRunner

from kg.cli import main


def _runner() -> CliRunner:
    return CliRunner()


def _env(output: str) -> dict:
    return json.loads(output)


def _vault_with_note(tmp_path: Path, monkeypatch) -> Path:
    runner = _runner()
    root = tmp_path / "vault"
    assert runner.invoke(main, ["init", str(root), "--json"]).exit_code == 0
    monkeypatch.chdir(root)
    source = root / "s.txt"
    source.write_bytes(b"source body")
    ingested = runner.invoke(main, ["ingest", str(source), "--json"])
    assert ingested.exit_code == 0, ingested.output
    digest = _env(ingested.output)["data"][0]["source_sha256"]
    proposal = {
        "schema_version": 1,
        "source_sha256": digest,
        "notes": [
            {
                "id": "nt_aaaaaaaaaaaaaaaa",
                "kind": "concept",
                "type": None,
                "title": "Alpha",
                "status": "verified",
                "source_sha256": digest,
                "created": "2026-01-01T00:00:00Z",
                "updated": "2026-01-01T00:00:00Z",
                "refs": [],
                "tags": [],
                "provenance": [],
                "body": "Alpha primary store",
            },
            {
                "id": "nt_bbbbbbbbbbbbbbbb",
                "kind": "concept",
                "type": None,
                "title": "Beta",
                "status": "verified",
                "source_sha256": digest,
                "created": "2026-01-01T00:00:00Z",
                "updated": "2026-01-01T00:00:00Z",
                "refs": [],
                "tags": [],
                "provenance": [],
                "body": "Beta follows Alpha",
            },
        ],
        "edges": [
            {"src": "nt_aaaaaaaaaaaaaaaa", "dst": "nt_bbbbbbbbbbbbbbbb", "relation": "causes", "confidence": 1.0}
        ],
    }
    path = root / "p.json"
    path.write_text(json.dumps(proposal), encoding="utf-8")
    applied = runner.invoke(main, ["apply", str(path), "--json"])
    assert applied.exit_code == 0, applied.output
    return root


def test_viz_group_registered_at_root_with_serve_vendor(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["viz", "--help"])
    assert result.exit_code == 0
    assert "serve" in result.output
    assert "vendor" in result.output
    # Root help lists the viz group; commands are not duplicated on the root.
    root_help = _runner().invoke(main, ["--help"]).output
    assert "viz" in root_help


def test_viz_help_lists_serve_and_vendor(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["viz", "--help"])
    assert result.exit_code == 0
    assert result.output.count("serve") >= 1
    assert result.output.count("vendor") >= 1


def test_viz_vendor_nondefault_pin_rejected_before_work(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["viz", "vendor", "--pin", "deadbeef", "--apply"])
    assert result.exit_code != 0
    assert "immutable" in result.output


def test_viz_serve_missing_vault_is_click_exception(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = _runner().invoke(main, ["viz", "serve", "--no-open"])
    assert result.exit_code != 0
    assert "not a kg vault" in result.output


def test_graph_help_shows_format_and_json(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["graph", "--help"])
    assert result.exit_code == 0
    for flag in ("--format", "--json"):
        assert flag in result.output


def test_graph_mermaid_export(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path, monkeypatch)
    monkeypatch.chdir(root)
    result = _runner().invoke(main, ["graph", "--format", "mermaid", "--json"])
    assert result.exit_code == 0
    env = _env(result.output)
    assert env["ok"] is True
    data = env["data"]
    assert data["format"] == "mermaid"
    assert data["notes"] == 2
    assert data["edges"] == 1
    assert data["truncated"] is False
    graph = data["graph"]
    assert "graph LR" in graph
    assert "nt_aaaaaaaaaaaaaaaa" in graph
    assert "nt_bbbbbbbbbbbbbbbb" in graph
    assert "causes" in graph


def test_graph_dot_export(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path, monkeypatch)
    monkeypatch.chdir(root)
    result = _runner().invoke(main, ["graph", "--format", "dot", "--json"])
    assert result.exit_code == 0
    env = _env(result.output)
    assert env["ok"] is True
    data = env["data"]
    assert data["format"] == "dot"
    assert data["notes"] == 2
    assert data["edges"] == 1
    graph = data["graph"]
    assert graph.startswith("digraph kg {")
    assert graph.rstrip().endswith("}")
    assert "causes" in graph


def test_graph_default_format_is_mermaid(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path, monkeypatch)
    monkeypatch.chdir(root)
    result = _runner().invoke(main, ["graph", "--json"])
    assert result.exit_code == 0
    assert _env(result.output)["data"]["format"] == "mermaid"


def test_graph_deterministic_output(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path, monkeypatch)
    monkeypatch.chdir(root)
    runner = _runner()
    first = _env(runner.invoke(main, ["graph", "--json"]).output)
    second = _env(runner.invoke(main, ["graph", "--json"]).output)
    assert first["data"]["graph"] == second["data"]["graph"]


def test_graph_unsupported_format_before_db(tmp_path: Path) -> None:
    # Validation must fail before any vault/DB work: no vault exists here.
    result = _runner().invoke(main, ["graph", "--format", "png", "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "unsupported_format"
    assert not (tmp_path / ".brain").exists()


def test_graph_read_only_no_mutation(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path, monkeypatch)
    monkeypatch.chdir(root)
    result = _runner().invoke(main, ["graph", "--json"])
    assert result.exit_code == 0
    # Only init/ingest/apply wrote contract rows; graph appends one audit row.
    rows = [
        json.loads(line)
        for line in (root / ".brain" / ".kg" / "contract.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert [row["cmd"] for row in rows] == ["init", "ingest", "apply", "graph"]
    assert rows[-1]["args"] == {"format": "mermaid"}
    assert rows[-1]["ok"] is True


def test_cron_print_instructions_only(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "vault"
    assert _runner().invoke(main, ["init", str(root), "--json"]).exit_code == 0
    monkeypatch.chdir(root)
    result = _runner().invoke(main, ["cron-print", "--json"])
    assert result.exit_code == 0
    env = _env(result.output)
    assert env["ok"] is True
    instructions = env["data"]["instructions"]
    for section in ("cron", "launchd", "systemd", "Task Scheduler"):
        assert section in instructions
    assert "kg index --rebuild" in instructions
    assert str(root) in instructions


def test_init_applies_schema_and_writes_manifest(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    result = _runner().invoke(main, ["init", str(root), "--json"])
    assert result.exit_code == 0, result.output
    env = _env(result.output)
    assert env["ok"] is True
    assert (root / ".brain" / ".kg" / "brain.sqlite").exists()
    manifest = json.loads((root / ".brain" / ".kg" / "manifest.json").read_text())
    assert manifest["version"] == "1.0.0"
    assert "created" in manifest


def test_init_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    first = _runner().invoke(main, ["init", str(root), "--json"])
    assert first.exit_code == 0, first.output
    second = _runner().invoke(main, ["init", str(root), "--json"])
    assert second.exit_code == 0, second.output


def test_cron_print_outside_vault_emits_envelope(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = _runner().invoke(main, ["cron-print", "--json"])
    assert result.exit_code == 1
    env = _env(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "not_initialized"


def test_dream_custom_out_filename_is_rewritten_to_reviewable_stem(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path, monkeypatch)
    monkeypatch.chdir(root)
    result = _runner().invoke(main, ["dream", "--passes", "dedup", "--out", ".brain/.kg/dreams/custom.json", "--json"])
    assert result.exit_code == 0, result.output
    dreams_dir = root / ".brain" / ".kg" / "dreams"
    files = list(dreams_dir.glob("*.json"))
    assert len(files) == 1
    diff = json.loads(files[0].read_text())
    assert files[0].stem == diff["id"]
    review = _runner().invoke(main, ["review", str(files[0]), "--approve", "--json"])
    assert review.exit_code == 0, review.output
