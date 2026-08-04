import os
from pathlib import Path

from kg.harness import render_all
from kg.install import InstallError, apply_install, plan_install, uninstall


def test_plan_only_does_not_mutate(tmp_path: Path):
    plan = plan_install(tmp_path)
    assert len(plan.items) == 18
    assert all(item.action == "create" for item in plan.items)
    assert not (tmp_path / ".claude").exists()


def test_apply_writes_all_expected_files_and_uninstall_removes_owned_files(tmp_path: Path):
    result = apply_install(plan_install(tmp_path))
    assert result == {"created": 18, "replaced": 0, "skipped": 0}
    assert len(list(tmp_path.glob(".claude/commands/kg/*.md"))) == 6
    assert len(list(tmp_path.glob(".cursor/rules/*"))) == 6
    assert len(list(tmp_path.glob(".pi/skills/*"))) == 6
    assert uninstall(tmp_path) == {"removed": 18}
    assert not any(tmp_path.glob(".claude/commands/kg/*.md"))
    assert not any(tmp_path.glob(".claude/commands/kg"))


def test_identical_files_skip_and_unowned_files_are_not_overwritten(tmp_path: Path):
    apply_install(plan_install(tmp_path))
    assert all(item.action == "skip" for item in plan_install(tmp_path).items)
    target = tmp_path / ".claude/commands/kg/init.md"
    target.write_text("user content\n")
    try:
        plan_install(tmp_path)
    except InstallError as exc:
        assert "force" in str(exc)
    else:
        raise AssertionError("unowned overwrite was accepted")


def test_force_replaces_owned_file(tmp_path: Path):
    apply_install(plan_install(tmp_path))
    target = tmp_path / ".claude/commands/kg/init.md"
    target.write_text(target.read_text().replace("# kg:init", "# Changed"))
    plan = plan_install(tmp_path, force=True)
    assert next(item for item in plan.items if item.path == target).action == "replace"
    assert apply_install(plan)["replaced"] == 1


def test_partial_failure_restores_every_target(tmp_path: Path, monkeypatch):
    apply_install(plan_install(tmp_path))
    all_rendered = list(tmp_path.glob(".claude/commands/kg/*.md")) + list(tmp_path.glob(".cursor/rules/*")) + list(tmp_path.glob(".pi/skills/*"))
    for path in all_rendered:
        path.write_text(path.read_text() + "\n<!-- local edit -->\n")
    before = {p: p.read_bytes() for p in all_rendered}
    plan = plan_install(tmp_path, force=True)
    real_replace = os.replace
    calls = {"stage": 0}

    def fail_second_stage(source, target):
        if Path(source).name.startswith(".kg-stage-"):
            calls["stage"] += 1
            if calls["stage"] == 2:
                raise OSError("injected replacement failure")
        return real_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_second_stage)
    try:
        apply_install(plan)
    except OSError as exc:
        assert str(exc) == "injected replacement failure"
    else:
        raise AssertionError("failure was swallowed")
    assert {p: p.read_bytes() for p in before} == before
    assert not list(tmp_path.rglob(".kg-stage-*"))
    assert not list(tmp_path.rglob(".kg-backup-*"))


def test_staging_failure_cleans_all_stages(tmp_path: Path, monkeypatch):
    apply_install(plan_install(tmp_path))
    all_rendered = list(tmp_path.glob(".claude/commands/kg/*.md")) + list(tmp_path.glob(".cursor/rules/*")) + list(tmp_path.glob(".pi/skills/*"))
    for path in all_rendered:
        path.write_text(path.read_text() + "\n<!-- local edit -->\n")
    plan = plan_install(tmp_path, force=True)
    real_fsync = os.fsync
    calls = {"count": 0}

    def fail_second_fsync(fd):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("injected staging failure")
        return real_fsync(fd)

    before = {item.path: item.path.read_bytes() for item in plan.items}
    monkeypatch.setattr(os, "fsync", fail_second_fsync)
    try:
        apply_install(plan)
    except OSError as exc:
        assert str(exc) == "injected staging failure"
    else:
        raise AssertionError("failure was swallowed")
    assert {path: path.read_bytes() for path in before} == before
    assert not list(tmp_path.rglob(".kg-stage-*"))
    assert not list(tmp_path.rglob(".kg-backup-*"))


def test_failure_during_backup_restores_all_preexisting_files(tmp_path: Path, monkeypatch):
    # Inject a failure mid-way through the backup phase. Every pre-existing file
    # must survive byte-identically; no .kg-stage-* or .kg-backup-* residue may
    # remain, and restored originals must never be unlinked.
    apply_install(plan_install(tmp_path))
    all_rendered = list(tmp_path.glob(".claude/commands/kg/*.md")) + list(tmp_path.glob(".cursor/rules/*")) + list(tmp_path.glob(".pi/skills/*"))
    for path in all_rendered:
        path.write_text(path.read_text() + "\n<!-- local edit -->\n")
    before = {p: p.read_bytes() for p in all_rendered}
    plan = plan_install(tmp_path, force=True)
    real_replace = os.replace
    calls = {"backup": 0}

    def fail_second_backup(source, target):
        if Path(source) in all_rendered and Path(target).name.startswith(".kg-backup-"):
            calls["backup"] += 1
            if calls["backup"] == 2:
                raise OSError("injected backup failure")
        return real_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_second_backup)
    try:
        apply_install(plan)
    except OSError as exc:
        assert str(exc) == "injected backup failure"
    else:
        raise AssertionError("failure was swallowed")
    assert {p: p.read_bytes() for p in before} == before
    assert not list(tmp_path.rglob(".kg-stage-*"))
    assert not list(tmp_path.rglob(".kg-backup-*"))


def test_uninstall_failure_restores_removed_files(tmp_path: Path, monkeypatch):
    apply_install(plan_install(tmp_path))
    rendered = render_all(tmp_path)
    before = {path: path.read_bytes() for path in rendered}
    real_replace = os.replace
    calls = {"count": 0}

    def fail_second_replace(source, target):
        if Path(source) in rendered:
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("injected uninstall failure")
        return real_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_second_replace)
    try:
        uninstall(tmp_path)
    except OSError as exc:
        assert str(exc) == "injected uninstall failure"
    else:
        raise AssertionError("failure was swallowed")
    assert {path: path.read_bytes() for path in before} == before
    assert not list(tmp_path.rglob(".kg-stage-*"))
    assert not list(tmp_path.rglob(".kg-backup-*"))
