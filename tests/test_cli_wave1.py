"""Serialized CLI wave 1: query, dream, review, install commands.

Covers command registration, help, JSON success/error codes, validation
before any DB work, review flag exclusivity + default read-only, and the
install plan/no-write/apply/uninstall lifecycle. Exercises the frozen
envelope contract from spec section 5/13: success `{ok:true,data:{...}}`,
failure `{ok:false,error:{code,message}}`.
"""

import json
from pathlib import Path

from click.testing import CliRunner

from kg.cli import main


def _runner() -> CliRunner:
    return CliRunner()


def _env(output: str) -> dict:
    return json.loads(output)


def _vault_with_note(tmp_path: Path) -> Path:
    """init + ingest + apply a minimal proposal so the vault has a live DB."""
    runner = _runner()
    root = tmp_path / "vault"
    assert runner.invoke(main, ["init", str(root), "--json"]).exit_code == 0
    # The source lives inside the vault root so ingest's anchor discovery finds .brain.
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


def test_wave1_commands_registered_and_in_help(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["--help"])
    assert result.exit_code == 0
    for name in ("query", "dream", "review", "install"):
        assert name in result.output
    for name in ("init", "ingest", "extract", "apply", "index"):
        assert name in result.output
    assert _runner().invoke(main, ["--version"]).output == "kg 1.0.0\n"


def test_query_help_shows_exact_options(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["query", "--help"])
    assert result.exit_code == 0
    for flag in ("--strategy", "--hops", "--relations", "--direction", "--limit", "--context", "--json"):
        assert flag in result.output


def test_query_json_success_envelope(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path)
    monkeypatch.chdir(root)
    runner = _runner()
    result = runner.invoke(main, ["query", "Alpha", "--json"])
    assert result.exit_code == 0
    env = _env(result.output)
    assert env["ok"] is True
    data = env["data"]
    assert data["strategy_used"] == "adaptive"
    assert "seed_counts" in data and "visited_count" in data
    assert any(r["id"] == "nt_aaaaaaaaaaaaaaaa" for r in data["results"])
    top = data["results"][0]
    for key in ("id", "title", "kind", "score", "ppr_score", "seed_ranks", "depth", "paths", "sources", "evidence", "snippet", "path"):
        assert key in top
    # query appends an audit row but never mutates notes or the DB.
    rows = [
        json.loads(line)
        for line in (root / ".brain" / ".kg" / "contract.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert [row["cmd"] for row in rows] == ["init", "ingest", "apply", "query"]
    assert rows[-1]["ok"] is True


def test_query_context_flag(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path)
    monkeypatch.chdir(root)
    result = _runner().invoke(main, ["query", "Alpha", "--context", "--json"])
    assert result.exit_code == 0
    assert "context" in _env(result.output)["data"]


def test_query_validation_before_db(tmp_path: Path) -> None:
    # No vault exists in cwd: validation must fail before any vault/DB work.
    runner = _runner()
    result = runner.invoke(main, ["query", "x", "--hops", "5", "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "limit_error"
    result = runner.invoke(main, ["query", "x", "--relations", "not_a_relation", "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "limit_error"
    assert not (tmp_path / ".brain").exists()


def test_query_non_integer_limit_and_hops_are_limit_error(tmp_path: Path) -> None:
    runner = _runner()
    for args in (["--limit", "abc"], ["--hops", "two"]):
        result = runner.invoke(main, ["query", "x", *args, "--json"])
        assert result.exit_code == 1
        env = _env(result.output)
        assert env["ok"] is False
        assert env["error"]["code"] == "limit_error"


def test_query_full_args_in_contract_row(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path)
    monkeypatch.chdir(root)
    result = _runner().invoke(main, ["query", "Alpha", "--strategy", "lexical", "--hops", "1", "--limit", "5", "--json"])
    assert result.exit_code == 0
    rows = [
        json.loads(line)
        for line in (root / ".brain" / ".kg" / "contract.jsonl").read_text().splitlines()
        if line.strip()
    ]
    args = rows[-1]["args"]
    assert args["query"] == "Alpha"
    assert args["strategy"] == "lexical"
    assert args["hops"] == 1
    assert args["relations"] == "causes,depends_on,related_to"
    assert args["direction"] == "both"
    assert args["limit"] == 5
    assert args["context"] is False


def test_review_nonexistent_diff_is_not_found_json(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["review", str(tmp_path / "nope.json"), "--json"])
    assert result.exit_code == 1
    env = _env(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "not_found"


def test_ingest_nonexistent_file_is_not_found_json(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["ingest", str(tmp_path / "nope.txt"), "--json"])
    assert result.exit_code == 1
    env = _env(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "not_found"


def test_ingest_requires_at_least_one_file(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["ingest", "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "limit_error"


def test_apply_nonexistent_proposal_is_not_found_json(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["apply", str(tmp_path / "nope.json"), "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "not_found"


def test_install_force_required_is_limit_error(tmp_path: Path) -> None:
    root = tmp_path / "harness"
    assert _runner().invoke(main, ["install", "--root", str(root), "--apply", "--json"]).exit_code == 0
    # Drift an owned file so the next plan demands --force.
    target = root / ".claude" / "commands" / "kg" / "init.md"
    target.write_text(target.read_text().replace("# kg:init", "# Changed"), encoding="utf-8")
    result = _runner().invoke(main, ["install", "--root", str(root), "--apply", "--json"])
    assert result.exit_code == 1
    env = _env(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "limit_error"
    # The drifted file survives an unforced failed apply.
    assert "Changed" in target.read_text()


def test_install_unowned_overwrite_is_forbidden(tmp_path: Path) -> None:
    root = tmp_path / "harness"
    target = root / ".claude" / "commands" / "kg" / "init.md"
    target.parent.mkdir(parents=True)
    target.write_text("user content\n", encoding="utf-8")
    result = _runner().invoke(main, ["install", "--root", str(root), "--apply", "--json"])
    assert result.exit_code == 1
    env = _env(result.output)
    assert env["ok"] is False
    assert env["error"]["code"] == "forbidden"
    assert target.read_text() == "user content\n"


def test_query_unknown_direction_and_strategy_rejected(tmp_path: Path) -> None:
    runner = _runner()
    for args in (["--direction", "sideways"], ["--strategy", "magic"]):
        result = runner.invoke(main, ["query", "x", *args, "--json"])
        assert result.exit_code == 1
        env = _env(result.output)
        assert env["ok"] is False
        assert env["error"]["code"] == "limit_error"


def test_query_lexical_strategy_and_json_absent(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path)
    monkeypatch.chdir(root)
    result = _runner().invoke(main, ["query", "Alpha", "--strategy", "lexical"])
    assert result.exit_code == 0
    # Human mode emits the data payload directly through the shared helper.
    env = _env(result.output)
    assert env["strategy_used"] == "lexical"


def test_dream_success_writes_diff_under_dreams(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path)
    monkeypatch.chdir(root)
    result = _runner().invoke(main, ["dream", "--passes", "dedup,orphan", "--json"])
    assert result.exit_code == 0
    env = _env(result.output)
    assert env["ok"] is True
    data = env["data"]
    assert data["id"].startswith("df_")
    assert data["operations"] >= 0
    diff_path = Path(data["path"])
    assert diff_path.parent == root / ".brain" / ".kg" / "dreams"
    payload = json.loads(diff_path.read_text())
    assert payload["status"] == "proposed"
    assert payload["id"] == data["id"]


def test_dream_default_is_all_seven_passes(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path)
    monkeypatch.chdir(root)
    result = _runner().invoke(main, ["dream", "--json"])
    assert result.exit_code == 0
    assert _env(result.output)["ok"] is True


def test_dream_unknown_pass_is_limit_error(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["dream", "--passes", "nope", "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "limit_error"


def test_dream_out_inside_dreams_and_json_absent(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path)
    monkeypatch.chdir(root)
    target = root / ".brain" / ".kg" / "dreams" / "custom.json"
    result = _runner().invoke(main, ["dream", "--out", str(target), "--passes", "dedup"])
    assert result.exit_code == 0
    files = list(target.parent.glob("df_*.json"))
    assert len(files) == 1
    diff = json.loads(files[0].read_text())
    assert diff["status"] == "proposed"
    assert files[0].stem == diff["id"]
    rows = [
        json.loads(line)
        for line in (root / ".brain" / ".kg" / "contract.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert rows[-1]["cmd"] == "dream"
    assert rows[-1]["args"]["passes"] == ["dedup"]
    assert rows[-1]["args"]["out"] == str(target)


def test_dream_out_outside_dreams_is_path_forbidden(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path)
    monkeypatch.chdir(root)
    result = _runner().invoke(main, ["dream", "--out", str(tmp_path / "outside.json"), "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "path_forbidden"
    assert not (tmp_path / "outside.json").exists()


def test_review_default_is_read_only(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path)
    monkeypatch.chdir(root)
    runner = _runner()
    dreamed = runner.invoke(main, ["dream", "--passes", "orphan", "--json"])
    diff_path = _env(dreamed.output)["data"]["path"]
    result = runner.invoke(main, ["review", diff_path, "--json"])
    assert result.exit_code == 0
    env = _env(result.output)
    assert env["ok"] is True
    assert env["data"]["applied"] == 0
    assert env["data"]["status"] == "proposed"
    assert json.loads(Path(diff_path).read_text())["status"] == "proposed"


def test_review_flags_mutually_exclusive(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path)
    monkeypatch.chdir(root)
    runner = _runner()
    diff_path = _env(runner.invoke(main, ["dream", "--passes", "orphan", "--json"]).output)["data"]["path"]
    result = runner.invoke(main, ["review", diff_path, "--approve", "--reject", "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "limit_error"


def test_review_approve_and_reject_flow(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path)
    monkeypatch.chdir(root)
    runner = _runner()
    diff_path = _env(runner.invoke(main, ["dream", "--passes", "orphan", "--json"]).output)["data"]["path"]
    rejected = runner.invoke(main, ["review", diff_path, "--reject", "--json"])
    assert rejected.exit_code == 0
    assert _env(rejected.output)["data"]["status"] == "rejected"
    assert json.loads(Path(diff_path).read_text())["status"] == "rejected"
    # re-review of a decided diff is idempotent
    again = runner.invoke(main, ["review", diff_path, "--approve", "--json"])
    assert again.exit_code == 0
    assert _env(again.output)["data"]["applied"] == 0
    assert _env(again.output)["data"]["status"] == "rejected"
    assert (root / ".brain" / "notes" / "concept" / "nt_aaaaaaaaaaaaaaaa.md").exists()


def test_review_approve_logs_single_row_with_action(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path)
    monkeypatch.chdir(root)
    runner = _runner()
    diff_path = _env(runner.invoke(main, ["dream", "--passes", "orphan", "--json"]).output)["data"]["path"]
    assert runner.invoke(main, ["review", diff_path, "--approve", "--json"]).exit_code == 0
    rows = [
        json.loads(line)
        for line in (root / ".brain" / ".kg" / "contract.jsonl").read_text().splitlines()
        if line.strip()
    ]
    review_rows = [row for row in rows if row["cmd"] == "review"]
    assert len(review_rows) == 1
    assert review_rows[0]["args"] == {"diff": Path(diff_path).stem, "action": "approve"}
    assert review_rows[0]["ok"] is True


def test_review_path_and_state_errors(tmp_path: Path, monkeypatch) -> None:
    root = _vault_with_note(tmp_path)
    monkeypatch.chdir(root)
    runner = _runner()
    # Inside the vault but outside .kg/dreams: vault discovery succeeds, then path gate rejects.
    outside = root / "outside.json"
    outside.write_text('{"id":"df_0000000000000000","status":"proposed","operations":[]}', encoding="utf-8")
    result = runner.invoke(main, ["review", str(outside), "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "diff_path"
    # hash mismatch maps to diff_state
    bogus = root / ".brain" / ".kg" / "dreams" / "df_0000000000000000.json"
    bogus.parent.mkdir(parents=True, exist_ok=True)
    bogus.write_text('{"id":"df_0000000000000000","status":"proposed","operations":[]}', encoding="utf-8")
    result = runner.invoke(main, ["review", str(bogus), "--json"])
    assert result.exit_code == 1
    assert _env(result.output)["error"]["code"] == "diff_state"


def test_install_plan_only_does_not_mutate(tmp_path: Path) -> None:
    root = tmp_path / "harness"
    result = _runner().invoke(main, ["install", "--root", str(root), "--json"])
    assert result.exit_code == 0
    env = _env(result.output)
    assert env["ok"] is True
    assert len(env["data"]["files"]) == 15
    assert env["data"]["root"] == str(root.resolve())
    assert not (root / ".claude").exists()
    assert not (root / ".cursor").exists()


def test_install_apply_then_uninstall_json(tmp_path: Path) -> None:
    root = tmp_path / "harness"
    runner = _runner()
    applied = runner.invoke(main, ["install", "--root", str(root), "--apply", "--json"])
    assert applied.exit_code == 0
    assert _env(applied.output)["data"] == {"created": 15, "replaced": 0, "skipped": 0}
    assert len(list(root.glob(".claude/commands/kg/*.md"))) == 5
    assert len(list(root.glob(".cursor/rules/*"))) == 5
    assert len(list(root.glob(".pi/skills/*"))) == 5
    removed = runner.invoke(main, ["install", "--root", str(root), "--uninstall", "--json"])
    assert removed.exit_code == 0
    assert _env(removed.output)["data"] == {"removed": 15}
    assert not list(root.glob(".claude/commands/kg/*.md"))
    assert not list(root.glob(".claude/commands/kg"))


def test_install_apply_uninstall_mutually_exclusive(tmp_path: Path) -> None:
    result = _runner().invoke(main, ["install", "--root", str(tmp_path / "h"), "--apply", "--uninstall", "--json"])
    assert result.exit_code == 2
    assert _env(result.output)["error"]["code"] == "limit_error"


def test_install_human_mode_and_plan_json(tmp_path: Path) -> None:
    # The M1.8 _emit helper is JSON-only; without --json the same envelope prints.
    root = tmp_path / "harness"
    plan = _runner().invoke(main, ["install", "--root", str(root)])
    assert plan.exit_code == 0
    env = json.loads(plan.output)
    assert "files" in env
    assert len(env["files"]) == 15
    assert not (root / ".claude").exists()
