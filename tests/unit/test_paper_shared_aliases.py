from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tfis.paper import (
    PaperLifecycleSupervisor,
    PaperLifecycleSupervisorContext,
    PaperLifecycleSupervisorResult,
    PaperLifecycleSupervisorStep,
    PaperOpenPositionCandidate,
    PaperOpenPositionDiscovery,
    paper_trade_action_required,
    paper_trade_branch_label,
    paper_trade_display_status_label,
    paper_trade_event_type_for_manager_status,
    paper_trade_followup_note,
    paper_trade_is_open,
    paper_trade_manager_status_is_lifecycle_terminal,
    paper_trade_manager_status_is_open,
    paper_trade_manager_status_is_terminal,
    paper_trade_normalized_message,
    paper_trade_option_label,
    paper_trade_pnl_tone,
    paper_trade_select_display_row,
    paper_trade_status_labels,
    paper_trade_summary_counts,
    paper_trade_is_terminal,
    paper_trade_status_kind,
    paper_trade_visible_for_latest_session,
    paper_position_is_active,
    paper_position_blocks_new_entry,
    paper_position_is_no_longer_open,
    paper_order_is_terminal,
    paper_order_trade_event_type,
    paper_order_trade_lifecycle_status,
    paper_order_visible_in_trade_monitor,
    paper_order_is_waiting_for_trigger,
    PaperOrderEvent,
    PaperOrderFinalizer,
    PaperOrderFinalizerDecision,
    PaperOrderFinalizerSummary,
    PaperOrderState,
    PaperOrderStateError,
    PaperOrderStateStore,
    PaperOrderStatus,
    PaperPositionState,
    PaperPositionStateError,
    PaperPositionStateEvent,
    PaperPositionStateEventType,
    PaperPositionStateStatus,
    PaperPositionStateStore,
    S23PaperLifecycleSupervisor,
    S23PaperLifecycleSupervisorContext,
    S23PaperLifecycleSupervisorResult,
    S23PaperLifecycleSupervisorStep,
    S23OpenPaperPositionCandidate,
    S23OpenPaperPositionDiscovery,
    S23PaperOrderEvent,
    S23PaperOrderFinalizer,
    S23PaperOrderFinalizerDecision,
    S23PaperOrderFinalizerSummary,
    S23PaperOrderState,
    S23PaperOrderStateError,
    S23PaperOrderStateStore,
    S23PaperOrderStatus,
    S23PaperPositionState,
    S23PaperPositionStateError,
    S23PaperPositionStateEvent,
    S23PaperPositionStateEventType,
    S23PaperPositionStateStatus,
    S23PaperPositionStateStore,
)


def test_paper_order_finalizer_aliases_point_to_existing_s23_types() -> None:
    assert PaperOrderFinalizer is S23PaperOrderFinalizer
    assert PaperOrderFinalizerDecision is S23PaperOrderFinalizerDecision
    assert PaperOrderFinalizerSummary is S23PaperOrderFinalizerSummary


def test_paper_lifecycle_supervisor_aliases_point_to_existing_s23_types() -> None:
    assert PaperLifecycleSupervisor is S23PaperLifecycleSupervisor
    assert PaperLifecycleSupervisorContext is S23PaperLifecycleSupervisorContext
    assert PaperLifecycleSupervisorResult is S23PaperLifecycleSupervisorResult
    assert PaperLifecycleSupervisorStep is S23PaperLifecycleSupervisorStep


def test_paper_open_position_discovery_aliases_point_to_existing_s23_types() -> None:
    assert PaperOpenPositionCandidate is S23OpenPaperPositionCandidate
    assert PaperOpenPositionDiscovery is S23OpenPaperPositionDiscovery


def test_paper_order_state_aliases_point_to_existing_s23_types() -> None:
    assert PaperOrderEvent is S23PaperOrderEvent
    assert PaperOrderState is S23PaperOrderState
    assert PaperOrderStateError is S23PaperOrderStateError
    assert PaperOrderStateStore is S23PaperOrderStateStore
    assert PaperOrderStatus is S23PaperOrderStatus


def test_paper_position_state_aliases_point_to_existing_s23_types() -> None:
    assert PaperPositionState is S23PaperPositionState
    assert PaperPositionStateError is S23PaperPositionStateError
    assert PaperPositionStateEvent is S23PaperPositionStateEvent
    assert PaperPositionStateEventType is S23PaperPositionStateEventType
    assert PaperPositionStateStatus is S23PaperPositionStateStatus
    assert PaperPositionStateStore is S23PaperPositionStateStore


def test_paper_order_status_helpers_cover_enum_and_string_inputs() -> None:
    assert paper_order_is_waiting_for_trigger(S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER) is True
    assert paper_order_is_waiting_for_trigger("PAPER_ORDER_WAITING_FOR_TRIGGER") is True
    assert paper_order_is_waiting_for_trigger(S23PaperOrderStatus.PAPER_ORDER_FILLED) is False
    assert paper_order_is_terminal(S23PaperOrderStatus.PAPER_ORDER_FILLED) is True
    assert paper_order_is_terminal("PAPER_ORDER_NOT_FILLED") is True
    assert paper_order_is_terminal("PAPER_ORDER_WAITING_FOR_TRIGGER") is False
    assert paper_order_trade_event_type("PAPER_ORDER_WAITING_FOR_TRIGGER") == "ORDER_WAITING"
    assert paper_order_trade_event_type("PAPER_ORDER_NOT_FILLED") == "ORDER_NOT_FILLED"
    assert paper_order_trade_lifecycle_status("PAPER_ORDER_WAITING_FOR_TRIGGER") == "ORDER_WAITING_FOR_TRIGGER"
    assert paper_order_trade_lifecycle_status("PAPER_ORDER_NOT_FILLED") == "ORDER_NOT_FILLED"
    assert paper_order_visible_in_trade_monitor("PAPER_ORDER_WAITING_FOR_TRIGGER") is True
    assert paper_order_visible_in_trade_monitor("PAPER_ORDER_NOT_FILLED") is True
    assert paper_order_visible_in_trade_monitor("PAPER_ORDER_FILLED") is False


def test_paper_position_status_helpers_cover_enum_and_string_inputs() -> None:
    assert paper_position_is_active(S23PaperPositionStateStatus.PAPER_POSITION_OPEN) is True
    assert paper_position_is_active("PAPER_POSITION_CARRIED_FORWARD") is True
    assert paper_position_is_active(S23PaperPositionStateStatus.PAPER_POSITION_CLOSED) is False
    assert paper_position_blocks_new_entry("PAPER_POSITION_RESUMED") is True
    assert paper_position_blocks_new_entry("PAPER_REVERSE_ENTRY_REQUIRED") is True
    assert paper_position_blocks_new_entry("PAPER_FRESH_ENTRY_REQUIRED") is False
    assert paper_position_is_no_longer_open(S23PaperPositionStateStatus.PAPER_POSITION_CLOSED) is True
    assert paper_position_is_no_longer_open("PAPER_REVERSE_ENTRY_REQUIRED") is True
    assert paper_position_is_no_longer_open("PAPER_POSITION_OPEN") is False


def test_paper_trade_classification_helpers_cover_terminal_open_and_action_required() -> None:
    assert paper_trade_is_terminal(
        event_type="CLOSE",
        lifecycle_status="PAPER_POSITION_CLOSED",
        manager_status="PAPER_POSITION_FORCE_CLOSED",
    ) is True
    assert paper_trade_is_terminal(
        event_type="HOLD",
        lifecycle_status="PAPER_POSITION_OPEN",
        manager_status="PAPER_POSITION_HELD",
    ) is False
    assert paper_trade_is_open(
        lifecycle_status="PAPER_POSITION_OPEN",
        manager_status="PAPER_POSITION_HELD",
    ) is True
    assert paper_trade_is_open(
        lifecycle_status="PAPER_POSITION_CLOSED",
        manager_status="PAPER_POSITION_ALREADY_CLOSED",
    ) is False
    assert paper_trade_action_required(
        fresh_entry_required=True,
        reverse_entry_required=False,
        rollover_required=False,
    ) is True
    assert paper_trade_action_required(
        fresh_entry_required=False,
        reverse_entry_required=False,
        rollover_required=False,
    ) is False


def test_paper_trade_display_status_label_normalizes_waiting_and_not_filled() -> None:
    assert paper_trade_display_status_label("PAPER_ORDER_WAITING_FOR_TRIGGER") == "ORDER_WAITING_FOR_TRIGGER"
    assert paper_trade_display_status_label("PAPER_ORDER_NOT_FILLED") == "ORDER_NOT_FILLED"
    assert paper_trade_display_status_label("PAPER_POSITION_HELD") == "PAPER_POSITION_HELD"
    assert paper_trade_display_status_label("n/a") == ""


def test_paper_trade_status_kind_covers_dashboard_state_buckets() -> None:
    assert paper_trade_status_kind(
        event_type="CLOSE",
        lifecycle_status="PAPER_POSITION_CLOSED",
        manager_status="PAPER_POSITION_CLOSED",
        fresh_entry_required=False,
        reverse_entry_required=False,
        rollover_required=False,
    ) == "closed"
    assert paper_trade_status_kind(
        event_type="HOLD",
        lifecycle_status="PAPER_FRESH_ENTRY_REQUIRED",
        manager_status="PAPER_POSITION_FRESH_ENTRY_REQUIRED",
        fresh_entry_required=True,
        reverse_entry_required=False,
        rollover_required=False,
    ) == "action"
    assert paper_trade_status_kind(
        event_type="HOLD",
        lifecycle_status="ORDER_NOT_FILLED",
        manager_status="PAPER_ORDER_NOT_FILLED",
        fresh_entry_required=False,
        reverse_entry_required=False,
        rollover_required=False,
    ) == "not_filled"
    assert paper_trade_status_kind(
        event_type="OPEN",
        lifecycle_status="ORDER_WAITING_FOR_TRIGGER",
        manager_status="PAPER_ORDER_WAITING_FOR_TRIGGER",
        fresh_entry_required=False,
        reverse_entry_required=False,
        rollover_required=False,
    ) == "waiting"
    assert paper_trade_status_kind(
        event_type="HOLD",
        lifecycle_status="PAPER_POSITION_OPEN",
        manager_status="PAPER_POSITION_HELD",
        fresh_entry_required=False,
        reverse_entry_required=False,
        rollover_required=False,
    ) == "open"
    assert paper_trade_status_kind(
        event_type="OPEN",
        lifecycle_status="READY",
        manager_status="READY",
        fresh_entry_required=False,
        reverse_entry_required=False,
        rollover_required=False,
    ) == "neutral"


def test_paper_trade_visible_for_latest_session_keeps_open_action_and_future_closes() -> None:
    latest_session_date = datetime.fromisoformat("2026-07-15T09:30:00+05:30").date()

    assert paper_trade_visible_for_latest_session(
        row_session_date=latest_session_date,
        event_timestamp=None,
        latest_session_date=latest_session_date,
        event_type="OPEN",
        lifecycle_status="ORDER_WAITING_FOR_TRIGGER",
        manager_status="PAPER_ORDER_WAITING_FOR_TRIGGER",
        fresh_entry_required=False,
        reverse_entry_required=False,
        rollover_required=False,
    ) is True
    assert paper_trade_visible_for_latest_session(
        row_session_date=datetime.fromisoformat("2026-07-16T09:30:00+05:30").date(),
        event_timestamp=None,
        latest_session_date=latest_session_date,
        event_type="CLOSE",
        lifecycle_status="PAPER_POSITION_CLOSED",
        manager_status="PAPER_POSITION_CLOSED",
        fresh_entry_required=False,
        reverse_entry_required=False,
        rollover_required=False,
    ) is True
    assert paper_trade_visible_for_latest_session(
        row_session_date=datetime.fromisoformat("2026-07-14T09:30:00+05:30").date(),
        event_timestamp=None,
        latest_session_date=latest_session_date,
        event_type="HOLD",
        lifecycle_status="PAPER_POSITION_OPEN",
        manager_status="PAPER_POSITION_HELD",
        fresh_entry_required=False,
        reverse_entry_required=False,
        rollover_required=False,
    ) is True
    assert paper_trade_visible_for_latest_session(
        row_session_date=datetime.fromisoformat("2026-07-14T09:30:00+05:30").date(),
        event_timestamp=None,
        latest_session_date=latest_session_date,
        event_type="HOLD",
        lifecycle_status="PAPER_FRESH_ENTRY_REQUIRED",
        manager_status="PAPER_POSITION_FRESH_ENTRY_REQUIRED",
        fresh_entry_required=True,
        reverse_entry_required=False,
        rollover_required=False,
    ) is True
    assert paper_trade_visible_for_latest_session(
        row_session_date=datetime.fromisoformat("2026-07-14T09:30:00+05:30").date(),
        event_timestamp=None,
        latest_session_date=latest_session_date,
        event_type="CLOSE",
        lifecycle_status="PAPER_POSITION_CLOSED",
        manager_status="PAPER_POSITION_CLOSED",
        fresh_entry_required=False,
        reverse_entry_required=False,
        rollover_required=False,
    ) is False


@dataclass(frozen=True)
class _DisplayRow:
    event_timestamp: datetime | None
    event_type: str
    lifecycle_status: str
    manager_status: str


def test_paper_trade_select_display_row_prefers_latest_terminal_row() -> None:
    open_row = _DisplayRow(
        event_timestamp=datetime.fromisoformat("2026-07-15T09:30:00+05:30"),
        event_type="OPEN",
        lifecycle_status="PAPER_POSITION_OPEN",
        manager_status="PAPER_POSITION_OPENED",
    )
    later_action_row = _DisplayRow(
        event_timestamp=datetime.fromisoformat("2026-07-16T09:30:00+05:30"),
        event_type="ACTION_REQUIRED",
        lifecycle_status="PAPER_ROLLOVER_REQUIRED",
        manager_status="PAPER_POSITION_ROLLOVER_REQUIRED",
    )
    terminal_row = _DisplayRow(
        event_timestamp=datetime.fromisoformat("2026-07-15T12:57:59+05:30"),
        event_type="CLOSE",
        lifecycle_status="PAPER_POSITION_CLOSED",
        manager_status="PAPER_POSITION_CLOSED",
    )
    assert paper_trade_select_display_row(
        [open_row, later_action_row, terminal_row]
    ) == terminal_row


def test_paper_trade_select_display_row_falls_back_to_latest_row_without_terminal() -> None:
    older_row = _DisplayRow(
        event_timestamp=datetime.fromisoformat("2026-07-15T09:30:00+05:30"),
        event_type="OPEN",
        lifecycle_status="ORDER_WAITING_FOR_TRIGGER",
        manager_status="PAPER_ORDER_WAITING_FOR_TRIGGER",
    )
    newer_row = _DisplayRow(
        event_timestamp=datetime.fromisoformat("2026-07-15T12:57:59+05:30"),
        event_type="HOLD",
        lifecycle_status="PAPER_POSITION_OPEN",
        manager_status="PAPER_POSITION_HELD",
    )
    assert paper_trade_select_display_row([older_row, newer_row]) == newer_row


@dataclass(frozen=True)
class _SummaryRow:
    event_timestamp: datetime | None
    event_type: str
    lifecycle_status: str
    manager_status: str
    fresh_entry_required: bool = False
    reverse_entry_required: bool = False
    rollover_required: bool = False


@dataclass(frozen=True)
class _StatusRow:
    event_timestamp: datetime | None
    event_type: str
    lifecycle_status: str
    manager_status: str
    fresh_entry_required: bool = False
    reverse_entry_required: bool = False
    rollover_required: bool = False


def test_paper_trade_summary_counts_follow_shared_status_kinds() -> None:
    counts = paper_trade_summary_counts(
        [
            _SummaryRow(
                event_timestamp=datetime.fromisoformat("2026-07-15T09:30:00+05:30"),
                event_type="HOLD",
                lifecycle_status="PAPER_POSITION_OPEN",
                manager_status="PAPER_POSITION_HELD",
            ),
            _SummaryRow(
                event_timestamp=datetime.fromisoformat("2026-07-15T10:00:00+05:30"),
                event_type="ACTION_REQUIRED",
                lifecycle_status="PAPER_FRESH_ENTRY_REQUIRED",
                manager_status="PAPER_POSITION_FRESH_ENTRY_REQUIRED",
                fresh_entry_required=True,
            ),
            _SummaryRow(
                event_timestamp=datetime.fromisoformat("2026-07-15T12:57:59+05:30"),
                event_type="CLOSE",
                lifecycle_status="PAPER_POSITION_CLOSED",
                manager_status="PAPER_POSITION_CLOSED",
            ),
            _SummaryRow(
                event_timestamp=datetime.fromisoformat("2026-07-15T13:00:00+05:30"),
                event_type="OPEN",
                lifecycle_status="ORDER_WAITING_FOR_TRIGGER",
                manager_status="PAPER_ORDER_WAITING_FOR_TRIGGER",
            ),
        ]
    )
    assert counts == {
        "unique_trades": 4,
        "open_positions": 1,
        "action_required": 1,
        "closed_trades": 1,
    }


def test_paper_trade_status_labels_cover_closed_waiting_and_action_flags() -> None:
    assert paper_trade_status_labels(
        _StatusRow(
            event_timestamp=datetime.fromisoformat("2026-07-15T12:57:59+05:30"),
            event_type="CLOSE",
            lifecycle_status="PAPER_POSITION_CLOSED",
            manager_status="PAPER_POSITION_CLOSED",
        )
    ) == ["POSITION_CLOSED"]
    assert paper_trade_status_labels(
        _StatusRow(
            event_timestamp=datetime.fromisoformat("2026-07-15T09:30:00+05:30"),
            event_type="OPEN",
            lifecycle_status="ORDER_WAITING_FOR_TRIGGER",
            manager_status="PAPER_ORDER_WAITING_FOR_TRIGGER",
            fresh_entry_required=True,
        )
    ) == ["ORDER_WAITING_FOR_TRIGGER", "Fresh Entry"]


def test_paper_trade_followup_note_only_applies_to_terminal_rows() -> None:
    assert paper_trade_followup_note(
        _StatusRow(
            event_timestamp=datetime.fromisoformat("2026-07-15T09:30:00+05:30"),
            event_type="HOLD",
            lifecycle_status="PAPER_POSITION_OPEN",
            manager_status="PAPER_POSITION_HELD",
            fresh_entry_required=True,
        )
    ) == ""
    assert paper_trade_followup_note(
        _StatusRow(
            event_timestamp=datetime.fromisoformat("2026-07-15T12:57:59+05:30"),
            event_type="CLOSE",
            lifecycle_status="PAPER_POSITION_CLOSED",
            manager_status="PAPER_POSITION_CLOSED",
            fresh_entry_required=True,
            rollover_required=True,
        )
    ) == "Follow-up: fresh entry recalculation required; rollover review required."


def test_paper_trade_normalized_message_removes_s23_specific_prefix() -> None:
    assert paper_trade_normalized_message("") == ""
    assert (
        paper_trade_normalized_message(
            "S23 READY decision created a paper sell order."
        )
        == "READY decision created a paper sell order."
    )


def test_paper_trade_option_and_branch_labels_are_shared() -> None:
    assert paper_trade_option_label("NIFTY_20260721_24200_CE") == "CE"
    assert paper_trade_option_label("BANKNIFTY_20260825_58000_PE") == "PE"
    assert paper_trade_option_label("UNKNOWN") == "OPTION"
    assert paper_trade_branch_label("S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL") == "Bear Call"
    assert paper_trade_branch_label("S21_BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT") == "Bull Put"
    assert paper_trade_branch_label("custom_branch") == "Custom Branch"


def test_paper_trade_pnl_tone_is_shared() -> None:
    assert paper_trade_pnl_tone(None) == ""
    assert paper_trade_pnl_tone(10.0) == "good-text"
    assert paper_trade_pnl_tone(-5.0) == "bad-text"


def test_paper_trade_manager_status_helpers_are_shared() -> None:
    assert paper_trade_manager_status_is_open("PAPER_POSITION_OPENED") is True
    assert paper_trade_manager_status_is_open("PAPER_POSITION_HELD") is True
    assert paper_trade_manager_status_is_open("PAPER_POSITION_FORCE_CLOSED") is False
    assert paper_trade_manager_status_is_terminal("PAPER_POSITION_FORCE_CLOSED") is True
    assert paper_trade_manager_status_is_terminal("PAPER_POSITION_ALREADY_CLOSED") is True
    assert paper_trade_manager_status_is_terminal("PAPER_POSITION_FRESH_ENTRY_REQUIRED") is False
    assert paper_trade_manager_status_is_terminal("PAPER_POSITION_HELD") is False
    assert paper_trade_manager_status_is_lifecycle_terminal("PAPER_POSITION_FRESH_ENTRY_REQUIRED") is True
    assert paper_trade_manager_status_is_lifecycle_terminal("PAPER_POSITION_ROLLOVER_REQUIRED") is True


def test_paper_trade_event_type_for_manager_status_is_shared() -> None:
    assert paper_trade_event_type_for_manager_status("PAPER_POSITION_OPENED").value == "OPEN"
    assert paper_trade_event_type_for_manager_status("PAPER_POSITION_HELD").value == "HOLD"
    assert paper_trade_event_type_for_manager_status("PAPER_POSITION_FORCE_CLOSED").value == "CLOSE"
    assert paper_trade_event_type_for_manager_status("PAPER_POSITION_FRESH_ENTRY_REQUIRED").value == "CLOSE"
    assert paper_trade_event_type_for_manager_status("PAPER_POSITION_ROLLOVER_REQUIRED").value == "ACTION_REQUIRED"
