"""No-tool baseline harness: no external coding agent.

Independent local evaluator: runs `kg --version` and reports pass iff it is
exactly `kg 1.0.0`. The cell is MEASURED when the evaluator runs; never
fabricated. The prompt argument is accepted but ignored (baseline = no LLM).
"""

import json
import subprocess
import sys

COMMAND: list[str] = [sys.executable, "-m", "bench.harness_no_tool"]
CREDENTIAL_ENV = None


def _evaluate() -> dict[str, object]:
    try:
        proc = subprocess.run(
            ["kg", "--version"], shell=False, capture_output=True, text=True, timeout=30, check=False
        )
        passed = proc.returncode == 0 and proc.stdout.strip() == "kg 1.0.0"
        return {"pass": passed, "tokens": None, "cost": None}
    except (OSError, subprocess.SubprocessError):
        return {"pass": False, "tokens": None, "cost": None}


if __name__ == "__main__":
    print(json.dumps(_evaluate()))

