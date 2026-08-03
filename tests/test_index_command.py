import json

from click.testing import CliRunner

from kg.cli import main


def test_index_json_success_and_malformed_exit_one(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["init", str(tmp_path), "--json"])
    assert result.exit_code == 0
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / ".brain" / "notes" / "concept" / "bad.md"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("bad", encoding="utf-8")
    result = runner.invoke(main, ["index", "--json"])
    assert result.exit_code == 1
    assert result.output.startswith('{"ok":false')
    result = runner.invoke(main, ["index", "--rebuild", "--json"])
    assert result.exit_code == 1
    assert "index_errors" in result.output


def test_index_ok_when_no_malformed_notes(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    assert runner.invoke(main, ["init", str(tmp_path), "--json"]).exit_code == 0
    monkeypatch.chdir(tmp_path)
    good = tmp_path / ".brain" / "notes" / "concept"
    good.mkdir(parents=True)
    (good / "nt_cccccccccccccccc.md").write_text(
        "---\nid: nt_cccccccccccccccc\nkind: concept\ntitle: Gamma\nstatus: verified\nsource_sha256: "
        + "c" * 64
        + "\ncreated: 2026-01-01\nupdated: 2026-01-01\nrefs: []\ntags: []\nprovenance: []\n---\nBody\n",
        encoding="utf-8",
    )
    result = runner.invoke(main, ["index", "--rebuild", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["ok"] is True
    assert json.loads(result.output)["data"]["notes"] == 1
