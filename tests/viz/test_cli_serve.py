import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_cli_serve_starts_and_serves_layout():
    tmp = Path(tempfile.mkdtemp())
    brain = tmp / ".brain"
    (brain / ".kg").mkdir(parents=True)
    c = sqlite3.connect(brain / ".kg" / "brain.sqlite")
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
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "kg.viz.cli", "serve", "--port", "0", "--wiki", str(brain / "wiki"), "--no-open"],
        cwd=str(tmp),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        token = None
        serving_url = None
        for _ in range(100):
            line = proc.stdout.readline()
            if not line:
                break
            if "token=" in line:
                token = line.strip().split("token=")[1]
            if "serving on " in line:
                serving_url = line.strip().split("serving on ")[1]
            if token and serving_url:
                break
        assert token, "no token printed"
        assert serving_url, "no serving line"
        req = urllib.request.Request(serving_url + "/api/layout", headers={"X-Auth-Token": token})
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
            assert payload["total_nodes"] == 1
            assert payload["nodes"][0]["in_calls"] == 0
    finally:
        proc.terminate()
        proc.wait(timeout=10)
