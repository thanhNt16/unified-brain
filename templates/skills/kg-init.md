# kg:init

Trigger
: The user asks to create or verify a local knowledge graph vault.

When
: Use when the vault root is known and initialization is explicitly requested.

Contract
: Call `kg init ROOT --json`. Assert `ok: true`; stop on nonzero exit or `error`. Retry failed execution at most `KG_RETRY_MAX` times, default 2; `KG_RETRY_MAX=0` means one attempt.

Procedure
1. Resolve the requested ROOT without changing it.
2. Run only `kg init ROOT --json`.
3. Inspect the JSON envelope and report the returned data.
