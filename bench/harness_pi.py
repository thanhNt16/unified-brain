"""Pi benchmark harness argv (contract-exact).

Launches with explicit Node v22.19.0 (ambient PATH Node is v20.14.0 and is
rejected before any measured run). Preserves the configured /9router haiku
model; no unverified --model/--provider flag is passed.
"""

from __future__ import annotations

import os
from pathlib import Path

NODE_V22 = "/Users/harrynguyen/.nvm/versions/node/v22.19.0/bin/node"
PI_CLI = "/Users/harrynguyen/.nvm/versions/node/v22.19.0/lib/node_modules/@earendil-works/pi-coding-agent/dist/cli.js"
COMMAND: list[str] = [NODE_V22, PI_CLI, "--print", "--mode", "json", "--provider", "9router", "--model", "haiku"]
CREDENTIAL_ENV = "PI_API_KEY"
DEFAULT_PI_DIR = Path.home() / ".pi" / "agent"

# 9router haiku is preserved via Pi config; never create/rewrite/delete it.
_PI_CONFIG_PATH = Path.home() / ".pi" / "agent" / "config.json"


def _child_node() -> str:
    for candidate in (Path(NODE_V22), Path.home() / ".nvm" / "versions" / "node" / "v22.19.0" / "bin" / "node"):
        if candidate.is_file():
            return str(candidate)
    return NODE_V22


def env() -> dict[str, str]:
    child = _child_node()
    inherited = dict(os.environ)
    inherited["PATH"] = f"{Path(child).parent!s}{os.pathsep}{inherited.get('PATH', '')}"
    if "PI_CODING_AGENT_DIR" not in inherited:
        inherited["PI_CODING_AGENT_DIR"] = str(DEFAULT_PI_DIR)
    return inherited
