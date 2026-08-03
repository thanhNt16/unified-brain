# kg:ingest

Trigger
: The user asks to capture one or more local source files.

When
: Use only for regular files explicitly named by the user.

Contract
: Call `kg ingest FILE... --json`. Assert `ok: true`; stop on nonzero exit or `error`. Retry failed execution at most `KG_RETRY_MAX` times, default 2; `KG_RETRY_MAX=0` means one attempt.

Procedure
1. Preserve each user-provided path exactly.
2. Run only `kg ingest FILE... --json`.
3. Report hashes, deduplication status, and returned data.
