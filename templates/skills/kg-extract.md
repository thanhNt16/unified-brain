# kg:extract

Trigger
: The user asks to turn an ingested source into graph notes.

When
: Use after `kg:ingest` succeeds and the vault is the current working directory.

Contract
: `kg extract RAW_PATH --json` prepares registered source metadata only. Read the returned raw files and author the proposal JSON at the returned `proposal_path`; then run `kg extract PROPOSAL.json --json` to validate and checkpoint it. Never call `kg apply` without explicit user approval. Retry failed execution at most `KG_RETRY_MAX` times, default 2; `KG_RETRY_MAX=0` means one attempt.

Procedure
1. Run `kg extract RAW_PATH --json` from the vault root. `RAW_PATH` may be `.brain/raw` or the ingested source directory.
2. Read every returned `raw_path`. Build one strict proposal JSON per source using the returned `source_sha256`:

```json
{
  "schema_version": 1,
  "source_sha256": "<64-hex source_sha256>",
  "notes": [],
  "edges": []
}
```

Each note needs `id` (`nt_` plus 16 lowercase hex), `kind` (`entity|concept|fact|source|summary`), `title`, `created`, `updated`, `status`, `source_sha256`, `refs`, `tags`, `provenance`, and optional `body`. Each edge needs `src`, `dst`, `relation`, and `confidence` between 0 and 1.
3. Write the proposal to the returned `proposal_path`, then run `kg extract PROPOSAL.json --json` from the vault root.
4. Show the returned checkpoint preview and ask for explicit approval.
5. Only after approval run `kg apply PROPOSAL.json --json`; assert `ok: true`. Never apply automatically.
