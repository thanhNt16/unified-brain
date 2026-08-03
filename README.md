# unified-brain kg

[![CI](https://github.com/thanhNt16/unified-brain/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/thanhNt16/unified-brain/actions/workflows/ci.yml)
[![Benchmark Pages](https://img.shields.io/badge/benchmark-pages-1a7f37)](https://thanhnt16.github.io/unified-brain/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

`kg` is a Python 3.11+ command-line toolkit for an **offline, local-first
knowledge graph**. Canonical Markdown is authoritative; SQLite is derived and
disposable. There is **no MCP layer, no graph database, no daemon, no runtime
Node, no CDN, and no dense-embedding model.** The CLI is deterministic and
LLM-free; a small set of skills drive the LLM steps (exactly five product
skills: `kg:init`, `kg:ingest`, `kg:extract`, `kg:query`, `kg:dream`).

- **Repo:** https://github.com/thanhNt16/unified-brain
- **Benchmark dashboard:** https://thanhnt16.github.io/unified-brain/
- **CI:** Linux/macOS/Windows × Python 3.11–3.13, full test + lint + type + build gate

## Summary

| Area | Approach |
|---|---|
| Canonical truth | Markdown notes with typed YAML frontmatter (POLE ontology) |
| Derived index | SQLite (WAL, FTS5, hashbow-v1 sparse vectors), disposable |
| Vectors | `hashbow-v1` — 16,384-dim sparse, stdlib-only, no numpy |
| Query | lexical + vector seeds → bounded recursive-CTE → RRF/PPR fusion |
| Dream | seven deterministic maintenance passes (no LLM) |
| Review | transactional approve/reject gate, read-only by default |
| Graph UI | vendored exact CBM `graph-ui` on a secure loopback Python server |
| Install | pinned, SHA256-verifying `curl | sh` source installer |
| Release gate | real live coding-agent benchmarks; `NOT_MEASURED` never passes |

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/) for installation and development

## Install

Install the pinned, hash-verified release from source in one step:

```sh
curl -fsSL https://github.com/thanhNt16/unified-brain/raw/main/install.sh | sh
```

The installer downloads the pinned source tarball, wheel, and published
`SHA256SUMS`, verifies every checksum via `shasum -a 256 -c` **before** any
install, installs through `uv tool install --from <verified-source>`, then
verifies `kg --version`. It prints the install plan and PATH guidance, mutates
no harness files, and cleans its temp directory on every exit path. There is no
Node runtime at install or runtime — the graph UI is a build-time artifact
bundled into the wheel.

### From source (development)

```sh
git clone https://github.com/thanhNt16/unified-brain.git
cd unified-brain
uv sync --group dev
uv run kg --version        # kg 1.0.0
```

## What the installer does not do

Installing the package from source does **not** touch any agent harness files.
Harness skills and rules are written only by the explicit, opt-in command:

```sh
kg install --apply
```

`kg install` by itself only prints the harness skill plan (target files per
harness). Overwrites require an explicit `--force` plus identical-template
checks. This separation is intentional: a source install is read-only with
respect to `.claude/skills/`, `.cursor/rules/`, and Pi skill paths.

## Commands (frozen 13-command tree)

| Command | Behavior |
|---|---|
| `kg init ROOT [--json]` | create `ROOT/.brain`; applies schema, writes manifest; rerun is a no-op |
| `kg ingest FILE... [--json]` | SHA256-capture raw sources into `.brain/raw/`, dedup by hash |
| `kg extract PROPOSAL.json [--json]` | strictly validate a proposal and write a checkpoint; never mutates canonical notes |
| `kg apply PROPOSAL.json [--json]` | the sole canonical writer: revalidate, lock, atomically replace notes, commit the projection |
| `kg query QUERY [--strategy adaptive\|lexical] [--hops 2] [--relations CSV] [--direction both\|in\|out] [--limit 20] [--context] [--json]` | the sole retrieval command |
| `kg dream --passes CSV [--out PATH] [--json]` | bounded deterministic ProposedDiff only; never applies |
| `kg review DIFF [--approve\|--reject] [--json]` | read-only by default; apply only on explicit approval |
| `kg index [--rebuild] [--json]` | project canonical notes into SQLite, regenerate wiki, rebuild derived tables with `--rebuild` |
| `kg graph --format mermaid\|dot [--json]` | bounded static export (max 500 edges) |
| `kg viz serve [--port 9749] [--wiki DIR] [--no-open]` | serve the bundled graph UI on `127.0.0.1` |
| `kg viz vendor [--pin COMMIT\|--apply\|--verify\|--version]` | manage the pinned upstream graph UI at build time |
| `kg install [--apply\|--uninstall] [--json]` | print harness plan by default; only `--apply` writes harness files |
| `kg cron-print` | print safe cron/launchd/systemd/Task Scheduler instructions; never schedules |

All commands support explicit `--json` (`{ok:true,data:{...}}` /
`{ok:false,error:{code,message,details?}}`); human mode is a concise summary.

## Quickstart workflow

```sh
kg init /tmp/vault
cd /tmp/vault

# 1. Capture immutable raw sources
kg ingest note.md reference.pdf

# 2. LLM skill reads a registered source and builds a proposal,
#    then the CLI validates it (no writes):
kg extract proposal.json

# 3. Explicitly apply the reviewed proposal: canonical notes + projection
kg apply proposal.json

# 4. Query the graph (deterministic, offline)
kg query "linked-note query" --strategy adaptive --context --json

# 5. Dream proposes maintenance ops; review applies them only on approval
kg dream --passes dedup,contradiction,supersede,stale,orphan,open-q,community
kg review .brain/.kg/dreams/<diff>.json --approve

# 6. Regenerate the derived DB and wiki
kg index

# 7. Open the bundled graph UI on the loopback interface
kg viz serve --port 9749
```

Every write lands under `.brain`; recovery from any derived divergence is
`kg index --rebuild`. Canonical notes and raw captures are never touched by
derived regeneration.

## Skills-first architecture

Five product skills guide the harness agent; each names exactly one CLI
subcommand, has Trigger / When / Contract / Procedure sections, stays under 80
lines, never embeds schema, and calls `kg` only.

| Skill | Drives |
|---|---|
| `kg:init` | `kg init ROOT --json` |
| `kg:ingest` | `kg ingest FILE... --json` |
| `kg:extract` | `kg extract PROPOSAL.json --json` |
| `kg:query` | `kg query QUERY --json` |
| `kg:dream` | `kg dream --passes CSV --json` |

`kg install --apply` renders these to `.claude/skills/kg-*.md`,
`.cursor/rules/kg-*.mdc`, and Pi's skills directory from one shared template
source. There is no reviewer skill and no MCP — review is deterministic CLI
behavior, not duplicated LLM logic.

## Graph UI (offline, pinned upstream)

The graph UI is vendored pristine from
[DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp)
`graph-ui` at commit `d6be58ef9d43c574a2d1b0827ecc1e3c4846f0fe`, with no source
patches. Upstream licensing and provenance are bundled (`LICENSE.upstream`,
`PROVENANCE.md`, third-party notices) and ship in the wheel under
`kg/viz/assets/`.

`kg viz serve` binds loopback (`127.0.0.1:9749`) only, with a per-process
bearer token printed once, exact loopback Host/Origin allowlists, CSP/nosniff
headers, bounded layout/payload caps, a 30s request timeout, strict path
traversal rejection, and a read-only SQLite connection. The UI is a static
bundle — no CDN, no external network access at runtime.

## Benchmarks & release gate

`bench/` holds a fixed corpus, a task manifest, a model configuration, and real
harness runners (Claude Code, Cursor, Pi, and a no-tool baseline). Every release
runs the same corpus and tasks through every configured harness.

- **Live dashboard:** https://thanhnt16.github.io/unified-brain/
- **Release gate:** `python -m bench.gate bench/report.json` — requires every
  mandatory cell `MEASURED` + passing; any absent or `NOT_MEASURED` cell blocks
  the release (never silently passes).

Results are reported per cell as `{harness, task, pass, time_s, tokens, cost,
status, reason}`. Cells that cannot be measured are recorded honestly as
`NOT_MEASURED` with their reason; no synthetic or invented scores are produced.
See [benchmark harness contracts](docs/superpowers/plans/2026-08-02-benchmark-harness-contracts.md).

## Project structure

```
src/kg/            core: cli, models, frontmatter, ids, storage, schema,
                  projection, ingest, extract, apply, retrieval, dream, review,
                  hashbow, wiki, index, envelope, release, install, harness
src/kg/viz/        secure graph UI: api, server, layout3d, vendor (+ bundled assets)
templates/skills/  one shared source for the five harness skills
bench/             corpus, tasks, runner, harnesses, gate, pages renderer
tests/             pytest unit/integration/security/package/bench
docs/              design spec, milestone plans, rulings, harness contracts
.github/workflows/ ci.yml (platform matrix), release.yml (live benchmark gate),
                  pages.yml (benchmark dashboard)
install.sh         pinned, hash-verifying source installer
```

## Development

```sh
uv sync --group dev
uv run pytest -q                       # full suite
uv run ruff check src tests bench      # lint
uv run mypy src/kg                     # types
uv build                               # wheel + sdist
```

CI runs the full matrix on push/PR and is reusable via `workflow_call`; the
release workflow requires all checks plus a live benchmark gate.

## Security

- Loopback-only HTTP; per-process bearer token printed once, never persisted or logged
- No shell interpolation in subprocesses; `kg` uses direct exec
- Ingest accepts regular files only and rejects symlinks, directories, and control paths
- The installer verifies pinned SHA256 checksums before installing and refuses any mismatch
- `kg cron-print` only prints scheduler instructions; it never schedules or starts a daemon

## License

MIT. See `LICENSE` for the full text, `NOTICE` for attribution of the vendored
graph UI, and `LICENSE.upstream` / `PROVENANCE.md` for the upstream license and
provenance of the pinned asset.
