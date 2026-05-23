from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tfis.importers import load_strategy_rule


def main() -> int:
    strategy_dir = ROOT / "config" / "strategies"
    files = sorted(strategy_dir.glob("*.yaml"))

    if not files:
        print(f"FAIL no strategy config files found in {strategy_dir}")
        return 1

    failures = 0
    for file_path in files:
        try:
            load_strategy_rule(file_path)
        except Exception as exc:
            failures += 1
            print(f"FAIL {file_path.name}: {exc}")
        else:
            print(f"PASS {file_path.name}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
