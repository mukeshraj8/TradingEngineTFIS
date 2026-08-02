from __future__ import annotations

from tfis.internal_paper.observation import build_phase5c_report_set


def main() -> int:
    for name in build_phase5c_report_set("reports/phase5c"):
        print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
