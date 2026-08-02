from __future__ import annotations

import re
from pathlib import Path

from tfis.adapters.phase5d import build_s21_first_branch_certification


GENERIC_ROOTS = (
    Path("src/tfis/monthly_status"),
    Path("src/tfis/execution_intent"),
    Path("src/tfis/internal_paper"),
    Path("src/tfis/internal_position"),
    Path("src/tfis/accounting"),
    Path("src/tfis/domain"),
)


def test_s21_does_not_add_strategy_branching_to_generic_platform() -> None:
    forbidden = re.compile(r"\b(strategy|strategy_code|strategy_id)\s*={0,2}\s*[\"']S21|if\s+.*S21")
    offenders: list[str] = []
    for root in GENERIC_ROOTS:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if forbidden.search(text):
                offenders.append(str(path))
    assert offenders == []


def test_reuse_report_declares_no_generic_runtime_changes() -> None:
    report = build_s21_first_branch_certification()["s21_platform_reuse_report"]
    assert report["generic_files_changed"] == ()
    assert report["runtime_generic_change_count"] == 0
    assert report["architecture_boundary_verdict"] == "PASS"
    assert all(row["reuse"] is True for row in report["capability_reuse_gate"])
