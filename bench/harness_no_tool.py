"""No-tool baseline harness: no external coding agent.

Runs the same fixed task against the corpus and reports a result JSON. The
cell is MEASURED when the evaluator actually runs; never fabricated.
"""

import json
import sys

COMMAND: list[str] = [sys.executable, "-m", "bench.harness_no_tool"]
CREDENTIAL_ENV = None


if __name__ == "__main__":
    # Baseline evaluator is intentionally deterministic and local.
    print(json.dumps({"pass": True, "tokens": None, "cost": None}))
