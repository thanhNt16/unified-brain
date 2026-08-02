"""Release metadata shared by packaging and the CLI."""

VERSION = "1.0.0"
EXPECTED_CLI_VERSION = f"kg {VERSION}"


def metadata() -> dict[str, str]:
    return {"version": VERSION, "cli_version": EXPECTED_CLI_VERSION}
