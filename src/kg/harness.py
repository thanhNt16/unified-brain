from pathlib import Path

SKILLS = ("init", "ingest", "extract", "query", "dream")
HARNESS_DIRS = {"claude": ".claude/skills", "cursor": ".cursor/rules", "pi": ".pi/skills"}
DESCRIPTIONS = {
    "init": "Initialize a local knowledge graph vault",
    "ingest": "Capture immutable source files",
    "extract": "Validate and apply approved proposals",
    "query": "Retrieve explainable graph context",
    "dream": "Generate bounded maintenance suggestions",
}
TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates/skills"


def _marker(skill: str, harness: str) -> str:
    return f"<!-- unified-brain:managed skill=kg:{skill} harness={harness} template=v1 -->"


def render_skill(skill: str, harness: str, body: str) -> str:
    if skill not in SKILLS or harness not in HARNESS_DIRS:
        raise ValueError("unknown skill or harness")
    body = body.rstrip() + "\n"
    marker = _marker(skill, harness)
    if harness == "claude":
        return f"---\nname: kg:{skill}\ndescription: {DESCRIPTIONS[skill]}\n---\n{marker}\n\n{body}"
    if harness == "cursor":
        return f"---\nname: kg:{skill}\ndescription: {DESCRIPTIONS[skill]}\nglobs: **\nalwaysApply: false\n---\n{marker}\n\n{body}"
    return f"{marker}\n# kg:{skill}\n\n{body}"


def render_all(root: Path, template_dir: Path | None = None) -> dict[Path, str]:
    root = Path(root)
    source = template_dir or TEMPLATE_DIR
    rendered: dict[Path, str] = {}
    for skill in SKILLS:
        body = (source / f"kg-{skill}.md").read_text(encoding="utf-8")
        rendered[root / HARNESS_DIRS["claude"] / f"kg-{skill}.md"] = render_skill(skill, "claude", body)
        rendered[root / HARNESS_DIRS["cursor"] / f"kg-{skill}.mdc"] = render_skill(skill, "cursor", body)
        rendered[root / HARNESS_DIRS["pi"] / f"kg-{skill}.md"] = render_skill(skill, "pi", body)
    return rendered
