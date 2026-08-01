from __future__ import annotations

from pathlib import Path

from tfis.internal_paper.end_to_end import write_phase5a_pre_reports


def build_phase5a_pre_report_set(report_dir: Path | str = "reports/phase5a_pre") -> list[str]:
    return write_phase5a_pre_reports(report_dir)
