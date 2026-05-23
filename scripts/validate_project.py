from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src" / "tfis"
CONFIG_FILES = [
    ROOT / "config" / "config.yaml",
    ROOT / "config" / "config.dev.yaml",
]


def main() -> int:
    failures: list[str] = []

    if not SRC_DIR.exists():
        failures.append(f"Missing source package directory: {SRC_DIR}")

    for config_path in CONFIG_FILES:
        if not config_path.exists():
            failures.append(f"Missing config file: {config_path}")

    import_env = os.environ.copy()
    import_env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-c", "import tfis"],
        cwd=str(ROOT),
        env=import_env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        failures.append(
            "Import check failed for tfis: "
            + (result.stderr.strip() or result.stdout.strip() or "unknown error")
        )

    if failures:
        print("PROJECT VALIDATION FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("PROJECT VALIDATION PASSED")
    print(f"- Source package present: {SRC_DIR}")
    for config_path in CONFIG_FILES:
        print(f"- Config present: {config_path}")
    print("- Import check passed: tfis")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
