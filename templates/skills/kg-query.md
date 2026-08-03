# kg:query

Trigger
: The user asks a question answerable from the local graph.

When
: Use for retrieval, explanation, paths, sources, or deterministic context packing.

Contract
: Call `kg query QUERY --strategy adaptive --json`. Assert `ok: true`; stop on nonzero exit or `error`. Retry failed execution at most `KG_RETRY_MAX` times, default 2; `KG_RETRY_MAX=0` means one attempt.

Procedure
1. Preserve the query and requested retrieval options.
2. Run only `kg query QUERY --strategy adaptive --json`.
3. Use only returned results, evidence, sources, paths, and context in the answer.
