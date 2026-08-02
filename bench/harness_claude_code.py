"""Claude Code benchmark harness argv (contract-exact, no flags invented)."""

CLAUDE_BIN = "/Users/harrynguyen/.local/bin/claude"
COMMAND: list[str] = ["/Users/harrynguyen/.local/bin/claude", "--print", "--output-format", "json", "--model", "haiku"]
CREDENTIAL_ENV = "CLAUDE_API_KEY"
