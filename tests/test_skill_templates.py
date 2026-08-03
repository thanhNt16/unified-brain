from pathlib import Path

SKILLS = ("init", "ingest", "extract", "query", "dream")
REQUIRED = ("Trigger", "When", "Contract", "Procedure")


def test_skill_sources_are_bounded_and_cli_only():
    for skill in SKILLS:
        text = Path("templates/skills", f"kg-{skill}.md").read_text()
        assert len(text.splitlines()) < 80
        assert all(section in text for section in REQUIRED)
        assert "KG_RETRY_MAX" in text
        assert "kg " in text
        assert not any(token in text for token in ("mcp", "python ", "curl ", "pip "))


def test_skill_names_match_product_commands():
    expected = {"init": "kg init", "ingest": "kg ingest", "extract": "kg extract", "query": "kg query", "dream": "kg dream"}
    for skill, command in expected.items():
        text = Path("templates/skills", f"kg-{skill}.md").read_text()
        assert command in text
