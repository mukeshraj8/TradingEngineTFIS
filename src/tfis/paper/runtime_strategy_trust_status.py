from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from tfis.domain.enums import ExpiryType
from tfis.importers import load_strategy_rule
from tfis.rules import S21_LEG_RULES, validate_s21_strategy_rule_matches_matrix

from .lifecycle_supervisor_runtime import load_paper_lifecycle_supervisor_target_specs
from .runtime_input_derivation import load_paper_decision_reference_packet


@dataclass(frozen=True, slots=True)
class PaperRuntimeStrategyTrustStatus:
    strategy_code: str
    status: str
    trust_level: str
    checked_rule_count: int
    issue_count: int
    message: str


def load_paper_runtime_strategy_trust_statuses(
    targets_config_path: str | Path,
    *,
    repo_root: str | Path,
) -> tuple[PaperRuntimeStrategyTrustStatus, ...]:
    root = Path(repo_root)
    specs = load_paper_lifecycle_supervisor_target_specs(targets_config_path, repo_root=root)
    statuses: list[PaperRuntimeStrategyTrustStatus] = []
    for spec in specs:
        if spec.strategy_code.upper() == "S21":
            statuses.append(
                _load_s21_trust_status(
                    spec.config_path,
                    spec.reference_packet_path,
                    repo_root=root,
                )
            )
            continue
        statuses.append(
            PaperRuntimeStrategyTrustStatus(
                strategy_code=spec.strategy_code,
                status="PASS",
                trust_level="CONTROLLED_PAPER",
                checked_rule_count=1 if spec.strategy_path is not None else 0,
                issue_count=0,
                message=(
                    f"{spec.strategy_code} is configured for controlled paper runtime; "
                    "live-money trust remains governed by the disabled live execution gate."
                ),
            )
        )
    return tuple(statuses)


def _load_s21_trust_status(
    config_path: Path,
    reference_packet_path: Path | None,
    *,
    repo_root: Path,
) -> PaperRuntimeStrategyTrustStatus:
    issues: list[str] = []
    data = _load_yaml(config_path)
    paper = _mapping(data.get("paper"), "paper")
    market = _mapping(data.get("market"), "market")
    broker = _mapping(data.get("broker"), "broker")
    strategies = data.get("strategies")
    strategy_entry = _mapping(strategies[0], "strategies[0]") if isinstance(strategies, list) and strategies else {}

    _expect_equal(issues, "paper.strategy_code", paper.get("strategy_code"), "S21")
    _expect_equal(issues, "paper.symbol", paper.get("symbol"), "BANKNIFTY")
    _expect_equal(issues, "paper.contract_cycle", paper.get("contract_cycle"), "MONTHLY")
    _expect_equal(issues, "market.underlying_symbol", market.get("underlying_symbol"), "BANKNIFTY")
    _expect_equal(issues, "broker.provider", broker.get("provider"), "fyers")
    _expect_minimum_int(
        issues,
        "broker.option_chain_strike_count",
        broker.get("option_chain_strike_count"),
        100,
    )
    _expect_bool(issues, "paper.paper_mode_enabled", paper.get("paper_mode_enabled"), True)
    _expect_bool(issues, "paper.no_live_orders_allowed", paper.get("no_live_orders_allowed"), True)
    _expect_bool(issues, "paper.kill_switch_enabled", paper.get("kill_switch_enabled"), True)
    _expect_bool(issues, "paper.session_kill_switch_active", paper.get("session_kill_switch_active"), False)
    _expect_bool(issues, "paper.same_day_square_off_only", paper.get("same_day_square_off_only"), False)
    _expect_parseable_date(issues, "market.weekly_expiry", market.get("weekly_expiry"))

    expected_registry_ids = {f"S21_{unique_code}" for unique_code in S21_LEG_RULES}
    registry_ids = set(str(item) for item in strategy_entry.get("registry_ids", ()) or ())
    if registry_ids != expected_registry_ids:
        issues.append(
            "strategies[0].registry_ids expected "
            + ", ".join(sorted(expected_registry_ids))
            + "; got "
            + ", ".join(sorted(registry_ids))
        )

    strategy_paths = tuple(
        _resolve_repo_path(repo_root, path)
        for path in strategy_entry.get("strategy_paths", ()) or ()
    )
    checked_rules = []
    for strategy_path in strategy_paths:
        rule = load_strategy_rule(strategy_path)
        checked_rules.append(rule.unique_code)
        matrix_mismatches = validate_s21_strategy_rule_matches_matrix(rule)
        issues.extend(f"{rule.unique_code}: {mismatch}" for mismatch in matrix_mismatches)
        if rule.symbol != "BANKNIFTY":
            issues.append(f"{rule.unique_code}: symbol expected BANKNIFTY, got {rule.symbol}")
        if rule.expiry_policy.expiry_type is not ExpiryType.MONTHLY:
            issues.append(f"{rule.unique_code}: expiry_type expected MONTHLY")
        if not rule.expiry_policy.no_carry_past_expiry:
            issues.append(f"{rule.unique_code}: no_carry_past_expiry must be true")
        if not rule.carry_forward_allowed:
            issues.append(f"{rule.unique_code}: carry_forward_allowed must be true")
        _expect_param(issues, rule.unique_code, rule.parameters, "strike_step", 100.0)
        _expect_param(issues, rule.unique_code, rule.parameters, "lot_size", 35.0)
        _expect_param(issues, rule.unique_code, rule.parameters, "minimum_lots", 500.0)
        expected_minimum_oi = int(
            float(rule.parameters.get("lot_size", 0.0))
            * float(rule.parameters.get("minimum_lots", 0.0))
        )
        if rule.minimum_oi != expected_minimum_oi:
            issues.append(
                f"{rule.unique_code}: minimum_oi expected {expected_minimum_oi}, got {rule.minimum_oi}"
            )

    missing_rules = sorted(set(S21_LEG_RULES) - set(checked_rules))
    if missing_rules:
        issues.append("missing S21 rule folders: " + ", ".join(missing_rules))

    if reference_packet_path is None:
        issues.append("missing S21 decision reference packet path")
    else:
        reference_packet = load_paper_decision_reference_packet(reference_packet_path)
        if reference_packet.instrument_group.lower() != "banknifty":
            issues.append("reference packet instrument_group must be banknifty")
        if reference_packet.lots != 1:
            issues.append(f"reference packet lots expected 1, got {reference_packet.lots}")
        if reference_packet.quantity != 35:
            issues.append(
                f"reference packet quantity expected configured BankNifty lot size 35, got {reference_packet.quantity}"
            )
        if reference_packet.strategy_branch not in S21_LEG_RULES:
            issues.append(
                "reference packet strategy_branch must name a supported S21 leg, got "
                + reference_packet.strategy_branch
            )
        if reference_packet.strategy_branch not in checked_rules:
            issues.append(
                "reference packet strategy_branch must be one of the configured S21 rule folders, got "
                + reference_packet.strategy_branch
            )

    status = "PASS" if not issues else "FAIL"
    message = (
        "S21 controlled-paper trust checks passed for BankNifty monthly rule matrix, "
        "paper-only guardrails, lot/strike/OI sizing, reference packet scope, and carry-forward policy. "
        "This is not live-money approval."
        if not issues
        else "S21 controlled-paper trust checks failed: " + "; ".join(issues)
    )
    return PaperRuntimeStrategyTrustStatus(
        strategy_code="S21",
        status=status,
        trust_level="CONTROLLED_PAPER_NOT_LIVE_MONEY",
        checked_rule_count=len(checked_rules),
        issue_count=len(issues),
        message=message,
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML object: {path}")
    return data


def _resolve_repo_path(repo_root: Path, path: object) -> Path:
    candidate = Path(str(path))
    if candidate.is_absolute():
        return candidate
    return repo_root / candidate


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Expected mapping for {label}")
    return value


def _expect_equal(issues: list[str], label: str, actual: object, expected: object) -> None:
    if actual != expected:
        issues.append(f"{label} expected {expected!r}, got {actual!r}")


def _expect_bool(issues: list[str], label: str, actual: object, expected: bool) -> None:
    if actual is not expected:
        issues.append(f"{label} expected {expected}, got {actual!r}")


def _expect_minimum_int(issues: list[str], label: str, actual: object, minimum: int) -> None:
    try:
        value = int(actual)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        issues.append(f"{label} expected integer >= {minimum}, got {actual!r}")
        return
    if value < minimum:
        issues.append(f"{label} expected integer >= {minimum}, got {actual!r}")


def _expect_parseable_date(issues: list[str], label: str, actual: object) -> None:
    if not actual:
        issues.append(f"{label} must be configured for the current contract expiry")
        return
    try:
        date.fromisoformat(str(actual))
    except ValueError:
        issues.append(f"{label} must be an ISO date, got {actual!r}")


def _expect_param(
    issues: list[str],
    unique_code: str,
    parameters: dict[str, float],
    name: str,
    expected: float,
) -> None:
    actual = parameters.get(name)
    if actual != expected:
        issues.append(f"{unique_code}: PARAM({name}) expected {expected}, got {actual}")


__all__ = [
    "PaperRuntimeStrategyTrustStatus",
    "load_paper_runtime_strategy_trust_statuses",
]
