"""Authenticated loopback HTTP server for the bundled graph UI."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

from . import api
from .vendor import ASSETS_DIR

CSP = "default-src 'self'; script-src 'self'; style-src 'self'"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def allowed_host(host: str, port: int) -> bool:
    host = host.strip().lower()
    return host in {"localhost", "127.0.0.1", f"localhost:{port}", f"127.0.0.1:{port}"}


def allowed_origin(origin: str, host: str, port: int) -> bool:
    if not origin:
        return True
    parsed = urlparse(origin)
    host_name = host.rsplit(":", 1)[0].lower() if ":" in host else host.lower()
    return (
        parsed.scheme in ("http", "https")
        and parsed.hostname in ("localhost", "127.0.0.1")
        and parsed.hostname == host_name
        and parsed.port in (None, port)
    )


def safe_path(root: Path, rel: str) -> Path | None:
    if not rel or "\\" in rel or any(ord(c) < 32 for c in rel):
        return None
    try:
        parsed = PurePosixPath(rel)
    except ValueError:
        return None
    if parsed.is_absolute() or ".." in parsed.parts or "//" in rel or rel.startswith("/"):
        return None
    root_resolved = root.resolve()
    candidate = (root_resolved / rel).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return None
    current = root_resolved
    for part in parsed.parts:
        current = current / part
        if current.is_symlink():
            return None
    return candidate


def etag_for(payload: bytes) -> str:
    return f'"{hashlib.sha256(payload).hexdigest()}"'


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, allow_nan=False, separators=(",", ":")).encode()


def build_app(token: str, vault_root: Path, db_path: Path, port: int, wiki_dir: Path | None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(30.0)

        def log_message(self, fmt: str, *args: object) -> None:
            return

        def _send(self, code: int, payload: bytes, content_type: str = "application/json", **extra: str) -> None:
            headers = {
                "Content-Type": content_type,
                "Content-Length": str(len(payload)),
                "X-Content-Type-Options": "nosniff",
                **extra,
            }
            if code >= 400:
                headers["Cache-Control"] = "no-store"
            self.send_response(code)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload)

        def _error(self, code: int, message: str, challenge: bool = False) -> None:
            extra = {"X-Auth-Token": token} if challenge else {}
            self._send(code, _json_bytes({"error": message}), **extra)

        def _authorized(self) -> bool:
            if not allowed_host(self.headers.get("Host", ""), port):
                self._error(403, "forbidden host")
                return False
            try:
                origin_allowed = allowed_origin(self.headers.get("Origin", ""), self.headers.get("Host", ""), port)
            except ValueError:
                origin_allowed = False
            if not origin_allowed:
                self._error(403, "forbidden origin")
                return False
            supplied = self.headers.get("X-Auth-Token", "")
            if not supplied:
                self._error(401, "auth required", challenge=True)
                return False
            if not constant_time_eq(supplied, token):
                self._error(403, "forbidden")
                return False
            return True

        def do_GET(self) -> None:
            if not self._authorized():
                return
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            try:
                if path == "/api/layout":
                    params = parse_qs(parsed.query)
                    try:
                        max_nodes = max(1, min(int(params.get("max_nodes", [2000])[0]), 2000))
                    except ValueError:
                        max_nodes = 2000
                    payload = _json_bytes(api.handle_layout(db_path, max_nodes))
                    if len(payload) > api.max_layout_bytes():
                        self._error(413, "payload too large")
                        return
                    etag = etag_for(payload)
                    if self.headers.get("If-None-Match") == etag:
                        self.send_response(304)
                        self.send_header("ETag", etag)
                        self.send_header("X-Content-Type-Options", "nosniff")
                        self.end_headers()
                        return
                    self._send(200, payload, **{"ETag": etag, "Content-Security-Policy": CSP})
                    return
                handlers = {
                    "/api/project": api.handle_project,
                    "/api/schema": api.handle_schema,
                    "/api/ui-config": lambda _: api.handle_ui_config(),
                    "/api/repo-info": lambda _: api.handle_repo_info(vault_root),
                }
                if path in handlers:
                    self._send(200, _json_bytes(handlers[path](db_path)))
                    return
                if path.startswith("/wiki/"):
                    if wiki_dir is None:
                        self._error(404, "not found")
                        return
                    slug = path[len("/wiki/"):]
                    safe = safe_path(wiki_dir, f"{slug}.md")
                    if safe is None:
                        self._error(403, "forbidden")
                        return
                    try:
                        body = safe.read_bytes()
                    except OSError:
                        self._error(404, "not found")
                        return
                    self._send(200, body, content_type="text/markdown")
                    return
                target = safe_path(ASSETS_DIR, path.lstrip("/")) if path != "/" else ASSETS_DIR / "index.html"
                if target is None or not target.is_file():
                    self._error(404, "not found")
                    return
                try:
                    payload = target.read_bytes()
                except OSError:
                    self._error(404, "not found")
                    return
                suffix_types = {".html": "text/html", ".js": "application/javascript", ".css": "text/css", ".svg": "image/svg+xml"}
                self._send(200, payload, content_type=suffix_types.get(target.suffix, "application/octet-stream"), **{"Content-Security-Policy": CSP})
            except Exception:  # noqa: BLE001 - handler boundary; never leak tracebacks
                self._error(500, "internal error")

        def do_POST(self) -> None:
            if not self._authorized():
                return
            if urlparse(self.path).path != "/rpc":
                self._error(404, "not found")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._error(400, "invalid content length")
                return
            if length > api.max_rpc_bytes():
                self._error(413, "payload too large")
                return
            body = self.rfile.read(length)
            self._send(200, _json_bytes(api.handle_rpc(body, db_path, vault_root)))

    return Handler


class Server:
    def __init__(self, httpd: ThreadingHTTPServer, token: str, port: int) -> None:
        self.httpd = httpd
        self.token = token
        self.port = port
        self.thread: threading.Thread | None = None
        self.timeout = 30


def start(host: str, port: int, wiki_dir: Path | None = None, *, vault_root: Path, db_path: Path) -> Server:
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("loopback only")
    token = new_token()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
    httpd.timeout = 30
    actual_port = int(httpd.server_address[1])
    httpd.RequestHandlerClass = build_app(token, vault_root, db_path, actual_port, wiki_dir)
    srv = Server(httpd, token, actual_port)
    srv.thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    srv.thread.start()
    print(f"kg viz: token={token}", flush=True)
    return srv


def stop(srv: Server) -> None:
    srv.httpd.shutdown()
    srv.httpd.server_close()
    if srv.thread:
        srv.thread.join(timeout=2)


def url(srv: Server, path: str = "") -> str:
    return f"http://127.0.0.1:{srv.port}{path}"


def fetch(srv: Server, path: str, headers: dict | None = None, method: str = "GET", body: bytes | None = None) -> tuple[int, dict, bytes]:
    req_headers = dict(headers or {})
    req_headers.setdefault("Host", f"127.0.0.1:{srv.port}")
    request = Request(url(srv, path), data=body, headers=req_headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, dict(response.headers), response.read()
    except HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def serve(vault_root: Path, db_path: Path, *, host: str = "127.0.0.1", port: int = 9749, wiki: Path | None = None, open_browser: bool = True) -> None:
    srv = start(host, port, wiki, vault_root=vault_root, db_path=db_path)
    if open_browser:
        webbrowser.open(url(srv))
    print(f"serving on {url(srv)}", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        stop(srv)
