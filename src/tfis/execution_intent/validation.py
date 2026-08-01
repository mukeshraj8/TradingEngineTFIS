from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .models import (
    ExecutionAuthorityMode,
    ExecutionIntentPurpose,
    IntentValidationDecision,
    RiskCheckResult,
    RiskCheckStatus,
    RiskEvidence,
    RiskFailure,
    RiskSeverity,
    RiskValidationInput,
    RiskValidationResult,
    RiskWarning,
)
from tfis.persistence import canonical_hash


ALLOWED_ENTRY_RECONCILIATION_GATES = frozenset(
    {"SHADOW_READY", "READ_ONLY_READY", "NEW_ENTRY_ELIGIBLE_AFTER_FUTURE_APPROVAL"}
)
BLOCKED_ENTRY_RECONCILIATION_GATES = frozenset(
    {"NEW_ENTRY_BLOCKED", "ACCOUNT_BLOCKED", "MANUAL_REVIEW_REQUIRED", "RECOVERY_BLOCKED"}
)
ALLOWED_RECOVERY_STATUSES = frozenset({"RECOVERABLE_OFFLINE", "RECONCILIATION_REQUIRED"})
BLOCKED_RECOVERY_STATUSES = frozenset(
    {
        "CONFIGURATION_MISMATCH",
        "RULE_VERSION_MISMATCH",
        "CORRUPTED_STATE",
        "UNSUPPORTED_SCHEMA",
        "BLOCKED",
        "PARTIAL_RECOVERY",
    }
)
LIFECYCLE_PURPOSES = frozenset(
    {
        ExecutionIntentPurpose.TARGET,
        ExecutionIntentPurpose.ORIGINAL_SL,
        ExecutionIntentPurpose.REVISED_SL,
        ExecutionIntentPurpose.EOD_EXIT,
        ExecutionIntentPurpose.RISK_EXIT,
        ExecutionIntentPurpose.OPERATOR_EXIT,
    }
)


class ExecutionIntentValidator:
    def validate(self, request: RiskValidationInput) -> RiskValidationResult:
        checks: list[RiskCheckResult] = []
        failures: list[RiskFailure] = []
        warnings: list[RiskWarning] = []

        def add(
            check_id: str,
            scope: str,
            status: RiskCheckStatus,
            reason: str,
            *,
            threshold: Mapping[str, Any] | None = None,
            observed: Mapping[str, Any] | None = None,
            source: str = "phase4e.validator",
            severity: RiskSeverity | None = None,
        ) -> None:
            evidence = RiskEvidence(
                evidence_id=f"{request.validation_id}:{check_id}",
                evidence_hash=canonical_hash(
                    {
                        "check_id": check_id,
                        "scope": scope,
                        "status": status.value,
                        "reason": reason,
                        "observed": observed or {},
                        "threshold": threshold or {},
                    }
                ),
                source=source,
                details={"reason": reason},
            )
            resolved_severity = severity or _severity(status)
            checks.append(
                RiskCheckResult(
                    check_id=check_id,
                    scope=scope,
                    input={"execution_intent_id": request.intent.execution_intent_id, "purpose": request.intent.action.purpose.value},
                    threshold_config=threshold or {},
                    observed_value=observed or {},
                    result=status,
                    severity=resolved_severity,
                    source=source,
                    evidence=evidence,
                )
            )
            if status in {RiskCheckStatus.REJECT, RiskCheckStatus.BLOCK, RiskCheckStatus.INSUFFICIENT_EVIDENCE, RiskCheckStatus.DUPLICATE, RiskCheckStatus.EXPIRED}:
                failures.append(RiskFailure(code=check_id, reason=reason, check_id=check_id, evidence_hash=evidence.evidence_hash))
            elif status is RiskCheckStatus.WARNING:
                warnings.append(RiskWarning(code=check_id, reason=reason, check_id=check_id, evidence_hash=evidence.evidence_hash))

        intent = request.intent
        action = intent.action
        instrument = intent.instrument
        account = request.account
        strategy = request.strategy
        portfolio = request.portfolio
        market = request.market_data
        position = request.position

        add(
            "AUTHORITY_MODE_OFFLINE_ONLY",
            "SYSTEM_AUTHORITY",
            RiskCheckStatus.PASS
            if intent.evidence.authority_mode in {ExecutionAuthorityMode.OFFLINE_ONLY, ExecutionAuthorityMode.SHADOW_ONLY, ExecutionAuthorityMode.VALIDATED_NOT_SUBMITTABLE}
            else RiskCheckStatus.REJECT,
            "Intent authority mode is limited to offline/shadow/non-submittable.",
            threshold={"allowed": ["OFFLINE_ONLY", "SHADOW_ONLY", "VALIDATED_NOT_SUBMITTABLE"]},
            observed={"authority_mode": intent.evidence.authority_mode.value},
        )
        if any(
            (
                intent.broker_submission_permitted,
                intent.paper_submission_permitted,
                intent.live_submission_permitted,
                intent.order_creation_permitted,
                intent.position_mutation_permitted,
            )
        ):
            add("AUTHORITY_FLAGS_FALSE", "SYSTEM_AUTHORITY", RiskCheckStatus.REJECT, "Execution authority flags must remain false.")
        else:
            add("AUTHORITY_FLAGS_FALSE", "SYSTEM_AUTHORITY", RiskCheckStatus.PASS, "No broker, paper, live, order, or position authority granted.")

        if request.recovery_status in BLOCKED_RECOVERY_STATUSES:
            add("RECOVERY_READY", "RECOVERY", RiskCheckStatus.BLOCK, "Recovery status blocks intent validation.", observed={"recovery_status": request.recovery_status})
        elif request.recovery_status == "RECONCILIATION_REQUIRED" and not request.reconciliation_gate:
            add("RECOVERY_READY", "RECOVERY", RiskCheckStatus.BLOCK, "Recovery requires reconciliation evidence before validation.")
        elif request.recovery_status in ALLOWED_RECOVERY_STATUSES:
            add("RECOVERY_READY", "RECOVERY", RiskCheckStatus.PASS, "Recovery status is acceptable for offline validation.", observed={"recovery_status": request.recovery_status})
        else:
            add("RECOVERY_READY", "RECOVERY", RiskCheckStatus.INSUFFICIENT_EVIDENCE, "Recovery status is not recognized as acceptable.", observed={"recovery_status": request.recovery_status})

        if action.purpose is ExecutionIntentPurpose.ENTRY:
            if request.reconciliation_gate in ALLOWED_ENTRY_RECONCILIATION_GATES:
                rec_status = RiskCheckStatus.PASS
                rec_reason = "Reconciliation gate permits offline validation for a fresh entry."
            elif request.reconciliation_gate in BLOCKED_ENTRY_RECONCILIATION_GATES:
                rec_status = RiskCheckStatus.BLOCK
                rec_reason = "Reconciliation gate blocks fresh entry validation."
            else:
                rec_status = RiskCheckStatus.BLOCK
                rec_reason = "Fresh entry requires acceptable reconciliation evidence."
        else:
            if request.reconciliation_gate in {"SHADOW_READY", "READ_ONLY_READY", "LIFECYCLE_ONLY", "NEW_ENTRY_BLOCKED"} and not _has_blocking_position_truth(request):
                rec_status = RiskCheckStatus.PASS
                rec_reason = "Lifecycle protection may validate when position linkage and quantity are reconciled."
            else:
                rec_status = RiskCheckStatus.BLOCK
                rec_reason = "Lifecycle protection requires unambiguous position reconciliation."
        add(
            "RECONCILIATION_GATE",
            "RECONCILIATION",
            rec_status,
            rec_reason,
            observed={"gate": request.reconciliation_gate, "blocking_classifications": list(request.reconciliation_blocking_classifications)},
        )

        add("ACCOUNT_ENABLED", "ACCOUNT", RiskCheckStatus.PASS if account.account_enabled else RiskCheckStatus.BLOCK, "Account must be enabled.")
        add(
            "ACCOUNT_ENVIRONMENT",
            "ACCOUNT",
            RiskCheckStatus.PASS if account.environment == account.required_environment else RiskCheckStatus.BLOCK,
            "Account environment must match the strategy/account configuration.",
            threshold={"required_environment": account.required_environment},
            observed={"environment": account.environment},
        )
        add("ACCOUNT_SESSION_AVAILABLE", "ACCOUNT", RiskCheckStatus.PASS if account.session_available else RiskCheckStatus.BLOCK, "Account session evidence must be available.")
        add("ACCOUNT_FUNDS_EVIDENCE", "ACCOUNT", RiskCheckStatus.PASS if account.funds_evidence_available else RiskCheckStatus.INSUFFICIENT_EVIDENCE, "Funds evidence must be available.")
        add("ACCOUNT_MARGIN_EVIDENCE", "ACCOUNT", RiskCheckStatus.PASS if account.margin_evidence_available else RiskCheckStatus.INSUFFICIENT_EVIDENCE, "Margin evidence must be available.")
        add("ACCOUNT_NOT_BLOCKED", "ACCOUNT", RiskCheckStatus.PASS if not account.account_blocked and not account.kill_switch_active else RiskCheckStatus.BLOCK, "Account block and kill switch must be inactive.")
        add(
            "ACCOUNT_CAPACITY",
            "ACCOUNT",
            RiskCheckStatus.PASS if account.active_orders < account.max_active_orders and account.active_positions <= account.max_active_positions else RiskCheckStatus.BLOCK,
            "Account active order/position limits must not be exceeded.",
            threshold={"max_active_orders": account.max_active_orders, "max_active_positions": account.max_active_positions},
            observed={"active_orders": account.active_orders, "active_positions": account.active_positions},
        )
        add("ACCOUNT_DAILY_LOSS_GATE", "ACCOUNT", RiskCheckStatus.PASS if not account.daily_loss_gate_blocked else RiskCheckStatus.BLOCK, "Account daily loss gate must not block validation.")
        add(
            "BROKER_READ_FRESHNESS",
            "ACCOUNT",
            RiskCheckStatus.PASS if account.broker_read_age_seconds <= account.max_broker_read_age_seconds else RiskCheckStatus.BLOCK,
            "Broker-read evidence must be fresh enough.",
            threshold={"max_age_seconds": account.max_broker_read_age_seconds},
            observed={"age_seconds": account.broker_read_age_seconds},
        )

        add("STRATEGY_ENABLED", "STRATEGY_INSTANCE", RiskCheckStatus.PASS if strategy.strategy_enabled else RiskCheckStatus.BLOCK, "Strategy instance must be enabled.")
        add(
            "STRATEGY_VERSION",
            "STRATEGY_INSTANCE",
            RiskCheckStatus.PASS if intent.strategy_version == strategy.expected_strategy_version else RiskCheckStatus.BLOCK,
            "Strategy version must match expected configuration.",
            threshold={"expected": strategy.expected_strategy_version},
            observed={"actual": intent.strategy_version},
        )
        add(
            "STRATEGY_CONFIGURATION_HASH",
            "STRATEGY_INSTANCE",
            RiskCheckStatus.PASS if strategy.configuration_hash == strategy.expected_configuration_hash == intent.evidence.configuration_hash else RiskCheckStatus.BLOCK,
            "Configuration hash must match source evidence.",
        )
        add(
            "RULE_MATRIX_VERSION",
            "STRATEGY_INSTANCE",
            RiskCheckStatus.PASS if strategy.rule_matrix_version == strategy.expected_rule_matrix_version == intent.evidence.rule_matrix_version else RiskCheckStatus.BLOCK,
            "Rule matrix version must match expected configuration.",
        )
        add("ACCOUNT_ASSIGNMENT", "STRATEGY_INSTANCE", RiskCheckStatus.PASS if strategy.assigned_account_id == intent.broker_account_id else RiskCheckStatus.BLOCK, "Strategy must be assigned to the target account.")
        add("ALLOWED_PRODUCT", "STRATEGY_INSTANCE", RiskCheckStatus.PASS if instrument.product in strategy.allowed_products else RiskCheckStatus.BLOCK, "Product must be allowed for strategy.")
        add("ALLOWED_UNDERLYING", "STRATEGY_INSTANCE", RiskCheckStatus.PASS if instrument.underlying in strategy.allowed_underlyings else RiskCheckStatus.BLOCK, "Underlying must be allowed for strategy.")
        add("ALLOWED_CONTRACT_TYPE", "STRATEGY_INSTANCE", RiskCheckStatus.PASS if (instrument.option_type or "NONE") in strategy.allowed_contract_types else RiskCheckStatus.BLOCK, "Contract type must be allowed for strategy.")
        add(
            "DUPLICATE_ENTRY_CYCLE",
            "STRATEGY_INSTANCE",
            RiskCheckStatus.PASS
            if action.purpose is not ExecutionIntentPurpose.ENTRY or strategy.active_fresh_entry_cycles < strategy.max_active_fresh_entry_cycles
            else RiskCheckStatus.BLOCK,
            "Only the configured number of active fresh-entry cycles is allowed.",
        )
        add("CONFIGURED_QUANTITY", "STRATEGY_INSTANCE", RiskCheckStatus.PASS if action.requested_quantity == strategy.configured_quantity or action.purpose in LIFECYCLE_PURPOSES else RiskCheckStatus.BLOCK, "Fresh-entry quantity must match configuration.")

        portfolio_blocks_entry = not portfolio.global_new_entry_enabled or portfolio.global_kill_switch or portfolio.global_daily_loss_blocked or portfolio.data_degraded_global_block
        allow_lifecycle_under_block = action.purpose in LIFECYCLE_PURPOSES and portfolio.kill_switch_action in {"BLOCK_NEW_ENTRIES", "PRESERVE_EXISTING_PROTECTION", "REDUCE_RISK"}
        if action.purpose is ExecutionIntentPurpose.ENTRY and portfolio_blocks_entry:
            portfolio_status = RiskCheckStatus.BLOCK
            portfolio_reason = "Portfolio controls block new entries."
        elif portfolio.global_kill_switch and not allow_lifecycle_under_block:
            portfolio_status = RiskCheckStatus.BLOCK
            portfolio_reason = "Portfolio kill switch blocks this purpose."
        else:
            portfolio_status = RiskCheckStatus.PASS
            portfolio_reason = "Portfolio controls permit offline validation for this purpose."
        add("PORTFOLIO_CONTROLS", "PORTFOLIO", portfolio_status, portfolio_reason, observed={"kill_switch_action": portfolio.kill_switch_action})
        add(
            "PORTFOLIO_CAPACITY",
            "PORTFOLIO",
            RiskCheckStatus.PASS if portfolio.total_active_orders <= portfolio.max_total_active_orders and portfolio.total_active_positions <= portfolio.max_total_active_positions else RiskCheckStatus.BLOCK,
            "Portfolio active order/position limits must not be exceeded.",
        )

        add("INSTRUMENT_SESSION_DATE", "INSTRUMENT_SESSION", RiskCheckStatus.PASS if intent.trading_date == market.trading_date else RiskCheckStatus.BLOCK, "Intent trading date must match market-data context.")
        add("INSTRUMENT_CONTRACT_MATCH", "INSTRUMENT_SESSION", RiskCheckStatus.PASS if intent.instrument.contract == market.contract else RiskCheckStatus.BLOCK, "Intent contract must match market-data context.")

        quantity_status = RiskCheckStatus.PASS
        quantity_reason = "Quantity is positive, integral, lot-aligned, and within limits."
        if action.requested_quantity <= 0:
            quantity_status = RiskCheckStatus.REJECT
            quantity_reason = "Quantity must be positive."
        elif action.quantity_unit not in {"LOTS", "LOT_COUNT"} and action.requested_quantity % instrument.lot_size != 0:
            quantity_status = RiskCheckStatus.REJECT
            quantity_reason = "Quantity must align with lot size."
        elif action.purpose in LIFECYCLE_PURPOSES and (
            position.broker_confirmed_remaining_quantity is None or action.requested_quantity > position.broker_confirmed_remaining_quantity
        ):
            quantity_status = RiskCheckStatus.BLOCK
            quantity_reason = "Lifecycle quantity cannot exceed broker-confirmed remaining quantity."
        add("QUANTITY_VALID", "QUANTITY", quantity_status, quantity_reason, threshold={"lot_size": instrument.lot_size}, observed={"quantity": action.requested_quantity})

        add_price_checks(request, add)

        if request.evaluated_at < action.authorized_not_before:
            time_status = RiskCheckStatus.BLOCK
            time_reason = "Authorized time has not been reached."
        elif action.authorized_not_after is not None and request.evaluated_at > action.authorized_not_after:
            time_status = RiskCheckStatus.EXPIRED
            time_reason = "Authorized time window has expired."
        else:
            time_status = RiskCheckStatus.PASS
            time_reason = "Intent timing is within the authorized window."
        add("TIMING_WINDOW", "TIMING", time_status, time_reason, observed={"evaluated_at": request.evaluated_at.isoformat()})

        market_required = action.purpose is ExecutionIntentPurpose.ENTRY or action.limit_price is not None or action.trigger_price is not None
        market_ok = (
            market.trading_date == intent.trading_date
            and market.source_age_seconds <= market.max_age_seconds
            and market.timestamp_skew_seconds <= market.max_timestamp_skew_seconds
            and market.has_ltp
            and (not market_required or (market.has_bid and market.has_ask))
            and (not market.oi_required or market.has_oi)
            and market.quality in {"COMPLETE", "FIXTURE", "LIFECYCLE_DERIVED"}
        )
        add("MARKET_DATA_QUALITY", "MARKET_DATA", RiskCheckStatus.PASS if market_ok else RiskCheckStatus.INSUFFICIENT_EVIDENCE, "Market-data quality must be sufficient for the intent.")

        duplicate_status = RiskCheckStatus.PASS
        duplicate_reason = "No duplicate action conflict observed."
        if request.duplicate.existing_intent_hash == intent.intent_hash:
            duplicate_status = RiskCheckStatus.DUPLICATE
            duplicate_reason = "Identical intent already exists; replay is idempotent."
        elif request.duplicate.same_idempotency_payload_hash and request.duplicate.same_idempotency_payload_hash != intent.intent_hash:
            duplicate_status = RiskCheckStatus.DUPLICATE
            duplicate_reason = "Same idempotency key has a different payload."
        elif request.duplicate.old_generation_seen:
            duplicate_status = RiskCheckStatus.BLOCK
            duplicate_reason = "Older protection generation cannot replace a newer generation."
        add("DUPLICATE_ACTION", "IDEMPOTENCY", duplicate_status, duplicate_reason)

        if action.purpose in LIFECYCLE_PURPOSES:
            if not position.position_cycle_id or position.position_status == "CLOSED":
                inv_status = RiskCheckStatus.BLOCK
                inv_reason = "Lifecycle/protection intent requires an open reconciled position."
            elif action.purpose in {ExecutionIntentPurpose.ORIGINAL_SL, ExecutionIntentPurpose.REVISED_SL} and position.duplicate_active_sl:
                inv_status = RiskCheckStatus.BLOCK
                inv_reason = "Duplicate active SL intent is blocked."
            elif action.purpose is ExecutionIntentPurpose.REVISED_SL and not position.superseded_requirement_id:
                inv_status = RiskCheckStatus.BLOCK
                inv_reason = "Revised SL must reference the superseded protection requirement."
            elif position.required_next_generation is not None and action.protection_generation is not None and action.protection_generation < position.required_next_generation:
                inv_status = RiskCheckStatus.BLOCK
                inv_reason = "Stale protection generation is rejected."
            else:
                inv_status = RiskCheckStatus.PASS
                inv_reason = "Position/protection invariants permit offline validation."
        else:
            inv_status = RiskCheckStatus.PASS
            inv_reason = "Position/protection invariant checks are not required for fresh entry."
        add("POSITION_PROTECTION_INVARIANTS", "POSITION_PROTECTION", inv_status, inv_reason)

        if not request.source_artifact_available:
            add("SOURCE_ARTIFACT_AVAILABLE", "SOURCE_EVIDENCE", RiskCheckStatus.INSUFFICIENT_EVIDENCE, "Source artifact is missing.")
        else:
            add("SOURCE_ARTIFACT_AVAILABLE", "SOURCE_EVIDENCE", RiskCheckStatus.PASS, "Source artifact is present.")
        if not request.source_hash_matches:
            add("SOURCE_HASH_MATCH", "SOURCE_EVIDENCE", RiskCheckStatus.BLOCK, "Source artifact hash does not match.")
        else:
            add("SOURCE_HASH_MATCH", "SOURCE_EVIDENCE", RiskCheckStatus.PASS, "Source artifact hash matches.")

        decision = _decision(checks)
        if duplicate_status is RiskCheckStatus.DUPLICATE and not any(check.result in {RiskCheckStatus.BLOCK, RiskCheckStatus.REJECT} for check in checks):
            decision = IntentValidationDecision.DUPLICATE
        return RiskValidationResult(
            validation_id=request.validation_id,
            execution_intent_id=intent.execution_intent_id,
            intent_hash=intent.intent_hash,
            decision=decision,
            checks=tuple(checks),
            failures=tuple(failures),
            warnings=tuple(warnings),
            authority_mode=ExecutionAuthorityMode.VALIDATED_NOT_SUBMITTABLE if decision is IntentValidationDecision.VALIDATED_NOT_SUBMITTABLE else intent.evidence.authority_mode,
        )


def add_price_checks(request: RiskValidationInput, add) -> None:
    action = request.intent.action
    instrument = request.intent.instrument

    prices = {"limit_price": action.limit_price, "trigger_price": action.trigger_price}
    invalid = [name for name, price in prices.items() if price is not None and not _valid_decimal(price)]
    non_positive = [name for name, price in prices.items() if price is not None and price <= 0]
    tick_invalid = [name for name, price in prices.items() if price is not None and _valid_decimal(price) and price % instrument.tick_size != 0]
    if invalid:
        add("PRICE_DECIMAL_VALID", "PRICE", RiskCheckStatus.REJECT, "Price must be a finite Decimal.", observed={"invalid": invalid})
    else:
        add("PRICE_DECIMAL_VALID", "PRICE", RiskCheckStatus.PASS, "Prices are valid Decimals.")
    if non_positive:
        add("PRICE_POSITIVE", "PRICE", RiskCheckStatus.REJECT, "Calculated risk/order price must be positive.", observed={"non_positive": non_positive})
    else:
        add("PRICE_POSITIVE", "PRICE", RiskCheckStatus.PASS, "Prices are positive where present.")
    if tick_invalid:
        add("PRICE_TICK_SIZE", "PRICE", RiskCheckStatus.REJECT, "Price must be normalized to tick size.", threshold={"tick_size": str(instrument.tick_size)}, observed={"tick_invalid": tick_invalid})
    else:
        add("PRICE_TICK_SIZE", "PRICE", RiskCheckStatus.PASS, "Prices align with tick size.")
    if action.order_type in {"SL", "STOP_LIMIT"} and action.trigger_price is None:
        add("PRICE_TRIGGER_RELATIONSHIP", "PRICE", RiskCheckStatus.REJECT, "Stop-style order requires trigger price.")
    elif action.order_type == "LIMIT" and action.limit_price is None:
        add("PRICE_TRIGGER_RELATIONSHIP", "PRICE", RiskCheckStatus.REJECT, "Limit order requires limit price.")
    else:
        add("PRICE_TRIGGER_RELATIONSHIP", "PRICE", RiskCheckStatus.PASS, "Order type and price fields are coherent.")


def mark_duplicate_request(request: RiskValidationInput, existing_hash: str | None) -> RiskValidationInput:
    return replace(request, duplicate=replace(request.duplicate, existing_intent_hash=existing_hash))


def _has_blocking_position_truth(request: RiskValidationInput) -> bool:
    return any(
        item
        in {
            "BROKER_ONLY_POSITION",
            "LOCAL_ONLY_POSITION",
            "POSITION_QUANTITY_MISMATCH",
            "POSITION_DIRECTION_MISMATCH",
            "UNKNOWN_LINKAGE",
            "UNKNOWN_PROTECTION_LINKAGE",
            "BROKER_STATE_UNAVAILABLE",
        }
        for item in request.reconciliation_blocking_classifications
    )


def _valid_decimal(value: Decimal) -> bool:
    try:
        return value.is_finite()
    except (AttributeError, InvalidOperation):
        return False


def _severity(status: RiskCheckStatus) -> RiskSeverity:
    if status is RiskCheckStatus.PASS:
        return RiskSeverity.INFO
    if status is RiskCheckStatus.WARNING:
        return RiskSeverity.WARNING
    if status in {RiskCheckStatus.REJECT, RiskCheckStatus.BLOCK, RiskCheckStatus.EXPIRED, RiskCheckStatus.DUPLICATE}:
        return RiskSeverity.ERROR
    return RiskSeverity.CRITICAL


def _decision(checks: list[RiskCheckResult]) -> IntentValidationDecision:
    statuses = {check.result for check in checks}
    if RiskCheckStatus.REJECT in statuses:
        return IntentValidationDecision.REJECTED
    if RiskCheckStatus.BLOCK in statuses:
        return IntentValidationDecision.BLOCKED
    if RiskCheckStatus.EXPIRED in statuses:
        return IntentValidationDecision.EXPIRED
    if RiskCheckStatus.INSUFFICIENT_EVIDENCE in statuses:
        return IntentValidationDecision.INSUFFICIENT_EVIDENCE
    if RiskCheckStatus.MANUAL_REVIEW_REQUIRED in statuses:
        return IntentValidationDecision.MANUAL_REVIEW_REQUIRED
    if RiskCheckStatus.DUPLICATE in statuses:
        return IntentValidationDecision.DUPLICATE
    return IntentValidationDecision.VALIDATED_NOT_SUBMITTABLE
