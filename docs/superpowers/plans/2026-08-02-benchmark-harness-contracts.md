# Benchmark Harness Contracts (M6 binding)

Source: read-only discovery workflow (no model invoked). Governs `bench/` runners so every cell is honestly measured or explicitly `NOT_MEASURED`. Supplements spec §15/§16 and rulings R8.

## Common runner rules

- Validate argv against the contract before launch; reject every unsupported/unverified flag. Never construct a shell command.
- Launch: `subprocess.Popen(argv, cwd=ABSOLUTE_WORKSPACE, env=ENV, shell=False, stdin=DEVNULL, stdout=PIPE, stderr=PIPE, start_new_session=True)`. `cwd` must be absolute and existing.
- Capture stdout/stderr as bytes; decode UTF-8 with replacement only after completion; retain both.
- Timeout is external: on expiry SIGTERM the process group, short grace, then SIGKILL; classify `FAILED`.
- Exit 0 + parseable expected JSON → `MEASURED`. Nonzero/signal/timeout/launch error/malformed JSON → `FAILED`.
- Auth probes, inspection-only, rejected contracts, pre-invocation skips → `NOT_MEASURED` with reason. Auth success ≠ measured.
- `pass` comes from the task evaluator, not process exit alone.
- `tokens=null`, `cost=null` unless a validated numeric schema field exists. Never estimate from text/timing/billing.
- Return stable `{harness,task,pass,time_s,tokens,cost,status,reason}`. Redact secrets from reason.

## Claude Code

- Binary: `/Users/harrynguyen/.local/bin/claude` (symlink; native at `~/.local/share/claude/versions/2.1.220`). Version 2.1.220.
- argv: `["/Users/harrynguyen/.local/bin/claude", "--print", "--output-format", "json", "--model", "haiku", PROMPT]`
- cwd: subprocess `cwd=` only (no `--cwd`).
- auth probe (no model): `["claude", "auth", "status"]` → loggedIn=true, oauth_token, firstParty.
- Reject undocumented `--cwd`, `--timeout`, `--sandbox`, and dangerous bypass flags by default.
- `/9router-models` routing not exposed by Claude CLI; do not claim it.

## Cursor

- Binary: `/Users/harrynguyen/.local/bin/cursor-agent` (version 2025.09.18-7ae6800). Bundles own Node.
- argv: `["/Users/harrynguyen/.local/bin/cursor-agent", "-p", "--output-format", "json", "--model", MODEL, PROMPT]`
- `/usr/local/bin/cursor` is a VS Code-style launcher — NOT the benchmark binary. `cursor agent` delegates to outdated cursor-agent — do not use.
- auth probe (no model): `["/Users/harrynguyen/.local/bin/cursor-agent", "status"]` → Login successful.
- Model identity/config unknown; require explicit model mapping before treating result as comparable.
- User Pi `/9router-models` config does not transfer to Cursor.

## Pi (0.83.0)

- Must launch with explicit Node v22.19.0; ambient PATH Node is v20.14.0.
- argv: `["/Users/harrynguyen/.nvm/versions/node/v22.19.0/bin/node", "/Users/harrynguyen/.nvm/versions/node/v22.19.0/lib/node_modules/@earendil-works/pi-coding-agent/dist/cli.js", "--print", "--mode", "json", PROMPT]`
- Model: preserve configured `/9router-models haiku` via Pi config; do NOT pass unverified `--model`/`--provider`. Settings show `defaultProvider=9router`.
- auth/model probe (no model invocation): `[…cli.js, "--offline", "--list-models", "haiku"]`.
- env: copy `os.environ`; prepend `~/.nvm/versions/node/v22.19.0/bin` to child PATH for Node-dependent extensions. Preserve `PI_CODING_AGENT_DIR` if set; otherwise default `~/.pi/agent`. Never create/rewrite/delete 9router config.
- Validate child Node runtime before a measured run; version mismatch → `FAILED`/`NOT_MEASURED` before model invocation, never silent retry on Node v20.

## No-tool baseline

- Real runner with no external coding-agent harness; same task/corpus/evaluator. Cell is `MEASURED` when the evaluator runs; never fabricated.

## Open blockers (honest)

- No validated token/cost fields observed anywhere → `null`, not estimates.
- Cursor model identity must be resolved before its cell is comparable.
- Actual benchmark execution requires separate authorization (this doc is inspection-only).
