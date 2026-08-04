from pathlib import Path

from kg.harness import SKILLS, render_all


def test_render_all_has_three_formats_and_shared_body(tmp_path: Path):
    rendered = render_all(tmp_path)
    assert len(rendered) == 18
    claude = rendered[tmp_path / ".claude/commands/kg/init.md"]
    cursor = rendered[tmp_path / ".cursor/rules/kg-init.mdc"]
    pi = rendered[tmp_path / ".pi/skills/kg-init.md"]
    body = Path("templates/skills/kg-init.md").read_text().strip()
    assert body in claude and body in cursor and body in pi
    assert claude.startswith("# kg:init\n")
    assert cursor.startswith("---\nname: kg:init\ndescription:")
    assert "alwaysApply: false" in cursor
    assert pi.startswith("<!-- unified-brain:managed")
    assert len({claude, cursor, pi}) == 3


def test_rendered_paths_are_exact(tmp_path: Path):
    paths = set(render_all(tmp_path))
    for skill in SKILLS:
        assert tmp_path / f".claude/commands/kg/{skill}.md" in paths
        assert tmp_path / f".cursor/rules/kg-{skill}.mdc" in paths
        assert tmp_path / f".pi/skills/kg-{skill}.md" in paths
