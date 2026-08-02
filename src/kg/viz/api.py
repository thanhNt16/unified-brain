"""Pure read-only adapter between the kg SQLite projection and CBM UI APIs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import layout3d

MAX_LAYOUT_BYTES = 4 * 1024 * 1024
MAX_RPC_BYTES = 64 * 1024


def max_layout_bytes() -> int:
    return MAX_LAYOUT_BYTES


def max_rpc_bytes() -> int:
    return MAX_RPC_BYTES


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _load_nodes(conn: sqlite3.Connection) -> list[dict[str, str]]:
    rows = conn.execute(
        "SELECT id, kind, type, title FROM notes WHERE status NOT IN ('tombstone', 'superseded') ORDER BY id"
    ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "kg_id": str(row["id"]),
            "label": str(row["kind"]),
            "name": str(row["title"]),
            "path": str(row["type"] or ""),
        }
        for row in rows
    ]


def _load_edges(conn: sqlite3.Connection) -> list[dict[str, str]]:
    rows = conn.execute("SELECT src, dst, relation FROM edges ORDER BY src, dst, relation").fetchall()
    return [{"source": str(row["src"]), "target": str(row["dst"]), "type": str(row["relation"])} for row in rows]


def load_nodes(db_path: Path) -> list[dict[str, str]]:
    conn = _connect(db_path)
    try:
        return _load_nodes(conn)
    finally:
        conn.close()


def load_edges(db_path: Path) -> list[dict[str, str]]:
    conn = _connect(db_path)
    try:
        return _load_edges(conn)
    finally:
        conn.close()


def handle_layout(db_path: Path, max_nodes: int) -> layout3d.LayoutResult:
    # One read-only connection/snapshot so nodes and edges cannot diverge mid-read.
    conn = _connect(db_path)
    try:
        nodes = _load_nodes(conn)
        edges = _load_edges(conn)
    finally:
        conn.close()
    idset = {str(n["id"]) for n in nodes}
    edges = [e for e in edges if str(e["source"]) in idset and str(e["target"]) in idset]
    return layout3d.compute_layout(nodes, edges, max_nodes)


def _meta(db_path: Path, key: str, default: str = "") -> str:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else default
    finally:
        conn.close()


def handle_project(db_path: Path) -> dict[str, str]:
    return {"name": _meta(db_path, "name", "brain"), "root_path": _meta(db_path, "root_path"), "indexed_at": _meta(db_path, "indexed_at")}


def handle_schema(db_path: Path) -> dict:
    conn = _connect(db_path)
    try:
        labels = [dict(row) for row in conn.execute("SELECT kind AS label, COUNT(*) AS count FROM notes WHERE status NOT IN ('tombstone', 'superseded') GROUP BY kind ORDER BY label")]
        edge_types = [dict(row) for row in conn.execute("SELECT relation AS type, COUNT(*) AS count FROM edges GROUP BY relation ORDER BY type")]
        total_nodes = conn.execute("SELECT COUNT(*) FROM notes WHERE status NOT IN ('tombstone', 'superseded')").fetchone()[0]
        total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        return {"node_labels": labels, "edge_types": edge_types, "total_nodes": total_nodes, "total_edges": total_edges}
    finally:
        conn.close()


def handle_repo_info(vault_root: Path) -> dict[str, str]:
    return {"root_path": str(vault_root), "branch": "", "remote_url": "", "web_base": "", "blob_base": ""}


def handle_ui_config() -> dict[str, str]:
    return {"lang": "en", "upstream_issues_url": ""}


def list_projects(db_path: Path) -> list[dict[str, str]]:
    return [handle_project(db_path)]


def get_graph_schema(db_path: Path) -> dict:
    return handle_schema(db_path)


def handle_rpc(body: bytes, db_path: Path, vault_root: Path) -> dict:
    if len(body) > MAX_RPC_BYTES:
        return {"jsonrpc": "2.0", "error": {"code": -32600, "message": "request too large"}, "id": None}
    try:
        request = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return {"jsonrpc": "2.0", "error": {"code": -32700, "message": "parse error"}, "id": None}
    if not isinstance(request, dict):
        return {"jsonrpc": "2.0", "error": {"code": -32600, "message": "invalid request"}, "id": None}
    request_id = request.get("id")
    params = request.get("params")
    name = params.get("name") if isinstance(params, dict) else None
    if request.get("method") != "tools/call" or name not in ("list_projects", "get_graph_schema"):
        return {"jsonrpc": "2.0", "error": {"code": -32601, "message": "UI RPC method is not allowed"}, "id": request_id}
    data = list_projects(db_path) if name == "list_projects" else get_graph_schema(db_path)
    return {"jsonrpc": "2.0", "result": {"content": [{"type": "text", "text": json.dumps(data, allow_nan=False)}]}, "id": request_id}


def handle_wiki(vault_root: Path, slug: str) -> str:
    path = vault_root / ".brain" / "wiki" / f"{slug}.md"
    if not path.is_file():
        raise KeyError(slug)
    return path.read_text(encoding="utf-8")
