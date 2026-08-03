# kg:extract

Trigger
: The user asks to turn an ingested source into graph notes.

When
: Use after the source has been ingested and the proposal JSON is ready.

Contract
: Call `kg extract PROPOSAL.json --json`. Assert `ok: true`; stop on nonzero exit or `error`. Retry failed execution at most `KG_RETRY_MAX` times, default 2; `KG_RETRY_MAX=0` means one attempt. Never call `kg apply` without explicit user approval.

Procedure
1. Read the registered raw source and build the proposal JSON.
2. Run `kg extract PROPOSAL.json --json`.
3. Show the checkpoint preview; ask for explicit approval.
4. Only after approval, run `kg apply PROPOSAL.json --json` and assert its envelope.
