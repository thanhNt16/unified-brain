from pathlib import Path

SKILLS = ("init", "ingest", "extract", "query", "dream")
HARNESS_DIRS = {"claude": ".claude/commands", "cursor": ".cursor/rules", "pi": ".pi/skills"}
DESCRIPTIONS = {
    "init": "Initialize a local knowledge graph vault",
    "ingest": "Capture immutable source files",
    "extract": "Validate and apply approved proposals",
    "query": "Retrieve explainable graph context",
    "dream": "Generate bounded maintenance suggestions",
}


def _template_dir() -> Path:
    # Wheel layout: templates/skills is a top-level data dir next to kg/.
    # Source layout: templates/skills lives two parents above kg/harness.py.
    here = Path(__file__).resolve().parent
    wheel_layout = here.parent / "templates" / "skills"
    if wheel_layout.is_dir():
        return wheel_layout
    return here.parents[1] / "templates" / "skills"


TEMPLATE_DIR = _template_dir()


def _marker(skill: str, harness: str) -> str:
    return f"<!-- unified-brain:managed skill=kg:{skill} harness={harness} template=v1 -->"


def render_skill(skill: str, harness: str, body: str) -> str:
    if skill not in SKILLS or harness not in HARNESS_DIRS:
        raise ValueError("unknown skill or harness")
    body = body.rstrip() + "\n"
    marker = _marker(skill, harness)
    if harness == "claude":
        return f"# kg:{skill}\n\n{marker}\n\n{body}"
    if harness == "cursor":
        return f"---\nname: kg:{skill}\ndescription: {DESCRIPTIONS[skill]}\nglobs: **\nalwaysApply: false\n---\n{marker}\n\n{body}"
    return f"{marker}\n# kg:{skill}\n\n{body}"


def render_all(root: Path, template_dir: Path | None = None) -> dict[Path, str]:
    root = Path(root)
    source = template_dir or TEMPLATE_DIR
    rendered: dict[Path, str] = {}
    for skill in SKILLS:
        body = (source / f"kg-{skill}.md").read_text(encoding="utf-8")
        rendered[root / HARNESS_DIRS["claude"] / "kg" / f"{skill}.md"] = render_skill(skill, "claude", body)
        rendered[root / HARNESS_DIRS["cursor"] / f"kg-{skill}.mdc"] = render_skill(skill, "cursor", body)
        rendered[root / HARNESS_DIRS["pi"] / f"kg-{skill}.md"] = render_skill(skill, "pi", body)
    return rendered
