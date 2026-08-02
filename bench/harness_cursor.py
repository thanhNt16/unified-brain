"""Cursor benchmark harness argv (contract-exact, no flags invented)."""

CURSOR_BIN = "/Users/harrynguyen/.local/bin/cursor-agent"
MODEL = "haiku"
COMMAND: list[str] = ["/Users/harrynguyen/.local/bin/cursor-agent", "-p", "--output-format", "json", "--model", MODEL]
CREDENTIAL_ENV = "CURSOR_API_KEY"
