from pathlib import Path

from kg.storage import Vault
from kg.wiki import generate


def test_wiki_is_generated_from_canonical_notes(tmp_path: Path) -> None:
    vault = Vault(tmp_path)
    path = tmp_path / ".brain" / "notes" / "concept"
    path.mkdir(parents=True)
    (path / "nt_aaaaaaaaaaaaaaaa.md").write_text(
        "---\nid: nt_aaaaaaaaaaaaaaaa\nkind: concept\ntitle: Alpha\nstatus: verified\nsource_sha256: "
        + "a" * 64
        + "\ncreated: 2026-01-01\nupdated: 2026-01-01\nrefs: []\ntags: []\nprovenance: []\n---\nBody\n",
        encoding="utf-8",
    )
    result = generate(vault)
    assert result["notes"] == 1
    index = (tmp_path / ".brain" / "wiki" / "index.md").read_text()
    assert "Alpha" in index and "nt_aaaaaaaaaaaaaaaa" in index
    assert (tmp_path / ".brain" / "wiki" / "concepts" / "nt_aaaaaaaaaaaaaaaa.md").exists()
    before = index
    generate(vault)
    assert (tmp_path / ".brain" / "wiki" / "index.md").read_text() == before
