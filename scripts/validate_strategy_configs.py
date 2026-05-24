from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tfis.importers import (
    discover_strategy_sources,
    get_strategy_status,
    validate_folder_strategy_detailed,
    validate_folder_strategy,
    validate_legacy_strategy,
)


def main() -> int:
    strategy_dir = ROOT / "config" / "strategies"
    legacy_files, folder_files = discover_strategy_sources(strategy_dir)
    sources = legacy_files + folder_files

    if not sources:
        print(f"FAIL no strategy config files found in {strategy_dir}")
        return 1

    failures = 0
    for file_path in legacy_files:
        ok, message = validate_legacy_strategy(file_path)
        if not ok:
            failures += 1
            print(f"FAIL {file_path.relative_to(ROOT)}: {message}")
        else:
            print(f"LEGACY PASS {file_path.relative_to(ROOT)}")

    for file_path in folder_files:
        ok, message, findings = validate_folder_strategy_detailed(file_path)
        warnings = [finding for finding in findings if finding.severity == "WARN"]
        if not ok:
            failures += 1
            print(f"FAIL {file_path.relative_to(ROOT)}: {message}")
        else:
            print(f"PASS {file_path.relative_to(ROOT)}")
            status = get_strategy_status(file_path.parent.name)
            if status is None:
                print(f"WARN {file_path.relative_to(ROOT)} missing registry entry")
            else:
                print(f"STATUS {file_path.relative_to(ROOT)} {status}")
            for finding in warnings:
                print(
                    f"WARN {file_path.relative_to(ROOT)} {finding.field_name}: "
                    f"{finding.message}"
                )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
