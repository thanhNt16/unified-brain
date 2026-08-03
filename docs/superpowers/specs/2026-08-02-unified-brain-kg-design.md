# unified-brain `kg` v1 — design / implementation contract

**Status:** approved (user auto-approval + workflow-synthesized, evidence-grounded from kgx + unified-mem + codebase-memory-mcp scout/challenge).
**Scope:** greenfield `/Users/harrynguyen/Desktop/unified-brain`. Personal local-first knowledge graph toolkit.
**Current state:** a concurrent unreviewed scaffold exists (`pyproject.toml`, `src/kg/*`, five skill stubs). Audit rejected it as a prototype: duplicate command registration, missing `import sys`, unversioned DB, writes outside lock, dropped extraction edges, missing vector/PPR/recursive-CTE/RRF usage, 2/7 dream passes, no CBM UI, no tests/CI/installer/license. **Execution must rewrite, not reuse.**

## 1. Goal

Ship a Python ≥3.11, offline core for personal local-first knowledge graphs: `init → ingest → extract → apply → query → dream → review → graph/viz`. Canonical Markdown is authoritative; SQLite is disposable. One executable: `kg`. One-line source install. Live Claude Code/Cursor/Pi benchmark gate required for every release.

## 2. Non-goals

- No MCP server or MCP configuration.
- No graph database, daemon, scheduler ownership, RBAC, server sync, multi-writer, or speculative plugin framework.
- No `kg save`, `kg traverse`, `kg path`, `kg cypher`, `kg reindex`, `kg migrate`, or separate `approve`/`reject` commands.
- No dense embeddings, numpy, ANN, runtime Node, CDN, static graph snapshot, or unimplemented graph formats.
- No automatic entity resolution: deterministic dedup only; merging differently titled entities requires human review in a later feature.

## 3. Architecture invariants

- CLI is deterministic and LLM-free. Skills own extraction, answer synthesis, dream judgment, and benchmark execution; CLI owns validation, all vault writes, idempotency, locks, transactions, rendering, indexing, and JSON contracts.
- **Single canonical edge model:** proposal `edges[]` become SQLite `edges`; no relation-note files, `relations` frontmatter, or second edge store.
- **Single canonical write path:** `kg apply` only. `kg extract` validates and checkpoints; it never writes canonical notes. `kg review --approve` applies validated dream operations through the same storage primitives.
- **Canonical-file-first transaction:** validate → acquire exclusive lock → atomically replace staged note files → commit one SQLite projection transaction. A DB failure leaves canonical files intact; `kg index --rebuild` converges the derived DB.
- SQLite uses WAL, `synchronous=FULL`, foreign keys, 5-second busy timeout, external-content FTS5 with triggers, and checkpoint `TRUNCATE` after indexing.
- **Single schema owner:** `src/kg/schema.py` owns `CURRENT_VERSION` and migrations. `models.py` and `contract.jsonl` reference that version; newer DB versions hard-fail with `run kg index --rebuild`.
- **Vector v1 is deterministic `hashbow-v1`:** 16,384 signed word-unigram/character-trigram features, sparse postings and precomputed norms. No model/API key needed. Dense vectors are a documented future slot, not shipped.
- Readers do not lock; SQLite WAL provides snapshot reads. Writers use a platform shim: POSIX `fcntl.flock(LOCK_NB)`, Windows `msvcrt.locking`; contention returns a structured error immediately.
- Core commands are offline and deterministic. `kg viz vendor` is the only network/build-time operation; live benchmark harnesses are intentionally external to the CLI.

## 4. Filesystem

```
src/kg/
  cli.py            — Click command tree + envelope/error handling
  models.py         — Pydantic proposal/note/edge/dream-diff; strict extra-forbid
  frontmatter.py    — strict YAML parser + byte-stable renderer
  storage.py        — vault discovery, lock, atomic writes, registry, contract log
  schema.py         — migrations + CURRENT_VERSION
  projection.py     — SQLite projection, FTS/hashbow indexing, rebuild
  ingest.py         — immutable raw capture + SHA256 registry
  extract.py        — proposal validation/checkpoint/render preview
  retrieval.py      — lexical/vector seeds, bounded CTE, RRF/PPR, explainability
  dream.py          — seven bounded deterministic candidate passes
  review.py         — diff status gate + transactional apply
  wiki.py           — deterministic derived Obsidian views
  viz/{api.py,server.py,layout3d.py,vendor.py} — secure graph UI adapter/server
  viz/assets/        — build-time bundled upstream UI
templates/skills/    — one source for harness skill templates
.brain/raw/          — immutable sha256.<ext> captures
.brain/notes/{entity,concept,fact,source,summary}/  — canonical Markdown
.brain/wiki/{index.md,log.md,entities/,concepts/,summaries/}  — generated, never hand-edited
.brain/.kg/{brain.sqlite,registry.jsonl,manifest.json,contract.jsonl,writer.lock,index-errors.jsonl,checkpoints/,dreams/}  — disposable/derived
install.sh          — pinned curl|sh source installer
bench/              — real Claude Code/Cursor/Pi benchmark harnesses, corpus, tasks, reports
tests/              — pytest acceptance/unit/security/package tests
.github/workflows/ci.yml  — platform build/test/release gates
```

## 5. Data model

- **Canonical note frontmatter:** `id`, `kind` (`entity|concept|fact|source|summary`), optional lowercase `type`, `title`, `created`, `updated`, `status` (`draft|verified|superseded|tombstone`), optional `supersedes`, required `source_sha256`, `refs[]`, `tags[]`, `provenance[]`, optional `embedding` metadata. No edge list in frontmatter.
- **Note ID:** `nt_` + first 16 hex of SHA256 of `kind|type|normalized_title`; normalization = Unicode NFKC, whitespace collapse, casefold for the title component. Same semantic title/kind/type re-extracts identically across machines.
- **Proposal JSON:** `{schema_version, source_sha256, notes:[Note], edges:[{src,dst,relation,confidence,evidence?}]}`. Required source hash must exist in `registry.jsonl`; note IDs unique; edge endpoints are proposal IDs or existing non-tombstone IDs; relation enum = `depends_on|causes|supports|contradicts|supersedes|mentions|related_to`; confidence ∈ [0,1]. Hard caps: 500 notes and 2,000 edges per proposal.
- **SQLite tables:** `meta(key,value)`; `notes(id PK,kind,type,title,body,tags_json,frontmatter_json,status,supersedes,source_sha256,created,updated)`; `edges(src,dst,relation,confidence,evidence,PRIMARY KEY(src,relation,dst))`; `notes_fts` external-content FTS5 over title/body with insert/update/delete triggers; `vec_features(feature,note_id,weight,PRIMARY KEY(feature,note_id))`; `doc_norms(note_id PK,l2)`; `deleted_notes(id PK,reason,diff_id,ts)`. Indexes cover status/source/src/dst/relation/note_id.
- **Tombstones** live in canonical frontmatter (`status=tombstone` or `superseded`); `deleted_notes` is only a rebuildable projection. Approving a drop updates the canonical note, deletes its incident edges, inserts `deleted_notes`, and updates the diff in one transaction. No `.tombstone.md` marker or unlink.
- **JSON envelope** for every `--json` command: success `{ok:true,data:{...}}`; failure `{ok:false,error:{code,message,details?}}`. `contract.jsonl` appends `{seq,ts,tool,cmd,args,ok,envelope,data,error}` for CLI validation/mutations; audit log, not reproducible from notes and not claimed as derived.

## 6. Commands (frozen 13-command tree)

| Command | Behavior |
|---|---|
| `kg init ROOT [--json]` | Creates `ROOT/.brain`; rerun no-op. Non-empty ROOT without `.brain` refused. Applies schema, writes manifest. |
| `kg ingest FILE... [--json]` | Regular files only; rejects symlinks/dirs/control paths/unreadable. SHA256-captures atomically to `.brain/raw/sha256.<safe-ext>`, dedups by hash, appends one registry row with `deduped` status. |
| `kg extract PROPOSAL.json [--json]` | Strictly validates, verifies source registry membership + all edge constraints, emits preview, writes checkpoint only after validation. No canonical note/DB mutation. Missing proposal → `schema_validation`. |
| `kg apply PROPOSAL.json [--json]` | Revalidates, locks, stages + atomically replaces canonical notes, commits one projection transaction, appends manifest/audit, returns counts. Sole normal note writer. |
| `kg query QUERY [--strategy adaptive\|lexical] [--hops 2] [--relations CSV] [--direction both\|in\|out] [--limit 20] [--context] [--json]` | Sole retrieval command. |
| `kg dream --passes CSV [--out PATH] [--json]` | Emits deterministic `ProposedDiff(status=proposed)` under `.brain/.kg/dreams/`; never applies. |
| `kg review DIFF [--approve\|--reject] [--json]` | Default read-only. Flags mutually exclusive; approve/reject require path under `.kg/dreams`, hash/status `proposed`, lock, idempotent status guard. |
| `kg index [--rebuild] [--json]` | Migrates then projects all canonical notes, skips malformed with `index-errors.jsonl`, exits 1 after processing if errors, regenerates wiki, checkpoints WAL. `--rebuild` recreates all derived tables. |
| `kg graph --format mermaid\|dot [--json]` | Bounded static export (max 500 edges); all other formats → `unsupported_format`. |
| `kg viz serve [--port 9749] [--wiki DIR] [--no-open]` | Serves bundled UI on `127.0.0.1`. |
| `kg viz vendor [--pin COMMIT\|--apply\|--verify\|--version]` | Manages the pinned upstream at build time. |
| `kg install [--apply\|--uninstall] [--json]` | Prints harness skill plan by default; only `--apply` mutates `.claude/skills/`, `.cursor/rules/`, Pi skill paths. |
| `kg cron-print` | Prints safe cron/launchd/systemd/Task Scheduler instructions; never schedules/starts a daemon. |

## 7. Skills

- `kg:init`, `kg:ingest`, `kg:extract`, `kg:query`, `kg:dream` are the only product skills. Each names exactly one CLI subcommand, has Trigger/When, Contract, Procedure sections, stays under 80 lines, never embeds schema.
- Claude templates render to `.claude/skills/kg-*.md`; Cursor to `.cursor/rules/kg-*.mdc` with required Cursor frontmatter; Pi to its supported skills directory. Shared body content is one source; harness metadata is format-specific, not byte-identical.
- Skills call `kg` only. They read raw/checkpoint/query output, build LLM proposals, show dry-run output, invoke `kg apply` only after explicit user approval. They assert `ok`, stop on nonzero exit/error, honor `KG_RETRY_MAX` (default 2; 0 = one attempt).
- No reviewer skill, no MCP. Review is deterministic CLI behavior, not duplicated LLM logic.

## 8. Flows

- **Init:** `kg init ROOT` → `.brain` skeleton/schema/manifest/contract.
- **Capture:** `kg ingest file` → SHA256 raw object + registry; repeat dedups.
- **Extract:** skill reads registered raw source → LLM creates proposal → `kg extract proposal.json` validates/checkpoints → user reviews preview → `kg apply proposal.json` writes notes/index.
- **Retrieve:** `kg query` lexical/vector seeds → bounded graph expansion → RRF/PPR → explainable envelope/context block.
- **Dream:** `kg dream --passes dedup,contradiction,...` → ProposedDiff only → `kg review diff` → explicit `--approve`/`--reject`.
- **Recovery:** any DB/file divergence → `kg index --rebuild`; canonical notes/raw untouched.
- **Wiki:** `kg index` derives index/log/entity/concept/summary Markdown solely from canonical notes + status history; generated files are never input truth.
- **Install:** `curl -fsSL PINNED_INSTALL_URL | sh` installs only the pinned tool + prints plan; `kg install --apply` is a separate explicit harness mutation.

## 9. Query

- **Seed lexical:** FTS5 BM25; malformed MATCH fallback to safely quoted terms then tokenized `LIKE`; never propagate `OperationalError`. Seed hashbow: sparse posting scan, top `min(3*limit,60)`. `lexical` = lexical seeds only; `adaptive` = union lexical + vector.
- **Traversal:** SQLite recursive CTE starts from sorted seeds, follows `edges` with relation+direction predicates, `depth < hops`, `hops ≤ 4`, deterministic `ORDER BY depth,nid`, global `VISITED_CAP=2000`, seed cap 60. No unrestricted Python frontier scan.
- **Ranking:** graph score + lexical/vector rankings fused with RRF `1/(60+rank)`. PPR 20 iterations, α `0.85`; relation weights `{causes:1.0,depends_on:0.9,supports:0.6,supersedes:0.5,contradicts:0.2,related_to:0.3,mentions:0.15}` × edge confidence; sinks teleport to RRF prior.
- **Result data:** `{results:[{id,title,kind,score,ppr_score,seed_ranks:{bm25,vector,graph},depth,paths,sources,evidence,snippet,path}],strategy_used,seed_counts,visited_count}`. Tombstone/superseded excluded unless a future flag (none in v1).
- **`--context`:** deterministic paragraph packing, `ceil(chars/4)` token budgeting, 32,000-token cap, preserves ID/title/source/evidence, `…[truncated]` marker.

## 10. Dream

- **Seven bounded deterministic passes:** `dedup` exact normalized-title grouping; `contradiction` same-source/tag buckets capped at 200 with bounded pair checks; `supersede`; `stale` (>180 days, no outgoing edge); `orphan`; `open-q` summary/question signals; `community` union-find over confidence > 0.8 edges.
- Each operation = `{op,id,reason,evidence,pass}`. Diff ID = content hash of normalized operations, not UUID; identical runs do not create a second diff. Diff capped at 500 operations.
- Dream never calls an LLM, mutates notes, deletes edges, or schedules itself. `review --approve` applies drops/supersedes through canonical status + one SQLite transaction; already approved/rejected diffs are no-ops.

## 11. Visualization (exact CBM reuse)

- Vendor pristine `DeusData/codebase-memory-mcp/graph-ui` at commit `d6be58ef9d43c574a2d1b0827ecc1e3c4846f0fe`; **no source patches**. Preserve `LICENSE.upstream`, `PROVENANCE.md`, third-party notices. Build Node assets once; wheel-bundle `src/kg/viz/assets`; reject external `http(s)://` references.
- `GET /api/layout?max_nodes=1..2000` returns CBM-shaped `{nodes:[{id,kg_id,x,y,z,label,name,size,color,in_calls:0}],edges:[{source,target,type}],total_nodes,truncated_nodes,truncated_edges}`; sorted IDs, max 2,000 nodes/4,000 edges, max 4 MiB, finite deterministic layout. Dangling edges drop.
- Retain `/api/project`, `/api/schema`, `/api/repo-info`, `/api/ui-config`, read-only supported `/rpc` tools `list_projects|get_graph_schema`, `/wiki/<slug>`, static assets + SPA fallback. Unsupported API calls → 404 or JSON-RPC `-32601`; no arbitrary filesystem browsing/indexing.
- `layout3d.py` ports upstream deterministic Barnes-Hut with FNV-1a seed, 40 iterations, θ 1.2, z=0. Server binds only `127.0.0.1:9749` by default.

## 12. Security

- Bearer token = per-process `secrets.token_urlsafe`, printed once, never persisted/logged, constant-time comparison. Missing/wrong → 403.
- Exact loopback Host allowlist (`localhost`, `127.0.0.1`, optional port) + matching Origin allowlist; non-loopback → 403. CSP `default-src 'self'; script-src 'self'; style-src 'self'`, `nosniff`, `no-store` on errors, ETag/304 on layout.
- All wiki/asset paths: URL decode → PurePosix validation; reject absolute/`..`/backslash/control/symlink/outside-root. SQLite is read-only in viz.
- Ingest rejects symlink arguments; reads regular files only. Writes use same-dir temp + `os.replace`; raw objects immutable + SHA256-verified on read. No shell interpolation in subprocesses.
- POST `/rpc` body cap 64 KiB; layout cap 4 MiB; request timeout 30s; JSON `allow_nan=False`. Scheduler instructions never contain secrets.

## 13. Errors

- All commands support explicit `--json`; no `sys.argv` sniffing. Human mode = concise summary. Exit 0 = completed/no-op; nonzero = structured error.
- **Codes:** `schema_validation`, `unknown_source`, `dangling_edge`, `unsupported_format`, `not_initialized`, `vault_exists`, `lock_busy`, `path_forbidden`, `parse_error`, `index_errors`, `db_schema_newer`, `diff_state`, `diff_path`, `limit_error`, `auth_required`, `forbidden`, `not_found`, `payload_too_large`, `internal_error`.
- Malformed YAML/invalid UTF-8/one corrupt note never aborts an index/dream scan: skip, append to `.brain/.kg/index-errors.jsonl`, continue, exit 1 with count.
- FTS punctuation (`"`, `foo:`, `(`, empty) returns safe results/empty set, never traceback. Unknown relation/direction/strategy/hops/limit fails validation before DB work.
- Crash after canonical replacement but before DB commit → canonical truth + stale derived DB; next `kg index --rebuild` repairs. Crash during one SQLite transaction rolls back. Lock release OS-managed on process death.
- Approve rejects malformed, outside-vault, non-proposed, or hash-mismatched diff. Reject never changes notes/DB. Already decided diff is idempotent.

## 14. Installation

- `install.sh` embeds exact release version, source URL/commit, SHA256 for source/artifact, expected `kg --version`; uses `curl -fsSL`, temp dir, `shasum -a 256 -c`, then `uv tool install --from <verified-source>`. Prints install plan + PATH guidance before install; no harness mutation.
- Installer refuses hash/version mismatch, cleans temp files, reports upgrade/rollback guidance, verifies executable after install. No Node at runtime.
- `kg install` ≠ source install: default prints targets/files; only explicit `kg install --apply` writes harness files; overwrite requires explicit force option + identical-template checks.

## 15. Benchmark (live, mandatory release gate)

- `/Users/harrynguyen/Desktop/unified-brain/bench/` contains one fixed corpus, task manifest, model configuration, runners for Claude Code/Cursor/Pi + no-tool baseline runner.
- Every harness runs the same tasks/corpus/model settings. Report cells = `{harness,task,pass,time_s,tokens,cost,status,reason}`. No synthetic baseline or invented score permitted.
- Unrun cell recorded as `NOT_MEASURED` with reason. **Release gate fails if any required cell is absent or `NOT_MEASURED`; only measured cells can pass a release.** Mandatory immediately; honest missing-data semantics preserved.

## 16. CI / release

- `.github/workflows/ci.yml` matrix: Ubuntu, macOS, Windows × Python 3.11, 3.12, latest; install via uv; lint, type checks, pytest, wheel/sdist build, wheel-content/security checks, CLI smoke.
- CI verifies POSIX/Windows lock shim, deterministic IDs/frontmatter/layout, source installer hash failure/success, wheel-bundled assets, upstream commit/license/provenance, no CDN refs, graph endpoint security.
- Release workflow requires all unit/integration/security/package tests, artifact hash/version verification, + live benchmark job. Benchmark job executes all configured real harnesses; missing credentials/tasks → `NOT_MEASURED` → fail release, never silently pass.
- CI rejects MCP files/config, extra graph formats, unpinned vendored UI, shell interpolation, `0.0.0.0` binds, unbounded payloads, generated wiki edits treated as canonical.

## 17. Testing

- **Parser:** strict frontmatter rejects malformed YAML/missing keys; 3 note kinds round-trip byte-identical (sorted keys, LF, trailing newline).
- **IDs:** subprocesses/re-extracts produce identical note + diff IDs; normalized title behavior tested.
- **Ingest/storage:** duplicate bytes → one raw object; registry statuses correct; symlink input rejected; atomic writes leave no temp residue; two writers serialize; Windows shim exercised in CI.
- **Schema/index:** fresh migration reaches current version; migration idempotent; newer version refuses; malformed notes logged/skipped; rebuild after DB deletion restores query results; FTS triggers + WAL checkpoint verified.
- **Apply:** unknown source, duplicate ID, invalid relation/confidence, dangling edge, cap violations write nothing; success updates notes/edges in one transaction; injected DB failure leaves canonical recoverable via rebuild.
- **Query:** lexical punctuation fallback; A→causes→B→causes→C fixture respects hops/direction/relations/limit; 10k-node hub respects seed/visited caps; RRF/PPR expected order; vector result matches independent hashbow; envelope keys exact.
- **Dream/review:** all 7 passes find injected fixtures; diff IDs deterministic; review read-only by default; approval writes status, tombstone projection, edge cleanup atomically; repeated decisions no-ops.
- **Viz:** token/Host/Origin/CSP/ETag/304/path traversal/symlink/body/payload caps; empty vault 200; exact CBM payload; deterministic finite layout; unsupported routes/tools rejected.
- **Installer/package:** `uv build` wheel contains assets, `LICENSE.upstream`, `PROVENANCE.md`; no absolute CDN URLs; pinned hash mismatch fails, verified install passes; harness untouched until `kg install --apply`.
- **End-to-end:** init → ingest → skill-created proposal → extract → explicit apply → adaptive query JSON → dream → review → approve → index → graph/viz. All writes remain under `.brain` except explicit harness install.

## 18. Milestones

- **M1 — Freeze contracts:** models/frontmatter/IDs, vault layout, registry, envelope, lock shim, migrations, tests.
- **M2 — Durable core:** ingest, strict extract/apply gate, canonical-first atomic projection, index/rebuild, FTS/hashbow, wiki generation, audit/error logs.
- **M3 — Retrieval/dream:** bounded CTE, RRF/PPR/explainability/context packing, all 7 dream passes + transactional review.
- **M4 — Harness:** shared skill templates + generated Claude/Cursor/Pi formats; plan-only/explicit `kg install --apply`.
- **M5 — Visualization:** vendor exact upstream commit, build/bundle assets, secure CBM adapter/server/layout, package/provenance checks.
- **M6 — Distribution/release:** pinned curl|sh installer, platform CI, complete tests, real live benchmark harnesses, release gate before first release.

## 19. Acceptance

- Fresh `uv run kg init /tmp/vault` creates exact `.brain` tree; rerun idempotent; `kg --version` matches package metadata.
- `kg ingest` source is immutable, hash-addressed, deduplicated; same hash required by `kg apply`; unknown source proposals write nothing.
- Canonical note/edge IDs, rendered bytes, diff IDs, query ordering, layout deterministic across repeated processes + platforms.
- Every mutation lock-protected + atomic; injected failures leave no canonical data loss; `kg index --rebuild` repairs any derived divergence.
- Accepted query example returns specified envelope, adaptive seed/graph/PPR fields, relation/direction/hop limits, no crash on malformed punctuation.
- Dream produces only bounded deterministic ProposedDiff; explicit review approval is the only application gate; tombstones + incident edges consistent after rebuild.
- Graph UI is the exact pinned upstream source with attribution, bundled assets, loopback bearer/Host/Origin/CSP/path/payload protections, required API shapes.
- `curl -fsSL <pinned-install-url> | sh` verifies source/artifact hash, installs with uv, verifies version, never mutates harnesses. `kg install --apply` is the only harness mutation.
- All matrix CI tests pass on Linux/macOS/Windows; package contains no CDN/MCP artifacts; live Claude Code/Cursor/Pi benchmark report has every required cell measured. Any missing/`NOT_MEASURED` cell blocks release.

## 20. Source traceability

- **kgx:** reuse typed Markdown/frontmatter, deterministic rendering, RRF/PPR concepts, bounded dream ProposedDiff/review, safe path principles. **Delete:** `synchronous=OFF`, stale incremental edges, duplicate edge representations, quadratic passes, unauthenticated HTTP.
- **unified-mem:** reuse SHA256 raw registry/chunking boundary, Pydantic ontology/gates, resolution-vs-dedup distinction, atomic manifest/plan ideas, snapshot/rollback security lessons, platform storage concepts. **Delete:** broken Pi installer, unversioned `FLOAT[384]`, generation-before-transaction, O(N) filtered ANN, quadratic dream combinations, private MCP patching, arbitrary-root viz, absent licensing.
- **codebase-memory-mcp:** vendor only pristine `graph-ui/` at `d6be58ef9d43c574a2d1b0827ecc1e3c4846f0fe`; port deterministic layout behavior + CBM payload/API compatibility. Preserve license/provenance. Do not port unified-mem UI patches or MCP product behavior.

## 21. Resolved conflicts

- Edge source: proposal `edges[]` → SQLite `edges`; relation files/frontmatter removed.
- IDs: normalized content-derived `nt_` hash; source-slug + UUID IDs removed.
- Writes: `kg apply` only; extract = validate/checkpoint only; `save` + extract-apply removed.
- Vectors: dependency-free hashbow sparse index; dense BLOB/model/dimension machinery removed.
- DB: one schema combining status/type/source/frontmatter with edges/hashbow/FTS/deleted projection; no entities table.
- Tombstones: canonical note status is truth; `deleted_notes` is rebuildable projection; no marker files/unlink.
- Review: one noninteractive `kg review DIFF [--approve|--reject]`; default read-only; no prompts or split commands.
- Commands: frozen 13-command tree; `index --rebuild` replaces reindex/migrate; benchmark stays in `bench/`, not CLI.
- Relation semantics: exactly 7 enum values; confidence is per-edge; relation weights are fixed PPR coefficients.
- Schema: `schema.py.CURRENT_VERSION` owns SQLite version; contract/model versions reference it.
- Wiki: generated exclusively by `kg index`; review never appends log directly.
- Harness files: shared template body with harness-specific metadata; not byte-identical incompatible formats.
- Query: one full explainable result envelope; old minimal result shape removed.
- Visualization: `kg viz serve` is canonical; 127.0.0.1, 2,000 nodes, 4,000 edges, 4 MiB.
- Benchmark: every required cell must be measured for release; absent data is explicitly `NOT_MEASURED`, never fabricated.
