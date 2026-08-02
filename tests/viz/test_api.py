import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from kg.viz import api


def make_vault():
    tmp = Path(tempfile.mkdtemp())
    brain = tmp / ".brain"
    brain.mkdir()
    (brain / ".kg").mkdir()
    db = brain / ".kg" / "brain.sqlite"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("INSERT INTO meta VALUES ('name','brain')")
    c.execute("INSERT INTO meta VALUES ('root_path',?)", (str(tmp),))
    c.execute("INSERT INTO meta VALUES ('indexed_at','2026-01-01')")
    c.execute(
        "CREATE TABLE notes (id TEXT PRIMARY KEY, kind TEXT, type TEXT, title TEXT, body TEXT, tags_json TEXT, frontmatter_json TEXT, status TEXT, supersedes TEXT, source_sha256 TEXT, created TEXT, updated TEXT)"
    )
    c.execute(
        "INSERT INTO notes VALUES ('nt_a','entity','person','Alpha','','[]','{}','draft',NULL,'sha','2026-01-01','2026-01-01')"
    )
    c.execute(
        "INSERT INTO notes VALUES ('nt_b','concept','idea','Beta','','[]','{}','draft',NULL,'sha','2026-01-01','2026-01-01')"
    )
    c.execute(
        "CREATE TABLE edges (src TEXT, dst TEXT, relation TEXT, confidence REAL, evidence TEXT, PRIMARY KEY (src, relation, dst))"
    )
    c.execute("INSERT INTO edges VALUES ('nt_a','nt_b','depends_on',0.9,'e')")
    c.commit()
    c.close()
    return tmp, db


def test_load_nodes():
    _, db = make_vault()
    ns = api.load_nodes(db)
    assert len(ns) == 2
    by = {n["kg_id"]: n for n in ns}
    assert by["nt_a"]["name"] == "Alpha"
    assert by["nt_a"]["label"] == "entity"
    for n in ns:
        assert n["id"] == n["kg_id"]


def test_load_edges():
    _, db = make_vault()
    assert api.load_edges(db) == [{"source": "nt_a", "target": "nt_b", "type": "depends_on"}]


def test_handle_layout_empty_vault():
    _, db = make_vault()
    r = api.handle_layout(db, 2000)
    assert r["total_nodes"] == 2
    assert len(r["nodes"]) == 2
    assert len(r["edges"]) == 1
    assert r["truncated_nodes"] == 0
    assert r["truncated_edges"] == 0
    for n in r["nodes"]:
        assert set(n.keys()) == {"id", "kg_id", "x", "y", "z", "label", "name", "size", "color", "in_calls"}


def test_handle_layout_max_nodes_caps():
    _, db = make_vault()
    r = api.handle_layout(db, 1)
    assert len(r["nodes"]) == 1
    assert r["truncated_nodes"] == 1
    assert r["total_nodes"] == 2
    assert r["edges"] == []


def test_handle_layout_drops_dangling_edges():
    _, db = make_vault()
    c = sqlite3.connect(db)
    c.execute("INSERT INTO edges VALUES ('nt_a','nt_z','mentions',0.5,'e')")
    c.commit()
    c.close()
    r = api.handle_layout(db, 2000)
    ids = {n["id"] for n in r["nodes"]}
    assert "nt_z" not in ids
    assert r["edges"] == [{"source": "nt_a", "target": "nt_b", "type": "depends_on"}]
    assert all(e["source"] in ids and e["target"] in ids for e in r["edges"])
    assert r["truncated_edges"] == 0


def test_handle_layout_ignores_tombstoned():
    _, db = make_vault()
    c = sqlite3.connect(db)
    c.execute("UPDATE notes SET status='tombstone' WHERE id='nt_b'")
    c.commit()
    c.close()
    r = api.handle_layout(db, 2000)
    assert [n["kg_id"] for n in r["nodes"]] == ["nt_a"]
    assert r["edges"] == []


def test_handle_project():
    _, db = make_vault()
    r = api.handle_project(db)
    assert r["name"]
    assert r["root_path"]
    assert r["indexed_at"]


def test_handle_schema():
    _, db = make_vault()
    r = api.handle_schema(db)
    assert r["total_nodes"] == 2
    assert r["total_edges"] == 1
    assert {x["label"] for x in r["node_labels"]} == {"entity", "concept"}
    assert {x["type"] for x in r["edge_types"]} == {"depends_on"}


def test_handle_repo_info():
    tmp, _ = make_vault()
    r = api.handle_repo_info(tmp)
    assert r["root_path"] == str(tmp)
    assert isinstance(r["branch"], str)


def test_handle_ui_config():
    r = api.handle_ui_config()
    assert r["lang"] == "en"
    assert r["upstream_issues_url"] == ""


def test_rpc_list_projects():
    tmp, db = make_vault()
    body = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_projects","arguments":{}}}'
    r = api.handle_rpc(body, db, tmp)
    assert r["jsonrpc"] == "2.0"
    text = r["result"]["content"][0]["text"]
    assert "list_projects" in text or "name" in text


def test_rpc_unsupported_tool():
    tmp, db = make_vault()
    body = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_code_snippet","arguments":{}}}'
    r = api.handle_rpc(body, db, tmp)
    assert r["error"]["code"] == -32601


def test_rpc_bad_json():
    tmp, db = make_vault()
    r = api.handle_rpc(b"not json", db, tmp)
    assert r["error"]["code"] == -32700


def test_rpc_body_size_limits():
    assert api.max_rpc_bytes() == 65536
    assert api.max_layout_bytes() == 4194304


def test_wiki_slug_returns_markdown():
    tmp, _ = make_vault()
    (tmp / ".brain" / "wiki").mkdir()
    (tmp / ".brain" / "wiki" / "entities").mkdir()
    (tmp / ".brain" / "wiki" / "entities" / "alpha.md").write_text("# Alpha\n")
    assert api.handle_wiki(tmp, "entities/alpha") == "# Alpha\n"


def test_wiki_missing_slug_raises():
    tmp, _ = make_vault()
    try:
        api.handle_wiki(tmp, "entities/nope")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass


def test_rpc_returns_valid_json():
    tmp, db = make_vault()
    body = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_graph_schema","arguments":{}}}'
    r = api.handle_rpc(body, db, tmp)
    json.loads(r["result"]["content"][0]["text"])
