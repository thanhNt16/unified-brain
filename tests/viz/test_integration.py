import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from kg.viz import server


def make_vault(tmp_path):
    brain = tmp_path / ".brain"
    (brain / ".kg").mkdir(parents=True)
    db = brain / ".kg" / "brain.sqlite"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("INSERT INTO meta VALUES ('name','brain')")
    c.execute("INSERT INTO meta VALUES ('root_path',?)", (str(tmp_path),))
    c.execute("INSERT INTO meta VALUES ('indexed_at','2026-01-01')")
    c.execute(
        "CREATE TABLE notes (id TEXT PRIMARY KEY, kind TEXT, type TEXT, title TEXT, body TEXT, tags_json TEXT, frontmatter_json TEXT, status TEXT, supersedes TEXT, source_sha256 TEXT, created TEXT, updated TEXT)"
    )
    c.execute(
        "INSERT INTO notes VALUES ('nt_a','entity','person','Alpha','','[]','{}','draft',NULL,'sha','2026-01-01','2026-01-01')"
    )
    c.execute(
        "CREATE TABLE edges (src TEXT, dst TEXT, relation TEXT, confidence REAL, evidence TEXT, PRIMARY KEY (src, relation, dst))"
    )
    c.execute("INSERT INTO edges VALUES ('nt_a','nt_a','related_to',0.5,'')")
    c.commit()
    c.close()
    wiki = brain / "wiki"
    wiki.mkdir()
    return brain


def start(tmp_path):
    brain = make_vault(tmp_path)
    return server.start("127.0.0.1", 0, brain / "wiki", vault_root=tmp_path, db_path=brain / ".kg" / "brain.sqlite")


def test_empty_vault_200(tmp_path):
    brain = make_vault(tmp_path)
    c = sqlite3.connect(brain / ".kg" / "brain.sqlite")
    c.execute("DELETE FROM notes")
    c.execute("DELETE FROM edges")
    c.commit()
    c.close()
    srv = server.start("127.0.0.1", 0, brain / "wiki", vault_root=tmp_path, db_path=brain / ".kg" / "brain.sqlite")
    try:
        code, _, body = server.fetch(srv, "/api/layout", headers={"X-Auth-Token": srv.token})
        assert code == 200
        j = json.loads(body)
        assert j["nodes"] == [] and j["edges"] == [] and j["total_nodes"] == 0
    finally:
        server.stop(srv)


def test_exact_payload_keys(tmp_path):
    srv = start(tmp_path)
    try:
        code, _, body = server.fetch(srv, "/api/layout", headers={"X-Auth-Token": srv.token})
        assert code == 200
        j = json.loads(body)
        n = j["nodes"][0]
        assert set(n.keys()) == {"id", "kg_id", "x", "y", "z", "label", "name", "size", "color", "in_calls"}
        assert n["z"] == 0.0
        assert n["in_calls"] == 0
        assert n["id"] == n["kg_id"]
        e = j["edges"][0]
        assert set(e.keys()) == {"source", "target", "type"}
        assert e["type"] == "related_to"
        assert set(j.keys()) == {"nodes", "edges", "total_nodes", "truncated_nodes", "truncated_edges"}
    finally:
        server.stop(srv)


def test_unsupported_api_and_rpc_rejected(tmp_path):
    srv = start(tmp_path)
    try:
        code, _, _ = server.fetch(srv, "/api/processes", headers={"X-Auth-Token": srv.token})
        assert code == 404
        body = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_code_snippet","arguments":{}}}'
        code, _, resp = server.fetch(
            srv, "/rpc", headers={"X-Auth-Token": srv.token, "Content-Type": "application/json"}, method="POST", body=body
        )
        assert code == 200
        j = json.loads(resp)
        assert j["error"]["code"] == -32601
    finally:
        server.stop(srv)


def test_layout_deterministic_over_http(tmp_path):
    srv = start(tmp_path)
    try:
        headers = {"X-Auth-Token": srv.token}
        _, _, b1 = server.fetch(srv, "/api/layout", headers=headers)
        _, _, b2 = server.fetch(srv, "/api/layout", headers=headers)
        assert b1 == b2
    finally:
        server.stop(srv)


def test_symlink_under_wiki_rejected(tmp_path):
    srv = start(tmp_path)
    try:
        link = tmp_path / ".brain" / "wiki" / "entities"
        link.mkdir(parents=True, exist_ok=True)
        secret = tmp_path / "secret.md"
        secret.write_text("top secret")
        (link / "leak.md").symlink_to(secret)
        code, _, _ = server.fetch(srv, "/wiki/entities/leak", headers={"X-Auth-Token": srv.token})
        assert code in (403, 404)
    finally:
        server.stop(srv)


def test_layout_clamped_to_2000(tmp_path):
    brain = make_vault(tmp_path)
    srv = server.start(
        "127.0.0.1", 0, brain / "wiki", vault_root=tmp_path, db_path=brain / ".kg" / "brain.sqlite"
    )
    try:
        code, _, _ = server.fetch(srv, "/api/layout?max_nodes=-5", headers={"X-Auth-Token": srv.token})
        assert code == 200
    finally:
        server.stop(srv)
