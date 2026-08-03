"""Render bench/report.json + release-gate status to an accessible GitHub Pages site.

No chart: stat tiles + a results table. Status colors are reserved
(good / warning / critical) and always carry an icon + text label, never
color alone. Light and dark themes via prefers-color-scheme. Self-contained
HTML (no external CSS/JS) so the page is offline and CDN-free.
"""

from __future__ import annotations

import html
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "bench" / "report.json"
OUT = ROOT / "pages" / "index.html"

_STATUS_META = {
    "MEASURED": ("good", "✓", "MEASURED"),
    "FAILED": ("critical", "✗", "FAILED"),
    "NOT_MEASURED": ("warning", "—", "NOT MEASURED"),
}
_UNKNOWN_META = ("muted", "?", "UNKNOWN")


def _status_meta(status: str) -> tuple[str, str, str]:
    return _STATUS_META.get(status, _UNKNOWN_META)


def _fmt(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:g}"
    return html.escape(str(value))


def _gate_error(cells: list[dict[str, object]]) -> str | None:
    try:
        from bench.gate import REQUIRED_HARNESSES, _required_tasks, validate_release_cells

        validate_release_cells(cells, REQUIRED_HARNESSES, _required_tasks())
        return None
    except ValueError as exc:
        return str(exc)


def render(cells: list[dict[str, object]]) -> str:
    total = len(cells)
    by_status: dict[str, int] = {}
    by_harness: dict[str, dict[str, int]] = {}
    for cell in cells:
        status = str(cell.get("status", "UNKNOWN"))
        by_status[status] = by_status.get(status, 0) + 1
        harness = str(cell.get("harness", "?"))
        bucket = by_harness.setdefault(harness, {"MEASURED": 0, "FAILED": 0, "NOT_MEASURED": 0, "pass": 0})
        if status in bucket:
            bucket[status] += 1
        if cell.get("pass") is True:
            bucket["pass"] += 1
    gate_error = _gate_error(cells)
    gate_ok = gate_error is None
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    stat_tiles: list[str] = []
    for label, kind, value in (
        ("Required cells", "muted", total),
        ("Measured", "good", by_status.get("MEASURED", 0)),
        ("Failed", "critical", by_status.get("FAILED", 0)),
        ("Not measured", "warning", by_status.get("NOT_MEASURED", 0)),
        ("Release gate", "good" if gate_ok else "critical", "PASS" if gate_ok else "FAIL"),
    ):
        stat_tiles.append(
            f'<div class="tile tile-{kind}"><div class="tile-value">{html.escape(str(value))}</div>'
            f'<div class="tile-label">{html.escape(label)}</div></div>'
        )

    harness_rows: list[str] = []
    for harness in sorted(by_harness):
        b = by_harness[harness]
        harness_rows.append(
            "<tr>"
            f"<td>{html.escape(harness)}</td>"
            f'<td class="num">{b["MEASURED"]}</td>'
            f'<td class="num">{b["FAILED"]}</td>'
            f'<td class="num">{b["NOT_MEASURED"]}</td>'
            f'<td class="num">{b["pass"]}</td>'
            "</tr>"
        )

    result_rows: list[str] = []
    for cell in sorted(cells, key=lambda c: (str(c.get("harness")), str(c.get("task")))):
        status = str(cell.get("status", "UNKNOWN"))
        _, icon, label = _status_meta(status)
        pass_value = cell.get("pass")
        pass_text = "—" if pass_value is None else ("pass" if pass_value else "fail")
        result_rows.append(
            "<tr>"
            f'<td>{html.escape(str(cell.get("harness", "")))}</td>'
            f'<td>{html.escape(str(cell.get("task", "")))}</td>'
            f'<td><span class="badge badge-{_status_meta(status)[0]}">'
            f'<span aria-hidden="true">{icon}</span> {html.escape(label)}</span></td>'
            f'<td class="num">{_fmt(pass_value if isinstance(pass_value, bool) else None) if False else pass_text}</td>'
            f'<td class="num">{_fmt(cell.get("time_s"))}</td>'
            f'<td class="num">{_fmt(cell.get("tokens"))}</td>'
            f'<td class="num">{_fmt(cell.get("cost"))}</td>'
            f'<td class="reason">{_fmt(cell.get("reason"))}</td>'
            "</tr>"
        )

    gate_block = (
        '<section class="gate gate-good"><h2>✓ Release gate: PASS</h2>'
        "<p>Every required benchmark cell is measured and passing.</p></section>"
        if gate_ok
        else f'<section class="gate gate-critical"><h2>✗ Release gate: FAIL</h2>'
        f"<p>Required cells missing or not measured (never silently passed):</p>"
        f'<pre class="gate-detail">{html.escape(gate_error or "")}</pre></section>'
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>unified-brain kg — benchmark results</title>
<style>
:root {{
  --bg:#ffffff; --surface:#f6f7f9; --ink:#1b1f24; --muted:#57606a; --border:#d9dee3;
  --good:#1a7f37; --good-bg:#e6f4ea; --warn:#9a6700; --warn-bg:#fff8c5;
  --crit:#cf222e; --crit-bg:#ffebe9; --radius:10px;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg:#0d1117; --surface:#161b22; --ink:#e6edf3; --muted:#9198a1; --border:#30363d;
    --good:#3fb950; --good-bg:#0d2818; --warn:#d29922; --warn-bg:#3a2c00;
    --crit:#f85149; --crit-bg:#4a1212;
  }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }}
main {{ max-width:1000px; margin:0 auto; padding:24px 16px 64px; }}
h1 {{ font-size:1.5rem; margin:0 0 4px; }}
.sub {{ color:var(--muted); margin:0 0 20px; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:20px; }}
.tile {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:14px; }}
.tile-value {{ font-size:1.8rem; font-weight:650; line-height:1.1; }}
.tile-label {{ color:var(--muted); font-size:.82rem; margin-top:2px; text-transform:uppercase; letter-spacing:.04em; }}
.tile-good .tile-value {{ color:var(--good); }}
.tile-warning .tile-value {{ color:var(--warn); }}
.tile-critical .tile-value {{ color:var(--crit); }}
.gate {{ border-radius:var(--radius); padding:14px 16px; margin-bottom:20px; border:1px solid var(--border); }}
.gate-good {{ background:var(--good-bg); }}
.gate-critical {{ background:var(--crit-bg); }}
.gate h2 {{ margin:0 0 4px; font-size:1.05rem; }}
.gate p {{ margin:0; color:var(--muted); }}
.gate-detail {{ white-space:pre-wrap; word-break:break-word; margin:10px 0 0; font-size:.82rem; }}
section h2 {{ font-size:1.05rem; margin:0 0 10px; }}
.table-wrap {{ overflow-x:auto; border:1px solid var(--border); border-radius:var(--radius); }}
table {{ border-collapse:collapse; width:100%; font-size:.9rem; }}
th,td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--border); white-space:nowrap; }}
th {{ background:var(--surface); font-weight:600; position:sticky; top:0; }}
td.num {{ font-variant-numeric:tabular-nums; text-align:right; }}
td.reason {{ white-space:normal; min-width:220px; color:var(--muted); }}
.badge {{ display:inline-flex; gap:4px; align-items:center; padding:2px 8px; border-radius:999px;
  font-size:.78rem; font-weight:600; border:1px solid var(--border); }}
.badge-good {{ color:var(--good); background:var(--good-bg); }}
.badge-warning {{ color:var(--warn); background:var(--warn-bg); }}
.badge-critical {{ color:var(--crit); background:var(--crit-bg); }}
.badge-muted {{ color:var(--muted); background:var(--surface); }}
.harness {{ margin-top:28px; }}
.footer {{ color:var(--muted); font-size:.8rem; margin-top:28px; }}
</style>
</head>
<body>
<main>
<h1>unified-brain kg — benchmark results</h1>
<p class="sub">Live haiku-model harness cells (Claude Code, Cursor, Pi) plus an independent no-tool evaluator. Status semantics are honest: <strong>NOT_MEASURED</strong> never silently passes the release gate.</p>
<div class="tiles">{"".join(stat_tiles)}</div>
{gate_block}
<section class="harness">
<h2>By harness</h2>
<div class="table-wrap">
<table>
<thead><tr><th>Harness</th><th>Measured</th><th>Failed</th><th>Not measured</th><th>Passing</th></tr></thead>
<tbody>{"".join(harness_rows)}</tbody>
</table>
</div>
</section>
<section class="harness">
<h2>Cells</h2>
<div class="table-wrap">
<table>
<thead><tr><th>Harness</th><th>Task</th><th>Status</th><th>Pass</th><th>Time (s)</th><th>Tokens</th><th>Cost</th><th>Reason</th></tr></thead>
<tbody>{"".join(result_rows)}</tbody>
</table>
</div>
</section>
<p class="footer">Generated {html.escape(generated)} from <code>bench/report.json</code>.</p>
</main>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    report = Path(argv[1]) if len(argv) > 1 else REPORT
    out = Path(argv[2]) if len(argv) > 2 else OUT
    cells = json.loads(report.read_text())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(cells), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(cells)} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
