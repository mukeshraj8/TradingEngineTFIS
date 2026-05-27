from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta

from tfis.domain.enums import MonthlyStatus, OptionType

from .models import (
    CalendarContextEvent,
    CostSlippageSettingsEvent,
    EventEnvelope,
    MonthlyStatusInputEvent,
    OptionChainContract,
    OptionChainSnapshotEvent,
    PaperDataSourceReference,
    PaperEventType,
    PaperReadinessStatus,
    PaperSessionConfigEvent,
    PaperSessionManifest,
    PaperTradePlanEvent,
    PaperSessionState,
    PaperValidationIssue,
    PaperValidationResult,
    SelectedContractBarEvent,
    SelectedContractQuoteEvent,
    SnapshotLabel,
    UnderlyingQuoteEvent,
    UnderlyingSnapshotEvent,
)


DEFAULT_MAX_QUOTE_AGE = timedelta(seconds=60)
ALLOWED_TIMEZONE = "Asia/Kolkata"
ALLOWED_STRATEGY_CODE = "S23"
ALLOWED_SYMBOL = "NIFTY"
ALLOWED_CONTRACT_CYCLE = "WEEKLY"
ALLOWED_MODE = "paper"

PaperEvent = (
    UnderlyingQuoteEvent
    | UnderlyingSnapshotEvent
    | OptionChainSnapshotEvent
    | SelectedContractQuoteEvent
    | SelectedContractBarEvent
    | CalendarContextEvent
    | MonthlyStatusInputEvent
    | PaperSessionConfigEvent
    | CostSlippageSettingsEvent
    | PaperTradePlanEvent
)


def required_snapshot_labels_for_config(
    config: PaperSessionConfigEvent,
) -> tuple[SnapshotLabel, ...]:
    labels: list[SnapshotLabel] = [SnapshotLabel.ORPT]
    if config.allow_current_day_fsl_trp:
        labels = [SnapshotLabel.AT_0915, SnapshotLabel.ORPT, SnapshotLabel.RC]
    elif config.allow_recalculation:
        labels.append(SnapshotLabel.RC)
    return tuple(labels)


class S23PaperContractValidator:
    def validate_event(
        self,
        event: PaperEvent,
        *,
        now: datetime | None = None,
    ) -> PaperValidationResult:
        issues = list(self._validate_envelope(event.envelope))
        issues.extend(self._validate_event_payload(event))
        warnings = tuple(event.envelope.data_quality_flags)
        return self._build_result(
            issues=issues,
            evaluated_state=PaperSessionState.NOT_STARTED,
            warnings=warnings,
            now=now,
        )

    def validate_session_readiness(
        self,
        *,
        calendar_context: CalendarContextEvent,
        monthly_status_input: MonthlyStatusInputEvent,
        paper_config: PaperSessionConfigEvent,
        cost_settings: CostSlippageSettingsEvent,
        underlying_quote: UnderlyingQuoteEvent,
        snapshots: tuple[UnderlyingSnapshotEvent, ...],
        option_chain_snapshot: OptionChainSnapshotEvent | None,
        selected_contract_quote: SelectedContractQuoteEvent | None,
        now: datetime,
        max_quote_age: timedelta = DEFAULT_MAX_QUOTE_AGE,
        required_snapshot_labels: tuple[SnapshotLabel, ...] | None = None,
    ) -> PaperValidationResult:
        issues: list[PaperValidationIssue] = []
        warnings: set[str] = set()

        events: tuple[PaperEvent, ...] = (
            calendar_context,
            monthly_status_input,
            paper_config,
            cost_settings,
            underlying_quote,
            *snapshots,
        )
        if option_chain_snapshot is not None:
            events = (*events, option_chain_snapshot)
        if selected_contract_quote is not None:
            events = (*events, selected_contract_quote)

        for event in events:
            result = self.validate_event(event, now=now)
            issues.extend(result.issues)
            warnings.update(result.warnings)

        if any(issue.readiness_status is PaperReadinessStatus.ABORTED for issue in issues):
            return self._build_result(
                issues=issues,
                evaluated_state=PaperSessionState.DECISION_READY,
                warnings=tuple(sorted(warnings)),
                now=now,
                required_snapshot_labels=required_snapshot_labels or (),
            )

        if paper_config.strategy_code != ALLOWED_STRATEGY_CODE:
            issues.append(
                self._issue(
                    "unsupported_strategy_code",
                    "Only S23 is supported by the first paper-mode rollout.",
                    PaperReadinessStatus.NO_TRADE,
                    field_name="strategy_code",
                    event_type=PaperEventType.PAPER_SESSION_CONFIG,
                )
            )
        if paper_config.symbol != ALLOWED_SYMBOL:
            issues.append(
                self._issue(
                    "unsupported_symbol_scope",
                    "Only NIFTY is supported by the first paper-mode rollout.",
                    PaperReadinessStatus.NO_TRADE,
                    field_name="symbol",
                    event_type=PaperEventType.PAPER_SESSION_CONFIG,
                )
            )
        if paper_config.contract_cycle != ALLOWED_CONTRACT_CYCLE:
            issues.append(
                self._issue(
                    "unsupported_contract_cycle",
                    "Only weekly options are supported by the first paper-mode rollout.",
                    PaperReadinessStatus.NO_TRADE,
                    field_name="contract_cycle",
                    event_type=PaperEventType.PAPER_SESSION_CONFIG,
                )
            )
        if paper_config.mode.lower() != ALLOWED_MODE:
            issues.append(
                self._issue(
                    "unsupported_mode",
                    "Only paper mode is supported by this contract foundation.",
                    PaperReadinessStatus.ABORTED,
                    field_name="mode",
                    event_type=PaperEventType.PAPER_SESSION_CONFIG,
                )
            )
        if not paper_config.paper_mode_enabled:
            issues.append(
                self._issue(
                    "paper_mode_disabled",
                    "Paper mode must be explicitly enabled for S23 paper sessions.",
                    PaperReadinessStatus.ABORTED,
                    field_name="paper_mode_enabled",
                    event_type=PaperEventType.PAPER_SESSION_CONFIG,
                )
            )
        if not paper_config.same_day_square_off_only:
            issues.append(
                self._issue(
                    "unsupported_continuation_path",
                    "Next-day continuation is blocked for the first S23 paper rollout.",
                    PaperReadinessStatus.ABORTED,
                    field_name="same_day_square_off_only",
                    event_type=PaperEventType.PAPER_SESSION_CONFIG,
                )
            )
        if calendar_context.is_holiday:
            issues.append(
                self._issue(
                    "holiday_session_blocked",
                    "Holiday sessions must not trade.",
                    PaperReadinessStatus.NO_TRADE,
                    event_type=PaperEventType.CALENDAR_CONTEXT,
                )
            )
        if monthly_status_input.monthly_status is MonthlyStatus.UNKNOWN:
            issues.append(
                self._issue(
                    "monthly_status_unknown",
                    "Monthly status UNKNOWN must result in NO_TRADE.",
                    PaperReadinessStatus.NO_TRADE,
                    event_type=PaperEventType.MONTHLY_STATUS_INPUT,
                )
            )

        labels = required_snapshot_labels or required_snapshot_labels_for_config(paper_config)
        missing_snapshot_labels, duplicate_snapshot_labels = self._validate_required_snapshots(
            snapshots,
            labels,
        )
        if duplicate_snapshot_labels:
            for label in duplicate_snapshot_labels:
                issues.append(
                    self._issue(
                        f"duplicate_snapshot_{label.value}",
                        f"Multiple {label.value} snapshots were supplied for one S23 paper session.",
                        PaperReadinessStatus.ABORTED,
                        event_type=PaperEventType.UNDERLYING_SNAPSHOT,
                    )
                )
        for label in missing_snapshot_labels:
            issues.append(
                self._issue(
                    f"missing_snapshot_{label.value}",
                    f"Required {label.value} snapshot is missing for the requested S23 paper path.",
                    PaperReadinessStatus.NO_TRADE,
                    event_type=PaperEventType.UNDERLYING_SNAPSHOT,
                )
            )

        issues.extend(
            self._validate_quote_freshness(
                underlying_quote,
                now=now,
                max_quote_age=max_quote_age,
                stale_code="stale_underlying_quote",
            )
        )
        if selected_contract_quote is None:
            issues.append(
                self._issue(
                    "missing_selected_contract_quote",
                    "Decision-ready paper sessions require a selected contract quote.",
                    PaperReadinessStatus.NO_TRADE,
                    event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
                )
            )
        else:
            issues.extend(
                self._validate_quote_freshness(
                    selected_contract_quote,
                    now=now,
                    max_quote_age=max_quote_age,
                    stale_code="stale_selected_contract_quote",
                )
            )

        if option_chain_snapshot is None:
            issues.append(
                self._issue(
                    "missing_option_chain_snapshot",
                    "Decision-ready paper sessions require an option-chain snapshot.",
                    PaperReadinessStatus.NO_TRADE,
                    event_type=PaperEventType.OPTION_CHAIN_SNAPSHOT,
                )
            )
        elif selected_contract_quote is not None:
            contract_symbols = {contract.symbol for contract in option_chain_snapshot.contracts}
            if selected_contract_quote.symbol not in contract_symbols:
                issues.append(
                    self._issue(
                        "selected_contract_not_in_option_chain",
                        "The selected contract quote is not present in the supplied option chain.",
                        PaperReadinessStatus.NO_TRADE,
                        event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
                    )
                )

        return self._build_result(
            issues=issues,
            evaluated_state=PaperSessionState.DECISION_READY,
            warnings=tuple(sorted(warnings)),
            now=now,
            required_snapshot_labels=labels,
            missing_snapshot_labels=missing_snapshot_labels,
        )

    def _validate_envelope(self, envelope: EventEnvelope) -> tuple[PaperValidationIssue, ...]:
        issues: list[PaperValidationIssue] = []
        if not self._has_text(envelope.timezone):
            issues.append(
                self._issue(
                    "missing_timezone",
                    "Normalized paper events require a timezone string.",
                    PaperReadinessStatus.ABORTED,
                    field_name="timezone",
                    event_type=envelope.event_type,
                )
            )
        elif envelope.timezone != ALLOWED_TIMEZONE:
            issues.append(
                self._issue(
                    "unsupported_timezone",
                    "Normalized S23 paper events must use Asia/Kolkata.",
                    PaperReadinessStatus.ABORTED,
                    field_name="timezone",
                    event_type=envelope.event_type,
                )
            )
        if not self._is_timezone_aware(envelope.effective_timestamp):
            issues.append(
                self._issue(
                    "naive_effective_timestamp",
                    "effective_timestamp must be timezone-aware.",
                    PaperReadinessStatus.ABORTED,
                    field_name="effective_timestamp",
                    event_type=envelope.event_type,
                )
            )
        if not self._is_timezone_aware(envelope.captured_at):
            issues.append(
                self._issue(
                    "naive_captured_at",
                    "captured_at must be timezone-aware.",
                    PaperReadinessStatus.ABORTED,
                    field_name="captured_at",
                    event_type=envelope.event_type,
                )
            )
        if envelope.effective_timestamp.date() != envelope.session_date:
            issues.append(
                self._issue(
                    "session_date_mismatch",
                    "effective_timestamp date must match session_date.",
                    PaperReadinessStatus.ABORTED,
                    field_name="session_date",
                    event_type=envelope.event_type,
                )
            )
        if not self._has_text(envelope.source_type):
            issues.append(
                self._issue(
                    "missing_source_type",
                    "Normalized paper events require a source_type.",
                    PaperReadinessStatus.ABORTED,
                    field_name="source_type",
                    event_type=envelope.event_type,
                )
            )
        if not self._has_text(envelope.source_id):
            issues.append(
                self._issue(
                    "missing_source_id",
                    "Normalized paper events require a source_id.",
                    PaperReadinessStatus.ABORTED,
                    field_name="source_id",
                    event_type=envelope.event_type,
                )
            )
        if not self._has_text(envelope.normalized_by):
            issues.append(
                self._issue(
                    "missing_normalized_by",
                    "Normalized paper events require a normalized_by value.",
                    PaperReadinessStatus.ABORTED,
                    field_name="normalized_by",
                    event_type=envelope.event_type,
                )
            )
        return tuple(issues)

    def _validate_event_payload(self, event: PaperEvent) -> tuple[PaperValidationIssue, ...]:
        if isinstance(event, UnderlyingQuoteEvent):
            return self._validate_underlying_quote(event)
        if isinstance(event, UnderlyingSnapshotEvent):
            return self._validate_underlying_snapshot(event)
        if isinstance(event, OptionChainSnapshotEvent):
            return self._validate_option_chain_snapshot(event)
        if isinstance(event, SelectedContractQuoteEvent):
            return self._validate_selected_contract_quote(event)
        if isinstance(event, SelectedContractBarEvent):
            return self._validate_selected_contract_bar(event)
        if isinstance(event, CalendarContextEvent):
            return self._validate_calendar_context(event)
        if isinstance(event, MonthlyStatusInputEvent):
            return self._validate_monthly_status_input(event)
        if isinstance(event, PaperSessionConfigEvent):
            return self._validate_paper_config(event)
        if isinstance(event, CostSlippageSettingsEvent):
            return self._validate_cost_settings(event)
        if isinstance(event, PaperTradePlanEvent):
            return self._validate_trade_plan_input(event)
        raise TypeError(f"Unsupported paper event type: {type(event)!r}")

    def _validate_underlying_quote(
        self,
        event: UnderlyingQuoteEvent,
    ) -> tuple[PaperValidationIssue, ...]:
        issues: list[PaperValidationIssue] = []
        if not self._has_text(event.symbol):
            issues.append(
                self._issue(
                    "missing_symbol",
                    "Underlying quote requires a symbol.",
                    PaperReadinessStatus.ABORTED,
                    field_name="symbol",
                    event_type=event.envelope.event_type,
                )
            )
        if event.ltp is None:
            issues.append(
                self._issue(
                    "missing_ltp",
                    "Underlying quote requires ltp.",
                    PaperReadinessStatus.ABORTED,
                    field_name="ltp",
                    event_type=event.envelope.event_type,
                )
            )
        return tuple(issues)

    def _validate_underlying_snapshot(
        self,
        event: UnderlyingSnapshotEvent,
    ) -> tuple[PaperValidationIssue, ...]:
        issues: list[PaperValidationIssue] = []
        if event.high is None:
            issues.append(
                self._issue(
                    "missing_high",
                    "Underlying snapshot requires high.",
                    PaperReadinessStatus.ABORTED,
                    field_name="high",
                    event_type=event.envelope.event_type,
                )
            )
        if event.low is None:
            issues.append(
                self._issue(
                    "missing_low",
                    "Underlying snapshot requires low.",
                    PaperReadinessStatus.ABORTED,
                    field_name="low",
                    event_type=event.envelope.event_type,
                )
            )
        if not self._is_timezone_aware(event.bar_start) or not self._is_timezone_aware(event.bar_end):
            issues.append(
                self._issue(
                    "naive_snapshot_bar_time",
                    "Snapshot bar_start and bar_end must be timezone-aware.",
                    PaperReadinessStatus.ABORTED,
                    event_type=event.envelope.event_type,
                )
            )
        if event.bar_end < event.bar_start:
            issues.append(
                self._issue(
                    "snapshot_time_range_invalid",
                    "Underlying snapshot bar_end must not precede bar_start.",
                    PaperReadinessStatus.ABORTED,
                    event_type=event.envelope.event_type,
                )
            )
        return tuple(issues)

    def _validate_option_chain_snapshot(
        self,
        event: OptionChainSnapshotEvent,
    ) -> tuple[PaperValidationIssue, ...]:
        issues: list[PaperValidationIssue] = []
        if not self._has_text(event.underlying_symbol):
            issues.append(
                self._issue(
                    "missing_underlying_symbol",
                    "Option-chain snapshot requires an underlying symbol.",
                    PaperReadinessStatus.ABORTED,
                    field_name="underlying_symbol",
                    event_type=event.envelope.event_type,
                )
            )
        if not event.contracts:
            issues.append(
                self._issue(
                    "missing_option_chain_contracts",
                    "Option-chain snapshot requires at least one contract row.",
                    PaperReadinessStatus.NO_TRADE,
                    event_type=event.envelope.event_type,
                )
            )
        for contract in event.contracts:
            issues.extend(self._validate_option_chain_contract(contract))
        return tuple(issues)

    def _validate_option_chain_contract(
        self,
        contract: OptionChainContract,
    ) -> tuple[PaperValidationIssue, ...]:
        issues: list[PaperValidationIssue] = []
        if not self._has_text(contract.symbol):
            issues.append(
                self._issue(
                    "missing_contract_symbol",
                    "Option-chain contract rows require a symbol.",
                    PaperReadinessStatus.ABORTED,
                    field_name="symbol",
                    event_type=PaperEventType.OPTION_CHAIN_SNAPSHOT,
                )
            )
        required_values = {
            "option_type": contract.option_type,
            "strike": contract.strike,
            "expiry": contract.expiry,
            "bid": contract.bid,
            "ask": contract.ask,
            "ltp": contract.ltp,
            "oi": contract.oi,
        }
        for field_name, value in required_values.items():
            if value is None:
                issues.append(
                    self._issue(
                        f"missing_contract_{field_name}",
                        f"Option-chain contract rows require {field_name}.",
                        PaperReadinessStatus.ABORTED,
                        field_name=field_name,
                        event_type=PaperEventType.OPTION_CHAIN_SNAPSHOT,
                    )
                )
        return tuple(issues)

    def _validate_selected_contract_quote(
        self,
        event: SelectedContractQuoteEvent,
    ) -> tuple[PaperValidationIssue, ...]:
        issues: list[PaperValidationIssue] = []
        if not self._has_text(event.symbol):
            issues.append(
                self._issue(
                    "missing_selected_contract_symbol",
                    "Selected contract quote requires a symbol.",
                    PaperReadinessStatus.ABORTED,
                    field_name="symbol",
                    event_type=event.envelope.event_type,
                )
            )
        required_values = {
            "option_type": event.option_type,
            "strike": event.strike,
            "expiry": event.expiry,
            "bid": event.bid,
            "ask": event.ask,
            "ltp": event.ltp,
            "oi": event.oi,
        }
        for field_name, value in required_values.items():
            if value is None:
                issues.append(
                    self._issue(
                        f"missing_selected_contract_{field_name}",
                        f"Selected contract quote requires {field_name}.",
                        PaperReadinessStatus.ABORTED,
                        field_name=field_name,
                        event_type=event.envelope.event_type,
                    )
                )
        return tuple(issues)

    def _validate_selected_contract_bar(
        self,
        event: SelectedContractBarEvent,
    ) -> tuple[PaperValidationIssue, ...]:
        issues: list[PaperValidationIssue] = []
        if not self._has_text(event.symbol):
            issues.append(
                self._issue(
                    "missing_selected_contract_bar_symbol",
                    "Selected contract bar requires a symbol.",
                    PaperReadinessStatus.ABORTED,
                    field_name="symbol",
                    event_type=event.envelope.event_type,
                )
            )
        for field_name, value in {
            "open": event.open,
            "high": event.high,
            "low": event.low,
            "close": event.close,
        }.items():
            if value is None:
                issues.append(
                    self._issue(
                        f"missing_selected_contract_bar_{field_name}",
                        f"Selected contract bar requires {field_name}.",
                        PaperReadinessStatus.ABORTED,
                        field_name=field_name,
                        event_type=event.envelope.event_type,
                    )
                )
        if not self._is_timezone_aware(event.bar_start) or not self._is_timezone_aware(event.bar_end):
            issues.append(
                self._issue(
                    "naive_selected_contract_bar_time",
                    "Selected contract bar times must be timezone-aware.",
                    PaperReadinessStatus.ABORTED,
                    event_type=event.envelope.event_type,
                )
            )
        if event.bar_end < event.bar_start:
            issues.append(
                self._issue(
                    "selected_contract_bar_time_range_invalid",
                    "Selected contract bar_end must not precede bar_start.",
                    PaperReadinessStatus.ABORTED,
                    event_type=event.envelope.event_type,
                )
            )
        return tuple(issues)

    def _validate_calendar_context(
        self,
        event: CalendarContextEvent,
    ) -> tuple[PaperValidationIssue, ...]:
        issues: list[PaperValidationIssue] = []
        if event.weekly_expiry is None:
            issues.append(
                self._issue(
                    "missing_weekly_expiry",
                    "Calendar context requires weekly_expiry.",
                    PaperReadinessStatus.ABORTED,
                    field_name="weekly_expiry",
                    event_type=event.envelope.event_type,
                )
            )
        if event.market_open is None or event.market_close is None:
            issues.append(
                self._issue(
                    "missing_market_hours",
                    "Calendar context requires market_open and market_close.",
                    PaperReadinessStatus.ABORTED,
                    event_type=event.envelope.event_type,
                )
            )
        return tuple(issues)

    def _validate_monthly_status_input(
        self,
        event: MonthlyStatusInputEvent,
    ) -> tuple[PaperValidationIssue, ...]:
        issues: list[PaperValidationIssue] = []
        if event.monthly_status is None:
            issues.append(
                self._issue(
                    "missing_monthly_status",
                    "Monthly status input requires a status value.",
                    PaperReadinessStatus.ABORTED,
                    field_name="monthly_status",
                    event_type=event.envelope.event_type,
                )
            )
        if not self._has_text(event.status_source):
            issues.append(
                self._issue(
                    "missing_status_source",
                    "Monthly status input requires a status_source.",
                    PaperReadinessStatus.ABORTED,
                    field_name="status_source",
                    event_type=event.envelope.event_type,
                )
            )
        if event.reference_date is None:
            issues.append(
                self._issue(
                    "missing_reference_date",
                    "Monthly status input requires reference_date.",
                    PaperReadinessStatus.ABORTED,
                    field_name="reference_date",
                    event_type=event.envelope.event_type,
                )
            )
        if not self._has_text(event.threshold_version):
            issues.append(
                self._issue(
                    "missing_threshold_version",
                    "Monthly status input requires threshold_version.",
                    PaperReadinessStatus.ABORTED,
                    field_name="threshold_version",
                    event_type=event.envelope.event_type,
                )
            )
        return tuple(issues)

    def _validate_paper_config(
        self,
        event: PaperSessionConfigEvent,
    ) -> tuple[PaperValidationIssue, ...]:
        issues: list[PaperValidationIssue] = []
        for field_name, value in {
            "strategy_code": event.strategy_code,
            "operator_id": event.operator_id,
            "symbol": event.symbol,
            "contract_cycle": event.contract_cycle,
            "mode": event.mode,
        }.items():
            if not self._has_text(value):
                issues.append(
                    self._issue(
                        f"missing_{field_name}",
                        f"Paper session config requires {field_name}.",
                        PaperReadinessStatus.ABORTED,
                        field_name=field_name,
                        event_type=event.envelope.event_type,
                    )
                )
        return tuple(issues)

    def _validate_cost_settings(
        self,
        event: CostSlippageSettingsEvent,
    ) -> tuple[PaperValidationIssue, ...]:
        issues: list[PaperValidationIssue] = []
        for field_name, value in {
            "brokerage_per_lot": event.brokerage_per_lot,
            "slippage_entry_points": event.slippage_entry_points,
            "slippage_exit_points": event.slippage_exit_points,
        }.items():
            if value is None:
                issues.append(
                    self._issue(
                        f"missing_{field_name}",
                        f"Cost settings require {field_name}.",
                        PaperReadinessStatus.ABORTED,
                        field_name=field_name,
                        event_type=event.envelope.event_type,
                    )
                )
        if not self._has_text(event.spread_buffer_policy):
            issues.append(
                self._issue(
                    "missing_spread_buffer_policy",
                    "Cost settings require spread_buffer_policy.",
                    PaperReadinessStatus.ABORTED,
                    field_name="spread_buffer_policy",
                    event_type=event.envelope.event_type,
                )
            )
        if not self._has_text(event.version_label):
            issues.append(
                self._issue(
                    "missing_version_label",
                    "Cost settings require version_label.",
                    PaperReadinessStatus.ABORTED,
                    field_name="version_label",
                    event_type=event.envelope.event_type,
                )
            )
        return tuple(issues)

    def _validate_trade_plan_input(
        self,
        event: PaperTradePlanEvent,
    ) -> tuple[PaperValidationIssue, ...]:
        issues: list[PaperValidationIssue] = []
        for field_name, value in {
            "strategy_branch": event.strategy_branch,
            "order_side": event.order_side,
            "order_reference_label": event.order_reference_label,
        }.items():
            if not self._has_text(value):
                issues.append(
                    self._issue(
                        f"missing_{field_name}",
                        f"Trade plan input requires {field_name}.",
                        PaperReadinessStatus.ABORTED,
                        field_name=field_name,
                        event_type=event.envelope.event_type,
                    )
                )
        if self._has_text(event.order_side) and event.order_side != "SELL":
            issues.append(
                self._issue(
                    "unsupported_trade_plan_order_side",
                    "The first S23 paper rollout only supports SELL order intents.",
                    PaperReadinessStatus.ABORTED,
                    field_name="order_side",
                    event_type=event.envelope.event_type,
                )
            )
        for field_name, value in {
            "lots": event.lots,
            "quantity": event.quantity,
            "planned_entry_price": event.planned_entry_price,
            "target_price": event.target_price,
            "stoploss_price": event.stoploss_price,
        }.items():
            if value is None:
                issues.append(
                    self._issue(
                        f"missing_{field_name}",
                        f"Trade plan input requires {field_name}.",
                        PaperReadinessStatus.ABORTED,
                        field_name=field_name,
                        event_type=event.envelope.event_type,
                    )
                )
            elif float(value) <= 0:
                issues.append(
                    self._issue(
                        f"invalid_{field_name}",
                        f"Trade plan input requires a positive {field_name}.",
                        PaperReadinessStatus.ABORTED,
                        field_name=field_name,
                        event_type=event.envelope.event_type,
                    )
                )
        if event.order_reference_time is None:
            issues.append(
                self._issue(
                    "missing_order_reference_time",
                    "Trade plan input requires order_reference_time.",
                    PaperReadinessStatus.ABORTED,
                    field_name="order_reference_time",
                    event_type=event.envelope.event_type,
                )
            )
        elif not self._is_timezone_aware(event.order_reference_time):
            issues.append(
                self._issue(
                    "naive_order_reference_time",
                    "Trade plan input order_reference_time must be timezone-aware.",
                    PaperReadinessStatus.ABORTED,
                    field_name="order_reference_time",
                    event_type=event.envelope.event_type,
                )
            )
        return tuple(issues)

    def _validate_required_snapshots(
        self,
        snapshots: tuple[UnderlyingSnapshotEvent, ...],
        required_labels: tuple[SnapshotLabel, ...],
    ) -> tuple[tuple[SnapshotLabel, ...], tuple[SnapshotLabel, ...]]:
        counts: dict[SnapshotLabel, int] = {}
        complete_labels: set[SnapshotLabel] = set()
        for snapshot in snapshots:
            counts[snapshot.snapshot_label] = counts.get(snapshot.snapshot_label, 0) + 1
            if snapshot.complete:
                complete_labels.add(snapshot.snapshot_label)

        missing = tuple(label for label in required_labels if label not in complete_labels)
        duplicates = tuple(
            label
            for label, count in sorted(counts.items(), key=lambda item: item[0].value)
            if count > 1
        )
        return missing, duplicates

    def _validate_quote_freshness(
        self,
        quote_event: UnderlyingQuoteEvent | SelectedContractQuoteEvent,
        *,
        now: datetime,
        max_quote_age: timedelta,
        stale_code: str,
    ) -> tuple[PaperValidationIssue, ...]:
        if not self._is_timezone_aware(now):
            return (
                self._issue(
                    "naive_validation_reference_time",
                    "Validation reference time must be timezone-aware.",
                    PaperReadinessStatus.ABORTED,
                ),
            )
        quote_age = now - quote_event.envelope.effective_timestamp
        if quote_age.total_seconds() < 0:
            return (
                self._issue(
                    "future_quote_timestamp",
                    "Quote effective_timestamp is in the future relative to validation time.",
                    PaperReadinessStatus.ABORTED,
                    event_type=quote_event.envelope.event_type,
                ),
            )
        if quote_age > max_quote_age:
            return (
                self._issue(
                    stale_code,
                    f"Quote age {quote_age.total_seconds():.0f}s exceeds allowed freshness.",
                    PaperReadinessStatus.NO_TRADE,
                    event_type=quote_event.envelope.event_type,
                ),
            )
        return ()

    def _build_result(
        self,
        *,
        issues: list[PaperValidationIssue],
        evaluated_state: PaperSessionState,
        warnings: tuple[str, ...],
        now: datetime | None,
        required_snapshot_labels: tuple[SnapshotLabel, ...] = (),
        missing_snapshot_labels: tuple[SnapshotLabel, ...] = (),
    ) -> PaperValidationResult:
        abort_reasons = tuple(
            issue.code
            for issue in issues
            if issue.readiness_status is PaperReadinessStatus.ABORTED
        )
        no_trade_reasons = tuple(
            issue.code
            for issue in issues
            if issue.readiness_status is PaperReadinessStatus.NO_TRADE
        )
        if abort_reasons:
            readiness_status = PaperReadinessStatus.ABORTED
        elif no_trade_reasons:
            readiness_status = PaperReadinessStatus.NO_TRADE
        else:
            readiness_status = PaperReadinessStatus.READY
        return PaperValidationResult(
            readiness_status=readiness_status,
            issues=tuple(issues),
            evaluated_state=evaluated_state,
            validated_at=now or datetime.now(),
            required_snapshot_labels=required_snapshot_labels,
            missing_snapshot_labels=missing_snapshot_labels,
            warnings=warnings,
            no_trade_reasons=no_trade_reasons,
            abort_reasons=abort_reasons,
        )

    def _issue(
        self,
        code: str,
        message: str,
        readiness_status: PaperReadinessStatus,
        *,
        field_name: str | None = None,
        event_type: PaperEventType | None = None,
    ) -> PaperValidationIssue:
        return PaperValidationIssue(
            code=code,
            message=message,
            readiness_status=readiness_status,
            field_name=field_name,
            event_type=event_type,
        )

    def _has_text(self, value: object) -> bool:
        return isinstance(value, str) and value.strip() != ""

    def _is_timezone_aware(self, value: datetime) -> bool:
        return value.tzinfo is not None and value.utcoffset() is not None


class S23PaperSessionManifestBuilder:
    def build(
        self,
        *,
        paper_config: PaperSessionConfigEvent,
        cost_settings: CostSlippageSettingsEvent,
        validation_result: PaperValidationResult,
        events: tuple[PaperEvent, ...],
        generated_at: datetime,
    ) -> PaperSessionManifest:
        data_sources = self._collect_data_sources(events)
        overlays: list[str] = []
        if paper_config.allow_recalculation:
            overlays.append("S23_RECALCULATION")
        if paper_config.allow_current_day_fsl_trp:
            overlays.append("S23_CURRENT_DAY_FSL_TRP")

        return PaperSessionManifest(
            strategy_code=paper_config.strategy_code,
            symbol=paper_config.symbol,
            contract_cycle=paper_config.contract_cycle,
            mode=paper_config.mode,
            session_date=paper_config.envelope.session_date,
            readiness_status=validation_result.readiness_status,
            evaluated_state=validation_result.evaluated_state,
            overlays_enabled=tuple(overlays),
            data_sources=data_sources,
            cost_slippage_version=cost_settings.version_label,
            no_trade_reasons=validation_result.no_trade_reasons,
            abort_reasons=validation_result.abort_reasons,
            warnings=validation_result.warnings,
            synthetic_fixture_used=any(source.synthetic_fixture for source in data_sources),
            generated_at=generated_at,
            brokerage_per_lot=cost_settings.brokerage_per_lot,
            slippage_entry_points=cost_settings.slippage_entry_points,
            slippage_exit_points=cost_settings.slippage_exit_points,
            spread_buffer_policy=cost_settings.spread_buffer_policy,
        )

    def _collect_data_sources(
        self,
        events: tuple[PaperEvent, ...],
    ) -> tuple[PaperDataSourceReference, ...]:
        unique_sources: dict[tuple[str, str], PaperDataSourceReference] = {}
        for event in events:
            envelope = event.envelope
            key = (envelope.event_type.value, envelope.source_id)
            unique_sources[key] = PaperDataSourceReference(
                event_type=envelope.event_type,
                source_type=envelope.source_type,
                source_id=envelope.source_id,
                synthetic_fixture=envelope.synthetic_fixture,
            )
        return tuple(
            unique_sources[key]
            for key in sorted(unique_sources, key=lambda item: (item[0], item[1]))
        )
