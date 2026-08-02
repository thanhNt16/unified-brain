# Unified Brain Compatibility Rulings

Normative authority: `docs/superpowers/specs/2026-08-02-unified-brain-kg-design.md`.
These rulings govern over conflicting plan snippets. Implementers and reviewers must apply them. Each ruling cites the spec section it preserves.

## R0 — Scope

Rulings are deterministic corrections for cross-milestone plan conflicts. They never broaden product scope or relax a security/durability requirement. When a plan snippet and the spec disagree, the spec wins and the snippet is edited in spirit to match.

## R1 — One storage API (M1.5 is authoritative)

Source of truth: `Vault`, `Lock`, `Registry`, `ContractLog`, `atomic_write` as produced by M1.5. (Spec §4 `storage.py`, §5 registry/contract-log shape, §13 `lock_busy`.)

- M1.5 keeps the public names `VaultPaths`, `discover_vault`, `writer_lock`, `Registry(path)`, `ContractLog(path)` AND adds the aliases M2+ consume:
  - `Vault = VaultPaths` alias.
  - `Lock(vault)` constructor accepting a `Vault`/`VaultPaths` and delegating to `writer_lock(vault.lock)`.
  - `Registry.append(row: dict)` overload that accepts a dict row; M1 also keeps `Registry.contains(source_sha256) -> bool`. If positional backward compatibility is needed, `append` accepts `(source_sha256=None, raw_path=None, original_name=None, status=None, **kw)` and merges a supplied dict.
  - `ContractLog.append(...)` stays dict in/dict out and is importable from `storage`.
- M2 ingest (`src/kg/ingest.py`) imports `Vault`, `Lock`, `Registry`, `atomic_write` from `kg.storage` and calls `Registry.contains`/`Registry.append(dict)`. It does not redefine them.
- M2 apply imports the same lock primitive.
- Reviewers reject any milestone that redefines these names locally.

## R2 — One hashbow implementation (M3.1 owns it; M2 imports it)

Source of truth: 16,384-dim sparse features, deterministic, stdlib-only. (Spec §2 `hashbow-v1`, §9 vector seed.)

- `src/kg/hashbow.py` is the single implementation with `DIM=16384`, `extract`, `l2`, `cosine`.
- The bucket function is `zlib.crc32(feature.encode()) % 16384`; trigram sign alternates by `crc32 & 1`; word-unigram sign is `+1`. This matches M3.1 exactly.
- M2 projection (`src/kg/projection.py`) imports `from kg.hashbow import DIM, extract, l2`. It never reimplements hashing and never uses SHA256 buckets.
- M2.3/M2.4 test for hashbow via the imported module so vector and projection share behavior.
- `vec_features(feature, note_id, weight)` and `doc_norms(note_id, l2)` are populated from `extract(text)`.

## R3 — schema.py migration history is append-only (M1.6 → M2.2)

Source of truth: `schema.CURRENT_VERSION` owns SQLite versioning; migrations are ordered and idempotent. (Spec §5, §13 `db_schema_newer`.)

- M1.6 ships `CURRENT_VERSION = 1` and `MIGRATIONS: OrderedDict`.
- M2.2 appends migration step 2 to `MIGRATIONS`, increments `CURRENT_VERSION = 2`, and reuses the same `migrate(conn)` loop. It must NOT rewrite `schema.py` from scratch and must NOT delete the v1 entry.
- The v1 migration uses `notes_fts` as an external-content FTS5 table (`content='notes', content_rowid='rowid'`) from the start, with the standard insert/update/delete triggers. M2 only adds tables/columns/constraints it needs; if a column type changes, it uses an additive migration (rename + new column + copy) rather than `DROP TABLE`.
- `deleted_notes.diff_id` is nullable (`diff_id TEXT`) to match the proposal diff lifecycle; M2 must not make it `NOT NULL`.
- `migrate` checks `current > CURRENT_VERSION → RuntimeError("db_schema_newer")` before applying any step.
- Reviewers reject any `DROP TABLE`/overwrite of `meta`/`notes`/`edges`/`notes_fts` in migration 2.

## R4 — Diff/dream model vocabulary (M1.2 is authoritative; M3 aligns)

Source of truth: `DreamOp`/`ProposedDiff` from M1.2, with diff IDs `df_`+16 hex. (Spec §10 `{op,id,reason,evidence,pass}` and content-hashed diff ID.)

- M1.2 produces `DreamOp(op, id, reason, evidence, pass_name)`, `ProposedDiff(id pattern ^df_[0-9a-f]{16}$, status, operations)`. `en_` entity IDs are not part of M3 dream operations; if M3 needs an entity-id helper, it lives in `ids.py` as `entity_id(...)` producing `en_`+16 hex and is only used where the spec calls for it.
- M3 dream passes produce `DreamOp` instances whose `pass_name` is one of `dedup|contradiction|supersede|stale|orphan|open-q|community` and whose `op` is `drop|supersede`. M3 must not invent `ops/pass_/flag/open_q` field names.
- M3 review computes the diff id as a content hash of normalized operations (deterministic, identical inputs → same id), per spec §10.

## R5 — Root CLI is append-only; helper layer is M1.8-owned

Source of truth: one Click command tree (Spec §6). (Spec §6 command table, §13 `--json`.)

- The first task that creates `src/kg/cli.py` (M1.8 or whichever plan task introduces CLI) defines a `@click.group() def main()` root, the `kg --version` option, and shared helpers `_require_vault`, `_open_db`, `_emit` (wrapping `envelope.ok/error`).
- Every later milestone (M2.8 index, M3.8 query/dream/review, M4.5 install, M5.2/M5.6 viz) imports the root group and helpers, then `main.add_command(...)` or uses `@main.command()` decorators. No milestone redefines `main` or replaces previously registered commands.
- If a plan snippet shows a standalone `serve_command` group for viz, it is attached as `main.add_command(viz_group)`; the root group stays one.
- Commands must NOT add a `ROOT` argument to commands the spec declares without one (`kg index` has no ROOT; `kg query QUERY` takes the query string).
- Reviewers reject any milestone that recreates `cli.py` or shadows a prior command/helper name.

## R6 — Packaging single source of truth (M1.1 sets it; later milestones only add)

Source of truth: package name `unified-brain-kg`, version `1.0.0`, Python `>=3.11`, hatchling src layout. (Spec §1 goal, §15 release.)

- M1.1 writes the canonical `pyproject.toml` with `name = "unified-brain-kg"`, `version = "1.0.0"`, and `[tool.hatch.build.targets.wheel] packages = ["src/kg"]`.
- M4 must add wheel packaging for `templates/skills/` by extending the wheel target's `sources`/`force-include` (e.g. `force-include = {"templates/skills" = "templates/skills"}`) so harness skill templates survive `uv build`. M4 must NOT overwrite metadata.
- M5.1 must NOT rewrite `pyproject.toml` to `name = "unified-brain"` or `version = "0.1.0"`. It only adds viz packaging: `packages = ["src/kg", "src/kg/viz"]` (or nested wheel target) plus `force-include` for `src/kg/viz/assets`, `LICENSE.upstream`, and `PROVENANCE.md`. If it needs `[tool.uv]`, it adds the section without touching metadata.
- M6.1 must NOT use fragile string replacement of `0.0.0.0`/`0.0.0`. It reads `pyproject.toml` via `tomllib`, asserts the existing version is already `1.0.0`, and makes `src/kg/release.py` the single source imported by `src/kg/__init__.py`. If a prior milestone left a non-1.0.0 version, M6.1 fixes it explicitly by writing the literal `1.0.0`.
- Reviewers reject any milestone that changes package `name`, lowers Python requirement, or rewrites a prior milestone's pyproject sections.

## R7 — Visualization payload consistency (M5)

Source of truth: CBM payload `{nodes:[{id,kg_id,...,in_calls:0}], edges:[{source,target,type}]}`. (Spec §11.)

- Node `id` and edge `source`/`target` use the SAME vault note id namespace (`nt_...` strings). `kg_id` is the vault note id echoed for CBM compatibility; it must equal the node `id`.
- M5 API (`api.py`) must build nodes and edges from one source so dangling edges drop cleanly: edge endpoints are matched against the selected node-id set before emission.
- `in_calls` is the literal integer `0` for every node.
- `serve(vault_root, db_path, *, host, port, wiki, open_browser)` is the single server entrypoint. M5.2 CLI calls it with `vault_root`/`db_path`; M5.5 server defines it with those required parameters. No milestone may define a second `serve(host, port, wiki, open_browser)` that omits vault discovery.
- Reviewers reject a viz API that mixes `kg_id` and `nt_` namespaces or emits edges whose endpoints are not in the node set.

## R8 — Release gate and installer honesty (M6)

Source of truth: real measured benchmark cells; pinned hash-verifying installer. (Spec §15, §14, §16.)

- Benchmark runners actually execute each configured harness; `NOT_MEASURED` is only for genuinely missing credentials/tasks and must fail the release gate.
- M6 release gate (`bench/gate.py`) imports the runner, requires every mandatory cell to be `MEASURED`, and fails on any `NOT_MEASURED`/`FAILED`/absent cell.
- Fake/no-credential harness results must not be mass-produced as passing; the no-tool baseline is a real runner.
- `install.sh` ships a real pinned source URL/commit plus its SHA256. It must not ship a placeholder hash. The hash verification step guards the same artifact that the install step consumes.
- Release workflow (`.github/workflows/release.yml`) reuses CI via `workflow_call` or inlines the same jobs; it must not reference a missing job.
- Reviewers reject placeholder hashes, fabricated benchmark cells, or release workflows that call undefined CI jobs.

## R9 — Distribution policy test scope (M6.5)

Source of truth: CI rejects MCP files/config, extra formats, unpinned UI, `0.0.0.0`, generated wiki as canonical. (Spec §16.)

- M6.5 `test_distribution_policy.py` asserts the absence of forbidden artifacts under `src/`, `tests/`, `bench/`, `.github/`, and packaged wheels only.
- It must NOT scan `docs/superpowers/plans/` or `docs/superpowers/specs/` (those legitimately mention MCP/CDN as deletions/traceability).
- The README may use the phrase "no MCP layer" when describing the product; the distribution policy test matches forbidden file paths and artifacts, not English prose.
- M6.7's LICENSE/NOTICE/CONTRIBUTING/README must exist before M6.5 runs; ordering within M6 is M6.7 → M6.5 if M6.5 inspects docs.

## R10 — Test data uses valid IDs (M1/M2/M3)

Source of truth: note id `nt_`+16 hex, edge endpoints are note ids. (Spec §5.)

- Any test fixture note id matches `^nt_[0-9a-f]{16}$`; diff ids match `^df_[0-9a-f]{16}$`; entity ids `^en_[0-9a-f]{16}$`.
- Edge endpoints in tests are valid note ids present in the same proposal's `notes[]` or marked as pre-existing.
- M2/M3 tests must not use stub ids like `nt_a` that fail M1's regex.
- Reviewers reject tests using invalid id fixtures.

## R11 — M1.3 frontmatter body slice

`parse_frontmatter` returns `text[end + 6:]` where `end = text.find("\n---\n", 4)`; the `\n---\n` is 5 chars, so the body starts at `end + 5`. M1.3 must use `text[end + 5:]`. Render path strips a trailing newline from the body and adds exactly one; round-trip tests must confirm `body == "Body\n"`.

## R12 — Dependency-name tests parse constrained strings (M1.1)

`"pytest" in ["pytest>=8,<9", ...]` is `False` (list membership is exact). M1.1 parses each dependency spec to its bare name (split on the first `<>!=`) before asserting membership. Applies to any later dependency-presence test.
