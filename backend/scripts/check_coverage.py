"""Fails unless the modules that guard correctness are fully covered (07-test-plan.md section 9).

Run from backend/ after: uv run pytest --cov=twyf --cov-branch --cov-report=json"""

import json
import sys
from pathlib import Path

FULL = [
    "src/twyf/orchestration/machine.py",
    "src/twyf/orchestration/claims.py",
    "src/twyf/orchestration/arithmetic.py",
    "src/twyf/citations/check.py",
    "src/twyf/citations/locate.py",
    "src/twyf/citations/normalize.py",
]


def main() -> int:
    files = json.loads(Path("coverage.json").read_text())["files"]
    short = []
    for name in FULL:
        percent = files[name]["summary"]["percent_covered"]
        if percent < 100:
            short.append(f"{name}: {percent:.1f}%")
    for line in short:
        print(f"not fully covered: {line}")
    print("full coverage holds" if not short else "")
    return 1 if short else 0


if __name__ == "__main__":
    sys.exit(main())
