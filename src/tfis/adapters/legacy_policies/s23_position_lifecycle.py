from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from tfis.adapters.legacy_policies import s23_premarket_plan as premarket
from tfis.adapters.legacy_policies import s23_trading_day_coordination as coordination
from tfis.adapters.legacy_policies import s23_vertical_slice as vertical
from tfis.domain.position_lifecycle import (
    CarriedContractOpeningQuote,
    LifecycleOpeningEvidence,
    LifecycleProtectionState,
    LifecycleQuoteFreshness,
    OfflineLifecycleHandoff,
    PositionLifecycleContext,
    PositionReconciliationStatus,
    ProtectiveOrderVisibilityStatus,
    ReconciledPositionSnapshot,
    build_offline_lifecycle_handoff,
)
from tfis.domain.carried_position_day import CarriedPositionEodOutcome, OfflineCarriedPositionEodDecision, OfflineCarriedPositionTradingDay
from tfis.lifecycle import (
    OfflineCarriedPositionTradingDayCoordinator,
    OfflineCarriedPositionTradingDayInput,
    PositionLifecycleBuildInput,
    PositionLifecycleContextBuilder,
)


@dataclass(frozen=True, slots=True)
class S23LifecycleFixture:
    fixture_id: str
    context: PositionLifecycleContext
    handoff: OfflineLifecycleHandoff
    trading_day_coordination_hash: str
    observed_requirements: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "fixture_id": self.fixture_id,
            "context": self.context.to_dict(),
            "handoff": self.handoff.to_dict(),
            "trading_day_coordination_hash": self.trading_day_coordination_hash,
            "observed_requirements": list(self.observed_requirements),
        }


@dataclass(frozen=True, slots=True)
class S23EodCarryDecision:
    decision: str
    rule_id: str
    source_cells: tuple[str, ...]
    evidence: dict


@dataclass(frozen=True, slots=True)
class S23RevisedFslFormulaResult:
    status: str
    rule_id: str
    source_cell: str
    branch: str
    option_side: str
    rc_reference: str
    buffer_pct: float
    revised_fsl: float | None
    evidence: dict


@dataclass(frozen=True, slots=True)
class S23CarriedTradingDayFixture:
    fixture_id: str
    lifecycle_fixture: S23LifecycleFixture
    trading_day: OfflineCarriedPositionTradingDay
    observed_requirements: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "fixture_id": self.fixture_id,
            "lifecycle_fixture": self.lifecycle_fixture.to_dict(),
            "trading_day": self.trading_day.to_dict(),
            "observed_requirements": list(self.observed_requirements),
        }


S23_EOD_CARRY_SOURCE_CELLS = {
    "CALL": ("AB6 OS!F190:J190", "AB6 OS!F191:J191"),
    "PUT": ("AB6 OS!Q190:U190", "AB6 OS!Q191:U191"),
}


S23_REVISED_FSL_SOURCE_RULES = {
    ("BULL", "CALL"): {
        "rule_id": "S23-CARRIED-CALL-MISSED-BULL-AB6OS-184",
        "source_cell": "AB6 OS!M184",
        "rc_reference": "09:29:59 AM HH",
        "buffer_pct": 7.0,
        "display_formula": "09:29:59 AM HH + 7.00%",
    },
    ("BEAR", "CALL"): {
        "rule_id": "S23-CARRIED-CALL-MISSED-BEAR-AB6OS-185",
        "source_cell": "AB6 OS!M185",
        "rc_reference": "09:29:59 AM HH",
        "buffer_pct": 10.0,
        "display_formula": "09:29:59 AM HH + 10.00%",
    },
    ("BULL", "PUT"): {
        "rule_id": "S23-CARRIED-PUT-MISSED-BULL-AB6OS-187",
        "source_cell": "AB6 OS!M187",
        "rc_reference": "09:29:59 AM HH",
        "buffer_pct": 10.0,
        "display_formula": "09:29:59 AM HH + 10.00%",
    },
    ("BEAR", "PUT"): {
        "rule_id": "S23-CARRIED-PUT-MISSED-BEAR-AB6OS-188",
        "source_cell": "AB6 OS!M188",
        "rc_reference": "09:29:59 AM HH",
        "buffer_pct": 7.0,
        "display_formula": "09:29:59 AM HH + 7.00%",
    },
}


def evaluate_s23_eod_carry_decision(*, option_close: float, original_sl: float, option_side: str) -> S23EodCarryDecision:
    side = option_side.upper()
    if side not in S23_EOD_CARRY_SOURCE_CELLS:
        raise ValueError(f"unsupported S23 option side for EOD carry decision: {option_side!r}")

    source_cells = S23_EOD_CARRY_SOURCE_CELLS[side]
    evidence = {
        "source_authority": "TFISRulesAndSpec/All in One - TFIS 26-12-2023.xlsx",
        "source_cells": source_cells,
        "square_off_rule": "15:00 close > original SL",
        "carry_forward_rule": "15:00 close <= original SL",
        "workbook_carry_forward_rule": "15:00 close < original SL",
        "equality_rule": "USER_CLARIFIED_AND_RECORDED: 15:00 close == original SL carries forward",
    }
    if option_close > original_sl:
        return S23EodCarryDecision("SQUARE_OFF_AT_CMP_REQUIRED", "S23-EOD-CARRY-AB6OS-190", source_cells, evidence)
    return S23EodCarryDecision("CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL", "S23-EOD-CARRY-AB6OS-191-USER-EQUALITY", source_cells, evidence)


def calculate_s23_carried_revised_fsl(*, branch: str, option_side: str, rc_option_high: float) -> S23RevisedFslFormulaResult:
    key = (branch.upper(), option_side.upper())
    rule = S23_REVISED_FSL_SOURCE_RULES.get(key)
    if rule is None:
        raise ValueError(f"unsupported S23 revised FSL rule: branch={branch!r} option_side={option_side!r}")

    evidence = {
        "source_authority": "TFISRulesAndSpec/All in One - TFIS 26-12-2023.xlsx",
        "display_formula": rule["display_formula"],
        "formula_type": "workbook_display_formula_only",
        "non_positive_handling": "RULE_AUTHORITY_UNRESOLVED_FOR_INVALID_MARKET_INPUT",
    }
    if rc_option_high <= 0:
        return S23RevisedFslFormulaResult(
            status="RULE_AUTHORITY_UNRESOLVED",
            rule_id=rule["rule_id"],
            source_cell=rule["source_cell"],
            branch=key[0],
            option_side=key[1],
            rc_reference=rule["rc_reference"],
            buffer_pct=rule["buffer_pct"],
            revised_fsl=None,
            evidence=evidence,
        )

    revised_fsl = rc_option_high * (1.0 + (rule["buffer_pct"] / 100.0))
    return S23RevisedFslFormulaResult(
        status="WORKBOOK_FORMULA_APPLIED",
        rule_id=rule["rule_id"],
        source_cell=rule["source_cell"],
        branch=key[0],
        option_side=key[1],
        rc_reference=rule["rc_reference"],
        buffer_pct=rule["buffer_pct"],
        revised_fsl=revised_fsl,
        evidence=evidence,
    )


def build_s23_bull_carried_normal_day_carry() -> S23CarriedTradingDayFixture:
    return _carried_day_fixture("bull_carried_normal_day_carry", build_s23_bull_carried_normal_lifecycle(), option_close=250.0, original_sl=300.0)


def build_s23_bull_carried_normal_day_equal_carry() -> S23CarriedTradingDayFixture:
    return _carried_day_fixture("bull_carried_normal_day_equal_carry", build_s23_bull_carried_normal_lifecycle(), option_close=300.0, original_sl=300.0)


def build_s23_bull_carried_normal_day_square_off() -> S23CarriedTradingDayFixture:
    return _carried_day_fixture("bull_carried_normal_day_square_off", build_s23_bull_carried_normal_lifecycle(), option_close=350.0, original_sl=300.0)


def build_s23_bull_carried_adverse_day_revised_fsl_carry() -> S23CarriedTradingDayFixture:
    return _carried_day_fixture("bull_carried_adverse_day_revised_fsl_carry", build_s23_bull_carried_adverse_gap_lifecycle(), option_close=250.0, original_sl=300.0)


def build_s23_bull_carried_target_exit_day() -> S23CarriedTradingDayFixture:
    return _carried_day_fixture("bull_carried_target_exit_day", build_s23_bull_carried_target_crossed_lifecycle(), option_close=None, original_sl=None)


def build_s23_bull_carried_normal_lifecycle() -> S23LifecycleFixture:
    return _fixture("bull_carried_normal", "bull", price=203.5, prior_reference=203.5, orpt_high=300.0)


def build_s23_bull_carried_adverse_gap_lifecycle() -> S23LifecycleFixture:
    return _fixture("bull_carried_adverse_gap", "bull", price=260.0, prior_reference=203.5, orpt_high=330.0, rc_high=335.0)


def build_s23_bull_carried_favorable_gap_lifecycle() -> S23LifecycleFixture:
    return _fixture("bull_carried_favorable_gap", "bull", price=150.0, prior_reference=203.5, orpt_high=300.0)


def build_s23_bull_carried_target_crossed_lifecycle() -> S23LifecycleFixture:
    return _fixture("bull_carried_target_crossed", "bull", price=75.0, prior_reference=203.5, orpt_high=330.0, rc_high=335.0)


def build_s23_bull_carried_protection_crossed_lifecycle() -> S23LifecycleFixture:
    return _fixture("bull_carried_protection_crossed", "bull", price=330.0, prior_reference=203.5, orpt_high=330.0, rc_high=335.0)


def build_s23_bear_carried_normal_lifecycle() -> S23LifecycleFixture:
    return _fixture("bear_carried_normal", "bear", price=194.25, prior_reference=194.25, orpt_high=300.0)


def build_s23_bear_carried_adverse_gap_lifecycle() -> S23LifecycleFixture:
    return _fixture("bear_carried_adverse_gap", "bear", price=250.0, prior_reference=194.25, orpt_high=320.0, rc_high=325.0)


def build_s23_missing_quote_lifecycle() -> S23LifecycleFixture:
    return _fixture("missing_carried_contract_quote", "bull", price=None, prior_reference=203.5, quote_available=False)


def build_s23_reconciliation_mismatch_lifecycle() -> S23LifecycleFixture:
    return _fixture("reconciliation_mismatch", "bull", price=203.5, prior_reference=203.5, reconciliation_status=PositionReconciliationStatus.MISMATCH, external_quantity=25)


def build_s23_stale_quote_lifecycle() -> S23LifecycleFixture:
    return _fixture("stale_carried_contract_quote", "bull", price=203.5, prior_reference=203.5, freshness=LifecycleQuoteFreshness.STALE)


def build_s23_missing_rc_lifecycle() -> S23LifecycleFixture:
    return _fixture("missing_rc_observation", "bull", price=260.0, prior_reference=203.5, orpt_high=330.0, rc_high=None, rc_available=False)


def _fixture(
    fixture_id: str,
    branch: str,
    *,
    price: float | None,
    prior_reference: float | None,
    quote_available: bool = True,
    freshness: LifecycleQuoteFreshness = LifecycleQuoteFreshness.FRESH,
    reconciliation_status: PositionReconciliationStatus = PositionReconciliationStatus.MATCHED,
    external_quantity: int | None = None,
    orpt_high: float | None = None,
    rc_high: float | None = None,
    rc_available: bool = True,
) -> S23LifecycleFixture:
    case = vertical.build_s23_bull_call_vertical_case() if branch == "bull" else vertical.build_s23_bear_call_vertical_case()
    plan = premarket.build_s23_bull_call_premarket_plan() if branch == "bull" else premarket.build_s23_bear_call_premarket_plan()
    trading_day = plan.trading_date
    position = _position_snapshot(fixture_id, case, plan, reconciliation_status, external_quantity)
    protection = _protection_state(plan, branch)
    opening = _opening_evidence(fixture_id, plan, price, prior_reference, quote_available, freshness, orpt_high=orpt_high, rc_high=rc_high, rc_available=rc_available)
    context = PositionLifecycleContextBuilder().build(
        PositionLifecycleBuildInput(
            context_id=f"m13-s23-{fixture_id}",
            trading_date=trading_day,
            strategy_family=case.runtime_input.strategy_family_id or "S23",
            strategy_definition=case.runtime_input.strategy_definition_id or case.strategy_rule.unique_code,
            strategy_version=getattr(case.runtime_input, "strategy_version", None) or "1.0.0",
            strategy_instance_id=case.runtime_input.strategy_instance_id or "S23_NIFTY_ACCOUNT_A_PAPER",
            configuration_hash=case.runtime_input.resolved_configuration_hash or "UNKNOWN",
            position_snapshot=position,
            protection_state=protection,
            opening_evidence=opening,
            policy_identities=dict(plan.planned_values.policy_identities) | {
                "position_lifecycle_context": "phase3d.generic.position_lifecycle_context_builder.v1",
                "s23_lifecycle_adapter": "phase3d.s23.call.carried_position_adapter.v1",
            },
        )
    )
    handoff = build_offline_lifecycle_handoff(context, f"m13-s23-{fixture_id}:handoff")
    carried = coordination.build_s23_carried_position_trading_day()
    return S23LifecycleFixture(fixture_id, context, handoff, carried.coordination_hash, _observed_requirements())


def _carried_day_fixture(
    fixture_id: str,
    lifecycle_fixture: S23LifecycleFixture,
    *,
    option_close: float | None,
    original_sl: float | None,
) -> S23CarriedTradingDayFixture:
    context = lifecycle_fixture.context

    def eod_factory(_context) -> OfflineCarriedPositionEodDecision:
        assert option_close is not None
        assert original_sl is not None
        side = "CALL"
        decision = evaluate_s23_eod_carry_decision(option_close=option_close, original_sl=original_sl, option_side=side)
        outcome = CarriedPositionEodOutcome(decision.decision)
        return OfflineCarriedPositionEodDecision(
            decision_id=f"m14-s23-{fixture_id}:eod-15-00",
            trading_date=context.trading_date,
            strategy_instance_id=context.strategy_instance_id,
            position_cycle_id=context.position_snapshot.position_cycle_id if context.position_snapshot else None,
            observed_price=option_close,
            original_sl=original_sl,
            option_side=side,
            comparison_time="15:00:00",
            source_rule_id=decision.rule_id,
            source_cells=decision.source_cells,
            workbook_square_off_operator=">",
            workbook_carry_forward_operator="<",
            effective_carry_forward_operator="<=",
            equality_outcome=CarriedPositionEodOutcome.CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL,
            square_off_outcome=CarriedPositionEodOutcome.SQUARE_OFF_AT_CMP_REQUIRED,
            carry_forward_outcome=CarriedPositionEodOutcome.CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL,
            outcome=outcome,
            evidence=decision.evidence
            | {
                "source_rule_id": decision.rule_id,
                "m14_scope": "offline_carried_position_trading_day",
                "broker_authority": "NONE",
                "paper_authority": "NONE",
                "live_authority": "NONE",
            },
        )

    day = OfflineCarriedPositionTradingDayCoordinator().coordinate(
        OfflineCarriedPositionTradingDayInput(
            day_id=f"m14-s23-{fixture_id}",
            lifecycle_context=context,
            eod_decision_factory=None if option_close is None else eod_factory,
        )
    )
    return S23CarriedTradingDayFixture(fixture_id, lifecycle_fixture, day, _observed_requirements())


def _position_snapshot(
    fixture_id: str,
    case: vertical.S23VerticalSliceCase,
    plan,
    reconciliation_status: PositionReconciliationStatus,
    external_quantity: int | None,
) -> ReconciledPositionSnapshot:
    quantity = int(plan.planned_values.quantity or 0)
    external = quantity if external_quantity is None else external_quantity
    return ReconciledPositionSnapshot(
        reconciliation_id=f"m13-s23-{fixture_id}:reconciliation",
        trading_date=plan.trading_date,
        strategy_family=case.runtime_input.strategy_family_id or "S23",
        strategy_definition=case.runtime_input.strategy_definition_id or case.strategy_rule.unique_code,
        strategy_version=getattr(case.runtime_input, "strategy_version", None) or "1.0.0",
        strategy_instance_id=case.runtime_input.strategy_instance_id or "S23_NIFTY_ACCOUNT_A_PAPER",
        configuration_hash=case.runtime_input.resolved_configuration_hash or "UNKNOWN",
        position_cycle_id=f"{case.runtime_input.strategy_instance_id}:CARRY:{plan.contract_resolution.selected_contract.symbol}",
        account_reference="ACCOUNT_A_PAPER_LOGICAL",
        contract=plan.contract_resolution.selected_contract,
        product=plan.product,
        side=plan.planned_values.order_side,
        opened_at=datetime.combine(plan.trading_date, plan.planned_values.normal_orpt, tzinfo=ZoneInfo("Asia/Kolkata")),
        entry_price=float(plan.planned_values.base_entry),
        local_quantity=quantity,
        external_quantity=external,
        reconciled_quantity=quantity if reconciliation_status is PositionReconciliationStatus.MATCHED else min(quantity, external),
        reconciliation_status=reconciliation_status,
        evidence={
            "source": "phase3d_m13_s23_fixture",
            "fresh_entry_isolation": "carried snapshot is constructed independently from fresh-entry plan execution",
        },
    )


def _protection_state(plan, branch: str) -> LifecycleProtectionState:
    formula_rule = S23_REVISED_FSL_SOURCE_RULES[(branch.upper(), "CALL")]
    return LifecycleProtectionState(
        target_levels={"target_1": float(plan.planned_values.preliminary_target)},
        protective_levels={"msl": float(plan.planned_values.preliminary_msl)},
        protective_order_status=ProtectiveOrderVisibilityStatus.MATCHED,
        lifecycle_recalculation_time=plan.planned_values.rc_time,
        revised_protective_formula_policy_id=formula_rule["rule_id"],
        protective_order_identities={
            "target_1": f"offline-target:{plan.contract_resolution.selected_contract.symbol}:target_1",
            "msl": f"offline-protective:{plan.contract_resolution.selected_contract.symbol}:msl",
        },
        provenance={
            "target": "Target protection is available from market open through approved offline terminal/broker target evidence.",
            "msl": "Prior-day SL is not blindly reused; adverse carried-position gaps require revised SL calculation at configured lifecycle recalculation time.",
            "revised_sl_formula": f"{formula_rule['source_cell']} {formula_rule['display_formula']}",
        },
    )


def _opening_evidence(
    fixture_id: str,
    plan,
    price: float | None,
    prior_reference: float | None,
    quote_available: bool,
    freshness: LifecycleQuoteFreshness,
    *,
    orpt_high: float | None,
    rc_high: float | None,
    rc_available: bool,
) -> LifecycleOpeningEvidence:
    ts = datetime.combine(plan.trading_date, plan.planned_values.normal_orpt, tzinfo=ZoneInfo("Asia/Kolkata"))
    quote = None
    if quote_available:
        quote = CarriedContractOpeningQuote(
            contract=plan.contract_resolution.selected_contract,
            source_timestamp=ts,
            ltp=price,
            high=price,
            low=price,
            bid=price - 0.5 if price is not None else None,
            ask=price + 0.5 if price is not None else None,
            oi=float(plan.contract_resolution.selected_contract.metadata.get("oi", 0.0)),
            prior_reference_price=prior_reference,
            freshness=freshness,
            provenance={
                "source": "phase3d_m13_s23_carried_contract_opening_quote_fixture",
                "independent_carried_contract_quote": "true",
            },
        )
    orpt_quote = None
    if quote_available and orpt_high is not None:
        orpt_quote = CarriedContractOpeningQuote(
            contract=plan.contract_resolution.selected_contract,
            source_timestamp=ts,
            ltp=orpt_high,
            high=orpt_high,
            low=min(orpt_high, price) if price is not None else None,
            prior_reference_price=prior_reference,
            freshness=freshness,
            provenance={"source": "AB6_OS_183_188_ORPT_ORIGINAL_SL_COMPARISON_FIXTURE"},
        )
    rc_quote = None
    if quote_available and rc_available and rc_high is not None:
        rc_quote = CarriedContractOpeningQuote(
            contract=plan.contract_resolution.selected_contract,
            source_timestamp=datetime.combine(plan.trading_date, plan.planned_values.rc_time, tzinfo=ZoneInfo("Asia/Kolkata")),
            ltp=rc_high,
            high=rc_high,
            low=min(rc_high, price) if price is not None else None,
            prior_reference_price=prior_reference,
            freshness=freshness,
            provenance={"source": "AB6_OS_184_185_187_188_RC_REVISED_FSL_FIXTURE"},
        )
    return LifecycleOpeningEvidence(
        evidence_id=f"m13-s23-{fixture_id}:opening-evidence",
        trading_date=plan.trading_date,
        underlying_opening_snapshot={"instrument": "NSE:NIFTY", "timestamp": ts, "shared_with_opening_context": True},
        carried_contract_quote=quote,
        observation_timestamp=ts,
        max_quote_age_seconds=300,
        orpt_contract_observation=orpt_quote,
        rc_contract_observation=rc_quote,
        shared_underlying_snapshot_permitted=True,
        provenance={"source": "phase3d_m13_s23_lifecycle_fixture"},
    )


def _observed_requirements() -> tuple[str, ...]:
    return (
        "near-expiry to next-expiry fallback: recorded from S23 source rules, not genericized in lifecycle",
        "directional strike traversal: recorded from S23 source rules, not genericized in lifecycle",
        "ideal-premium and minimum-premium phases: recorded from S23 source rules, not genericized in lifecycle",
        "configurable OI thresholds: recorded from S23 source rules, not genericized in lifecycle",
        "MIN/MAX bounded Target or MSL formulas: recorded from S23 source rules, not genericized in lifecycle",
        "non-positive calculated risk prices: S23 option-selling formulas remain positive for valid positive premiums; invalid market inputs remain fail-closed",
        "additional historical reference lookbacks: recorded from S23 source rules, not genericized in lifecycle",
        "carried-position target crossed at open: authoritative EXIT_REQUIRED recorded offline",
        "carried-position adverse premium gap: authoritative revised SL placement requirement recorded offline after configured recalculation time",
        "fresh-entry Gap/Missed-Entry and carried-position SL recalculation: kept separate",
    )
