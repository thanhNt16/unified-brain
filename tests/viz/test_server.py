import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from kg.viz import server


def make_vault():
    tmp = Path(tempfile.mkdtemp())
    brain = tmp / ".brain"
    (brain / ".kg").mkdir(parents=True)
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
        "CREATE TABLE edges (src TEXT, dst TEXT, relation TEXT, confidence REAL, evidence TEXT, PRIMARY KEY (src, relation, dst))"
    )
    c.execute("INSERT INTO edges VALUES ('nt_a','nt_a','related_to',0.5,'')")
    c.commit()
    c.close()
    wiki = brain / "wiki" / "entities"
    wiki.mkdir(parents=True)
    (wiki / "alpha.md").write_text("# Alpha")
    return tmp, db


def start_server(vault_root, db_path):
    srv = server.start("127.0.0.1", 0, vault_root / ".brain" / "wiki", vault_root=vault_root, db_path=db_path)
    return srv, srv.token


def auth(token):
    return {"X-Auth-Token": token}


def test_missing_token_401():
    vault_root, db = make_vault()
    srv, _ = start_server(vault_root, db)
    try:
        code, _, _ = server.fetch(srv, "/api/layout")
        assert code == 401
    finally:
        server.stop(srv)


def test_wrong_token_403():
    vault_root, db = make_vault()
    srv, _ = start_server(vault_root, db)
    try:
        code, _, _ = server.fetch(srv, "/api/layout", headers={"X-Auth-Token": "wrong"})
        assert code == 403
    finally:
        server.stop(srv)


def test_valid_token_layout_200():
    vault_root, db = make_vault()
    srv, tok = start_server(vault_root, db)
    try:
        code, headers, body = server.fetch(srv, "/api/layout", headers=auth(tok))
        assert code == 200
        assert headers.get("Content-Type", "").startswith("application/json")
        j = json.loads(body)
        assert j["total_nodes"] == 1
        assert j["nodes"][0]["in_calls"] == 0
        assert "ETag" in headers
    finally:
        server.stop(srv)


def test_layout_etag_304():
    vault_root, db = make_vault()
    srv, tok = start_server(vault_root, db)
    try:
        code, headers, _ = server.fetch(srv, "/api/layout", headers=auth(tok))
        assert code == 200
        etag = headers["ETag"]
        code2, _, _ = server.fetch(srv, "/api/layout", headers={**auth(tok), "If-None-Match": etag})
        assert code2 == 304
    finally:
        server.stop(srv)


def test_bad_host_403():
    vault_root, db = make_vault()
    srv, tok = start_server(vault_root, db)
    try:
        code, _, _ = server.fetch(srv, "/api/layout", headers={**auth(tok), "Host": "evil.com"})
        assert code == 403
    finally:
        server.stop(srv)


def test_bad_origin_403():
    vault_root, db = make_vault()
    srv, tok = start_server(vault_root, db)
    try:
        code, _, _ = server.fetch(srv, "/api/layout", headers={**auth(tok), "Origin": "http://evil.com"})
        assert code == 403
    finally:
        server.stop(srv)


def test_layout_csp_and_nosniff():
    vault_root, db = make_vault()
    srv, tok = start_server(vault_root, db)
    try:
        _, headers, _ = server.fetch(srv, "/api/layout", headers=auth(tok))
        csp = headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "style-src 'self'" in csp
        assert headers.get("X-Content-Type-Options") == "nosniff"
    finally:
        server.stop(srv)


def test_layout_no_store_on_errors():
    vault_root, db = make_vault()
    srv, _ = start_server(vault_root, db)
    try:
        _, headers, _ = server.fetch(srv, "/api/layout", headers={"X-Auth-Token": "wrong"})
        assert headers.get("Cache-Control") == "no-store"
        assert headers.get("X-Content-Type-Options") == "nosniff"
    finally:
        server.stop(srv)


def test_layout_max_nodes_range():
    vault_root, db = make_vault()
    srv, tok = start_server(vault_root, db)
    try:
        code, _, _ = server.fetch(srv, "/api/layout?max_nodes=9999", headers=auth(tok))
        assert code == 200
    finally:
        server.stop(srv)


def test_unsupported_api_404():
    vault_root, db = make_vault()
    srv, tok = start_server(vault_root, db)
    try:
        code, _, _ = server.fetch(srv, "/api/index", headers=auth(tok))
        assert code == 404
    finally:
        server.stop(srv)


def test_rpc_ok():
    vault_root, db = make_vault()
    srv, tok = start_server(vault_root, db)
    try:
        body = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_projects","arguments":{}}}'
        code, _, resp = server.fetch(
            srv, "/rpc", headers={**auth(tok), "Content-Type": "application/json"}, method="POST", body=body
        )
        assert code == 200
        assert b"jsonrpc" in resp
    finally:
        server.stop(srv)


def test_rpc_payload_too_large():
    vault_root, db = make_vault()
    srv, tok = start_server(vault_root, db)
    try:
        big = b'{"x":"' + b"a" * 70000 + b'"}'
        code, _, _ = server.fetch(
            srv, "/rpc", headers={**auth(tok), "Content-Type": "application/json"}, method="POST", body=big
        )
        assert code == 413
    finally:
        server.stop(srv)


def test_wiki_served_read_only():
    vault_root, db = make_vault()
    srv, tok = start_server(vault_root, db)
    try:
        code, _, body = server.fetch(srv, "/wiki/entities/alpha", headers=auth(tok))
        assert code == 200
        assert body == b"# Alpha"
    finally:
        server.stop(srv)


def test_path_traversal_rejected():
    vault_root, db = make_vault()
    srv, tok = start_server(vault_root, db)
    try:
        for p in ("/wiki/../../etc/passwd", "/wiki/..%2f..%2fetc/passwd", "/wiki/entities/..%2f..%2fsecret"):
            code, _, _ = server.fetch(srv, p, headers=auth(tok))
            assert code == 403, p
    finally:
        server.stop(srv)


def test_static_spa_fallback_404():
    vault_root, db = make_vault()
    srv, tok = start_server(vault_root, db)
    try:
        code, _, _ = server.fetch(srv, "/some/deep/route", headers=auth(tok))
        assert code == 404
    finally:
        server.stop(srv)


def test_token_unique_per_process():
    vault_root, db = make_vault()
    srv1, tok1 = start_server(vault_root, db)
    srv2, tok2 = start_server(vault_root, db)
    try:
        assert tok1 != tok2
    finally:
        server.stop(srv1)
        server.stop(srv2)


def test_token_never_in_headers():
    vault_root, db = make_vault()
    srv, tok = start_server(vault_root, db)
    try:
        _, headers, _ = server.fetch(srv, "/api/project", headers=auth(tok))
        assert "token" not in str(headers).lower()
    finally:
        server.stop(srv)
