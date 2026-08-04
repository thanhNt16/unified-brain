# kg:apply

Trigger
: The user explicitly approves a validated proposal to persist graph notes.

When
: Use only after `kg:extract` returned a checkpoint preview and the user approved it. Never run `kg apply` without explicit user approval.

Contract
: Run `kg apply PROPOSAL.json --json` from the vault root. Assert `ok: true` and stop on nonzero exit or `error`. Retry failed execution at most `KG_RETRY_MAX` times, default 2; `KG_RETRY_MAX=0` means one attempt.

Procedure
1. Confirm the user approved the checkpoint preview.
2. Run `kg apply PROPOSAL.json --json` from the vault root.
3. Report the returned note/edge counts and the persisted source hash.
4. If it names a pending checkpoint, extract the proposal from `.brain/.kg/checkpoints/<id>.json` and apply that path.