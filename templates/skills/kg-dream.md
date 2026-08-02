# kg:dream

Trigger
: The user asks for bounded graph maintenance suggestions.

When
: Use when deterministic candidate discovery is requested; never apply suggestions automatically.

Contract
: Call `kg dream --passes dedup,contradiction,supersede,stale,orphan,open-q,community --json`. Assert `ok: true`; stop on nonzero exit or `error`. Retry failed execution at most `KG_RETRY_MAX` times, default 2; `KG_RETRY_MAX=0` means one attempt.

Procedure
1. Run only the requested bounded `kg dream` command.
2. Show the proposed diff and its status.
3. Do not mutate notes, edges, or schedules; approval uses the deterministic review CLI.
