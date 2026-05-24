from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import warnings

from tfis.domain.enums import MonthlyStatus
from tfis.domain.strategy_rule import StrategyRule
from tfis.importers import load_strategy_rule


@dataclass(frozen=True, slots=True)
class BranchSelectionIssue:
    path: Path
    reason: str


@dataclass(frozen=True, slots=True)
class BranchSelectionResult:
    requested_status: str
    normalized_status: MonthlyStatus | None
    selected_rules: tuple[StrategyRule, ...]
    issues: tuple[BranchSelectionIssue, ...]


class StrategyBranchSelector:
    """Select folder-based strategies eligible for the current monthly status.

    This selector is intentionally simple:

    - it does not calculate monthly status
    - it does not mutate or normalize strategy files
    - it only filters already-configured folder strategies
    - it ignores legacy single-file YAML paths
    """

    def __init__(self, *, strict: bool = False) -> None:
        self.strict = strict
        self.last_result = BranchSelectionResult(
            requested_status="",
            normalized_status=None,
            selected_rules=(),
            issues=(),
        )

    def select(
        self,
        strategy_paths: Iterable[str | Path],
        current_status: MonthlyStatus | str,
    ) -> list[StrategyRule]:
        requested_status = (
            current_status.value
            if isinstance(current_status, MonthlyStatus)
            else str(current_status)
        )
        normalized_status = self._normalize_status(current_status)
        selected: list[StrategyRule] = []
        issues: list[BranchSelectionIssue] = []

        if normalized_status is None:
            self.last_result = BranchSelectionResult(
                requested_status=requested_status,
                normalized_status=None,
                selected_rules=(),
                issues=(),
            )
            return selected

        for strategy_path in strategy_paths:
            path = Path(strategy_path)
            path_issue = self._classify_path_issue(path)
            if path_issue is not None:
                issues.append(path_issue)
                self._handle_issue(path_issue)
                continue

            try:
                rule = load_strategy_rule(path)
            except Exception as exc:
                issue = BranchSelectionIssue(
                    path=path,
                    reason=f"failed to load strategy folder: {exc}",
                )
                issues.append(issue)
                self._handle_issue(issue)
                continue

            if normalized_status in rule.allowed_monthly_statuses:
                selected.append(rule)

        self.last_result = BranchSelectionResult(
            requested_status=requested_status,
            normalized_status=normalized_status,
            selected_rules=tuple(selected),
            issues=tuple(issues),
        )
        return selected

    def _normalize_status(
        self,
        current_status: MonthlyStatus | str,
    ) -> MonthlyStatus | None:
        if isinstance(current_status, MonthlyStatus):
            return current_status
        if isinstance(current_status, str):
            normalized = current_status.strip()
            if not normalized:
                return None
            try:
                return MonthlyStatus(normalized)
            except ValueError:
                return None
        return None

    def _classify_path_issue(self, path: Path) -> BranchSelectionIssue | None:
        if not path.exists():
            return BranchSelectionIssue(path=path, reason="path does not exist")
        if not path.is_dir():
            if path.suffix.lower() in {".yaml", ".yml"}:
                return BranchSelectionIssue(
                    path=path,
                    reason="single-file YAML strategies are not eligible for branch selection",
                )
            return BranchSelectionIssue(
                path=path,
                reason="path is not a folder-based strategy directory",
            )
        if not (path / "strategy.yaml").is_file():
            return BranchSelectionIssue(
                path=path,
                reason="missing strategy.yaml in strategy folder",
            )
        return None

    def _handle_issue(self, issue: BranchSelectionIssue) -> None:
        if self.strict:
            raise ValueError(
                f"Invalid strategy folder for branch selection: {issue.path} ({issue.reason})"
            )
        if issue.reason in {
            "single-file YAML strategies are not eligible for branch selection",
            "path is not a folder-based strategy directory",
        }:
            return
        warnings.warn(
            f"Skipping strategy path {issue.path}: {issue.reason}",
            stacklevel=3,
        )
