# Unified Brain Master Execution DAG

> **Authority:** `docs/superpowers/specs/2026-08-02-unified-brain-kg-design.md` is normative. Milestone plan snippets are implementation guidance. When a snippet, test, or file verb conflicts with the spec or established interface, preserve the spec and record the correction in the SDD ledger.

**Goal:** Execute M1–M6 without same-file races, then pass the full acceptance, packaging, security, benchmark, and live-harness release gates.

## Frozen invariants

- Python >=3.11; one `kg` executable; no MCP layer, daemon, Node runtime, CDN, numpy, or dense vectors.
- Canonical Markdown is authoritative. SQLite is a disposable derived index.
- `kg apply` is the sole normal canonical-note writer.
- IDs: `nt_`, `eg_`, and `en_` plus deterministic SHA256-derived 16-hex suffixes.
- Hashbow-v1: 16,384 sparse dimensions.
- Query: lexical + vector seeds, bounded recursive-CTE traversal, RRF/PPR fusion.
- Visualization: pristine CBM `graph-ui/` pinned at `d6be58ef9d43c574a2d1b0827ecc1e3c4846f0fe`; secure Python loopback backend.
- All JSON CLI output uses `{ok, data, error}`.
- Required benchmark cells must be measured; `NOT_MEASURED` fails release.

## Dependency graph

```text
DAG/spec freeze
  |
  v
M1 contracts
  |------------------|
  v                  v
M2 durable core     M4.1-M4.4 harness internals
  |                  |
  |----------|       |
  v          v       v
M3 query/   M5 viz  M4.5 CLI integration
 dream       |
  |----------|-------|
             v
        CLI consolidation
             |
             v
        M6 distribution
             |
             v
  full review + E2E + live benchmarks
```

## Interface cross-check

| Producer | Frozen interface | Consumers |
|---|---|---|
| M1 `models.py` | `Relation`, `NoteStatus`, `Provenance`, `Note`, `Edge`, `Proposal`, `DreamOp`, `ProposedDiff` | M2 extract/apply/projection; M3 dream/review; M5 API |
| M1 `frontmatter.py` | strict deterministic parse/render | M2 projection/apply/wiki; M3 context/review |
| M1 `ids.py` | deterministic note/edge/entity IDs | M2 extract/apply; M3 dream; M5 payload IDs |
| M1 `storage.py` | `Vault`, cross-platform `Lock`, `Registry`, `ContractLog`, `atomic_write` | M2–M5 writers/installers |
| M1 `schema.py` | `CURRENT_VERSION`, ordered `MIGRATIONS`, `migrate` | M2 projection migration; M3 query; M5 read-only API |
| M1 `envelope.py` | success/error envelope and stable error codes | every CLI command |
| M2 `projection.py` | `notes`, `edges`, `notes_fts`, `vec_features`, `doc_norms`, `deleted_notes`; index/rebuild APIs | M3 retrieval/traversal/PPR; M5 layout API |
| M2 `extract.py` | validate/checkpoint only; no canonical mutation | M3 review flow; harness extract skill |
| M2 `apply.py` | canonical-first transactional apply | M3 approved dream operations; harness workflows |
| M2 `wiki.py` | deterministic generated-only views | M5 `/wiki/<slug>` |
| M3 `hashbow.py` | `DIM=16384`, sparse extract/norm/cosine | M2 projection implementation and M3 vector query. If M2 lands first, it imports this module rather than maintaining duplicate hashing logic. |
| M3 `query.py` | adaptive query and context packing | root CLI; harness query skill; benchmarks |
| M3 `dream.py` / `review.py` | deterministic proposals; explicit transactional approve/reject gate | root CLI; harness dream skill |
| M4 templates/render/install | harness-neutral source bodies; atomic owned-file install | CLI install command; integration tests |
| M5 API/server | CBM payload contract; `127.0.0.1`; bearer, Host/Origin/CSP/caps | viz CLI; package tests |
| M6 release/bench | version single source; measured cell validation | CI/release workflows and docs |

## Shared-file serialization

| File | Serialized owner order |
|---|---|
| `src/kg/cli.py` | M2.8 → M3.8 → M4.5 → M5.2/M5.6 → M6 smoke/version checks. Each task extends the existing Click tree; never replaces prior commands. |
| `src/kg/schema.py` | M1.6 → M2.2. M2 appends one migration and increments `CURRENT_VERSION`; never rewrites migration history. |
| `src/kg/projection.py` | M2.3 → M2.4 → M2.6. |
| `src/kg/install.py` | M4.3 → M4.4. |
| `pyproject.toml` | M1.1 → M5.1/M5.8 package-data additions → M6.1/M6.5 release metadata. Later tasks merge sections; never recreate the file. |
| `src/kg/__init__.py` | M1.1 → M6.1 version single-source import. |
| `.github/workflows/ci.yml` | M5.8 establishes viz checks → M6.6 consolidates the complete platform matrix. M6 modifies, not independently creates. |

## Execution waves

Only tasks with disjoint production files may execute concurrently. Every task must land with its own tests, commit, spec review, and quality review before dependents start.

1. **Wave 0 — baseline:** record approved spec/plans and rejected scaffold; initialize feature branch and SDD ledgers.
2. **Wave 1 — M1:** M1.1 first. Then M1.2–M1.4 may run concurrently; M1.5–M1.7 may run concurrently after their imported model interfaces exist. M1.8 gates the milestone.
3. **Wave 2 — M2 + M4 internals:** run M2 in dependency order. M4.1–M4.4 may run alongside M2 because their production files are disjoint. Hold M4.5 until M2.8 has landed.
4. **Wave 3 — M3 + M5 internals:** M3.1 first if M2 projection has not already centralized hashbow. M3 and M5 tasks may run concurrently only where files are disjoint. Serialize root CLI integration in the shared-file order above.
5. **Wave 4 — integration:** run M2.9, M3.8, M4.5, M5.6–M5.9 after all consumed interfaces land. Run complete M1–M5 suite.
6. **Wave 5 — M6:** release metadata → installer/bench in disjoint lanes → release gate → distribution policy → consolidated CI/release workflows → docs → complete verification.
7. **Wave 6 — final:** whole-branch code/security/spec review; fix once; run unit/integration/E2E, wheel install smoke, graph-viz acceptance, and real Claude Code/Cursor/Pi/no-tool benchmark cells.

## Pre-flight corrections

- Plan assertions such as membership tests against version-constrained dependency strings must test package names correctly; preserve the intended contract rather than a mechanically false assertion.
- Tasks that label an existing file `Create` (`pyproject.toml`, `.github/workflows/ci.yml`) must modify/merge it at that milestone.
- M2 and M3 must share one hashbow-v1 implementation. No duplicated hash extraction logic.
- CLI tasks must register subcommands onto one Click root. No task may replace commands added by an earlier milestone.
- Live benchmark cells cannot be fabricated or silently skipped. Missing harness executables or results produce an explicit failed release gate.

## Completion gate

Complete only when:

```text
init → ingest → extract → apply/index → adaptive query → dream → review → graph viz
```

passes end-to-end, all required CI matrix cells are defined, wheel assets are offline and attributed, security checks pass, and every mandatory benchmark integration reports a real measured result.
