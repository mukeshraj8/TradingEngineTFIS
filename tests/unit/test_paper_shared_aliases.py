from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from tfis.domain import ExpiryType, OptionType, RolloverPolicy
from tfis.paper import (
    PaperBrokerAdapterConfig,
    PaperBrokerPaperIngressRunner,
    PaperBrokerCostSettingsConfig,
    PaperBrokerIngressThresholdConfig,
    PaperBrokerScopeConfig,
    PaperBrokerSelectionConfig,
    PaperCollectedSnapshotInputs,
    PaperFyersSnapshotArtifactSet,
    PaperFyersSnapshotCollector,
    PaperFyersSnapshotCollectorError,
    PaperFyersSnapshotPreflightIssue,
    PaperFyersSnapshotPreflightSummary,
    PaperFyersSnapshotPreludeProvenance,
    PaperDecisionReferencePacket,
    PaperDerivedRuntimeInputs,
    PaperGeneratedPreludeDryRunArtifactSet,
    PaperGeneratedPreludeDryRunError,
    PaperGeneratedPreludeDryRunProvenance,
    PaperGeneratedPreludeDryRunRunner,
    PaperGuardrailEvaluator,
    PaperGuardrailSettings,
    PaperHistoricalComparisonError,
    PaperHistoricalComparisonSummary,
    PaperHistoricalComparisonStatus,
    PaperHistoricalFieldComparison,
    PaperHistoricalMismatchSeverity,
    PaperLivePreludeBuilder,
    PaperLivePreludeError,
    PaperLivePreludeRequest,
    PaperLivePreludeResult,
    PaperLiveReferenceDerivationError,
    PaperLiveReferenceDerivationResult,
    PaperLiveReferenceDeriver,
    PaperLiveIngressArtifactSet,
    PaperMorningDecisionCheckpoint,
    PaperMorningDecisionRunResult,
    PaperMorningDecisionStageRun,
    build_paper_live_state_store,
    build_paper_live_state_store_from_yaml,
    build_paper_expiry_governance,
    build_paper_broker_adapter,
    build_paper_position_manager,
    FilesystemPaperLiveStateStore,
    FilesystemS23PaperLiveStateStore,
    build_s23_paper_live_state_store,
    build_s23_paper_live_state_store_from_yaml,
    InMemoryPaperLiveStateStore,
    InMemoryS23PaperLiveStateStore,
    load_paper_lifecycle_supervisor_target_specs,
    NullPaperLiveStateStore,
    NullS23PaperLiveStateStore,
    PaperExpiryGovernance,
    PaperExpiryGovernanceDecision,
    PaperLiveIngressConfig,
    PaperLiveIngressError,
    PaperLiveIngressPreflightIssue,
    PaperLiveIngressPreflightSummary,
    PaperLiveIngressSummary,
    PaperLiveDecisionRunResult,
    PaperLiveDecisionTimelineBuilder,
    PaperLiveDecisionTimelineCheckpoint,
    PaperLiveDecisionTimelineResult,
    PaperLiveDecisionTimelineStage,
    PaperLiveDecisionTimelineStageBuild,
    PaperLifecycleSupervisor,
    PaperLifecycleSupervisorContext,
    PaperLifecycleSupervisorResult,
    PaperLifecycleSupervisorStep,
    PaperLifecycleSupervisorTargetDiscovery,
    PaperLifecycleSupervisorTargetSpec,
    PaperLifecycleSupervisorWatchTarget,
    PaperLifecycleBrokerConfig,
    PaperLifecycleCostConfig,
    PaperLifecycleRuntimeConfig,
    PaperLifecycleRuntimeConfigError,
    PaperLiveStateSettings,
    PaperLiveStateStore,
    PaperOpenPositionCandidate,
    PaperOpenPositionDiscovery,
    paper_live_state_owner_id,
    paper_trade_action_required,
    paper_trade_branch_label,
    paper_trade_display_status_label,
    paper_trade_event_type_for_manager_status,
    paper_trade_followup_note,
    paper_trade_has_display_backing,
    paper_trade_is_open,
    paper_trade_ledger_candidate_paths,
    paper_trade_latest_active_rows,
    paper_trade_latest_historical_close_rows,
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
    run_paper_live_decision_check,
    run_paper_morning_supervised_decision,
    paper_order_is_terminal,
    paper_order_state_candidate_paths,
    paper_order_trade_event_type,
    paper_order_trade_lifecycle_status,
    paper_order_visible_for_latest_session,
    paper_order_visible_in_trade_monitor,
    paper_order_watchable_for_session,
    paper_order_is_waiting_for_trigger,
    RedisPaperLiveStateStore,
    RedisS23PaperLiveStateStore,
    PaperOrderEvent,
    PaperOrderFinalizer,
    PaperOrderFinalizerDecision,
    PaperOrderFinalizerSummary,
    PaperOrderPlan,
    PaperOrderStateCandidate,
    PaperOrderStateDiscovery,
    PaperOrderState,
    PaperOrderStateError,
    PaperOrderStateStore,
    PaperOrderStatus,
    PaperReplayBundleFile,
    PaperReplayBundleManager,
    PaperReplayBundleManifest,
    PaperReplayBundleSummary,
    PaperReplayBundleValidationResult,
    PaperReviewAuditStep,
    PaperReviewBundleStatus,
    PaperReviewDataProvenance,
    PaperReviewError,
    PaperReviewFillPhase,
    PaperReviewFreshness,
    PaperReviewGuardrail,
    PaperReviewLifecyclePhase,
    PaperReviewOrderIntent,
    PaperReviewOrderPlan,
    PaperReviewRuntimeContracts,
    PaperReviewSelectedContract,
    PaperReviewSummary,
    PaperSessionReviewer,
    PaperPositionState,
    PaperPositionStateError,
    PaperPositionStateEvent,
    PaperPositionStateEventType,
    PaperPositionStateStatus,
    PaperPositionStateStore,
    PaperPositionManager,
    PaperPositionManagerError,
    PaperPositionManagerEvent,
    PaperPositionManagerResult,
    PaperPositionManagerStatus,
    PaperPreludeSessionContext,
    PaperPreludeMode,
    PaperSessionOrchestrator,
    PaperSessionSnapshot,
    PaperMarketReferencePacket,
    PaperMonthlyStatusReferencePacket,
    PaperContractValidator,
    PaperRuntimeInputDerivationError,
    PaperRuntimeInputDeriver,
    PaperSnapshotInput,
    PaperSnapshotOptionChainStatistics,
    PaperSnapshotValidationAggregateMetrics,
    PaperSnapshotValidationArtifactSet,
    PaperSnapshotValidationHarness,
    PaperSnapshotValidationReport,
    PaperSessionManifestBuilder,
    PaperSnapshotValidationSample,
    PaperSnapshotValidationWarning,
    load_paper_decision_reference_packet,
    S23PaperLifecycleSupervisor,
    S23PaperLifecycleSupervisorContext,
    S23PaperLifecycleSupervisorResult,
    S23PaperLifecycleSupervisorStep,
    S23BrokerAdapterConfig,
    S23BrokerPaperIngressRunner,
    S23BrokerCostSettingsConfig,
    S23BrokerIngressThresholdConfig,
    S23PaperBrokerScopeConfig,
    S23BrokerSelectionConfig,
    S23PaperExpiryGovernance,
    S23PaperExpiryGovernanceDecision,
    S23PaperLiveStateSettings,
    S23PaperLiveStateStore,
    S23LivePaperIngressArtifactSet,
    S23LivePaperIngressConfig,
    S23LivePaperIngressError,
    S23LivePaperIngressPreflightIssue,
    S23LivePaperIngressPreflightSummary,
    S23LivePaperIngressSummary,
    S23LiveDecisionRunResult,
    S23LiveDecisionTimelineBuilder,
    S23LiveDecisionTimelineCheckpoint,
    S23LiveDecisionTimelineResult,
    S23LiveDecisionTimelineStage,
    S23LiveDecisionTimelineStageBuild,
    S23MorningDecisionCheckpoint,
    S23MorningDecisionRunResult,
    S23MorningDecisionStageRun,
    S23OpenPaperPositionCandidate,
    S23OpenPaperPositionDiscovery,
    S23PaperOrderEvent,
    S23PaperOrderFinalizer,
    S23PaperOrderFinalizerDecision,
    S23PaperOrderFinalizerSummary,
    S23PaperOrderPlan,
    S23PaperSessionOrchestrator,
    S23PaperSessionSnapshot,
    S23PaperOrderState,
    S23PaperOrderStateError,
    S23PaperOrderStateStore,
    S23PaperOrderStatus,
    S23PaperReplayBundleFile,
    S23PaperReplayBundleManager,
    S23PaperReplayBundleManifest,
    S23PaperReplayBundleSummary,
    S23PaperReplayBundleValidationResult,
    S23PaperReviewAuditStep,
    S23PaperReviewBundleStatus,
    S23PaperReviewDataProvenance,
    S23PaperReviewError,
    S23PaperReviewFillPhase,
    S23PaperReviewFreshness,
    S23PaperReviewGuardrail,
    S23PaperReviewLifecyclePhase,
    S23PaperReviewOrderIntent,
    S23PaperReviewOrderPlan,
    S23PaperReviewRuntimeContracts,
    S23PaperReviewSelectedContract,
    S23PaperReviewSummary,
    S23PaperSessionReviewer,
    S23PaperPositionState,
    S23PaperPositionStateError,
    S23PaperPositionStateEvent,
    S23PaperPositionStateEventType,
    S23PaperPositionStateStatus,
    S23PaperPositionStateStore,
    S23PaperPositionManager,
    S23PaperPositionManagerError,
    S23PaperPositionManagerEvent,
    S23PaperPositionManagerResult,
    S23PaperPositionManagerStatus,
    S23CollectedSnapshotInputs,
    S23DecisionReferencePacket,
    S23DerivedRuntimeInputs,
    S23FyersSnapshotArtifactSet,
    S23FyersSnapshotCollector,
    S23FyersSnapshotCollectorError,
    S23FyersSnapshotPreflightIssue,
    S23FyersSnapshotPreflightSummary,
    S23FyersSnapshotPreludeProvenance,
    S23GeneratedPreludeDryRunArtifactSet,
    S23GeneratedPreludeDryRunError,
    S23GeneratedPreludeDryRunProvenance,
    S23GeneratedPreludeDryRunRunner,
    S23PaperContractValidator,
    S23PaperGuardrailEvaluator,
    S23PaperGuardrailSettings,
    S23PaperHistoricalComparisonError,
    S23PaperHistoricalComparisonSummary,
    S23PaperHistoricalFieldComparison,
    S23LiveReferenceDerivationError,
    S23LiveReferenceDerivationResult,
    S23LiveReferenceDeriver,
    S23LivePreludeError,
    S23PaperPreludeSessionContext,
    S23PaperLivePreludeBuilder,
    S23PaperLivePreludeRequest,
    S23PaperLivePreludeResult,
    S23PaperPreludeMode,
    S23PaperSnapshotInput,
    S23SnapshotOptionChainStatistics,
    S23SnapshotValidationAggregateMetrics,
    S23SnapshotValidationArtifactSet,
    S23SnapshotValidationHarness,
    S23SnapshotValidationReport,
    S23SnapshotValidationSample,
    S23SnapshotValidationWarning,
    S23PaperSessionManifestBuilder,
    S23MarketReferencePacket,
    S23MonthlyStatusReferencePacket,
    S23RuntimeInputDerivationError,
    S23RuntimeInputDeriver,
    load_s23_decision_reference_packet,
    run_s23_live_decision_check,
    run_s23_morning_supervised_decision,
    s23_live_state_owner_id,
)


def test_paper_order_finalizer_aliases_point_to_existing_s23_types() -> None:
    assert PaperOrderFinalizer is S23PaperOrderFinalizer
    assert PaperOrderFinalizerDecision is S23PaperOrderFinalizerDecision
    assert PaperOrderFinalizerSummary is S23PaperOrderFinalizerSummary


def test_paper_orchestrator_aliases_point_to_existing_s23_types() -> None:
    assert PaperOrderPlan is S23PaperOrderPlan
    assert PaperSessionOrchestrator is S23PaperSessionOrchestrator
    assert PaperSessionSnapshot is S23PaperSessionSnapshot


def test_paper_lifecycle_supervisor_aliases_point_to_existing_s23_types() -> None:
    assert PaperLifecycleSupervisor is S23PaperLifecycleSupervisor
    assert PaperLifecycleSupervisorContext is S23PaperLifecycleSupervisorContext
    assert PaperLifecycleSupervisorResult is S23PaperLifecycleSupervisorResult
    assert PaperLifecycleSupervisorStep is S23PaperLifecycleSupervisorStep


def test_paper_open_position_discovery_aliases_point_to_existing_s23_types() -> None:
    assert PaperOpenPositionCandidate is S23OpenPaperPositionCandidate
    assert PaperOpenPositionDiscovery is S23OpenPaperPositionDiscovery


def test_paper_open_position_discovery_shared_blocking_scan_finds_open_and_reverse_required_positions(
    tmp_path,
) -> None:
    store = S23PaperPositionStateStore()
    open_dir = tmp_path / "open"
    reverse_dir = tmp_path / "reverse"
    closed_dir = tmp_path / "closed"
    open_dir.mkdir()
    reverse_dir.mkdir()
    closed_dir.mkdir()

    open_state = store.create_open_position_state(
        strategy_code="S23",
        unique_code="OPEN_BRANCH",
        symbol="NIFTY",
        option_type=OptionType.CALL,
        selected_contract_symbol="NIFTY_20260723_24150_CE",
        expiry_date=date(2026, 7, 23),
        expiry_type=ExpiryType.WEEKLY,
        rollover_policy=RolloverPolicy.T_MINUS_1,
        forced_close_time=None,
        no_carry_past_expiry=True,
        entry_date=date(2026, 7, 20),
        entry_timestamp=datetime(2026, 7, 20, 9, 30),
        entry_price=194.25,
        lots=1,
        quantity=65,
        side="SELL",
        target_price=77.70,
        stoploss_price=242.0,
        fsl_price=None,
        trp_price=None,
        carry_forward_allowed=True,
        last_updated_timestamp=datetime(2026, 7, 20, 9, 30),
    )
    store.save_state(open_dir, open_state)

    reverse_state = store.create_open_position_state(
        strategy_code="S23",
        unique_code="REVERSE_BRANCH",
        symbol="NIFTY",
        option_type=OptionType.PUT,
        selected_contract_symbol="NIFTY_20260723_24150_PE",
        expiry_date=date(2026, 7, 23),
        expiry_type=ExpiryType.WEEKLY,
        rollover_policy=RolloverPolicy.T_MINUS_1,
        forced_close_time=None,
        no_carry_past_expiry=True,
        entry_date=date(2026, 7, 20),
        entry_timestamp=datetime(2026, 7, 20, 9, 31),
        entry_price=209.0,
        lots=1,
        quantity=65,
        side="SELL",
        target_price=85.10,
        stoploss_price=258.94,
        fsl_price=None,
        trp_price=None,
        carry_forward_allowed=True,
        last_updated_timestamp=datetime(2026, 7, 20, 9, 31),
    )
    store.save_state(reverse_dir, reverse_state)
    store.mark_position_closed(
        reverse_dir,
        session_date=date(2026, 7, 20),
        closed_at=datetime(2026, 7, 20, 10, 15),
        reason_code="reverse_entry_required",
        message="Reverse entry required.",
        reverse_entry_required=True,
    )

    closed_state = store.create_open_position_state(
        strategy_code="S23",
        unique_code="CLOSED_BRANCH",
        symbol="NIFTY",
        option_type=OptionType.PUT,
        selected_contract_symbol="NIFTY_20260723_24200_PE",
        expiry_date=date(2026, 7, 23),
        expiry_type=ExpiryType.WEEKLY,
        rollover_policy=RolloverPolicy.T_MINUS_1,
        forced_close_time=None,
        no_carry_past_expiry=True,
        entry_date=date(2026, 7, 20),
        entry_timestamp=datetime(2026, 7, 20, 9, 32),
        entry_price=212.0,
        lots=1,
        quantity=65,
        side="SELL",
        target_price=86.0,
        stoploss_price=260.0,
        fsl_price=None,
        trp_price=None,
        carry_forward_allowed=True,
        last_updated_timestamp=datetime(2026, 7, 20, 9, 32),
    )
    store.save_state(closed_dir, closed_state)
    store.mark_position_closed(
        closed_dir,
        session_date=date(2026, 7, 20),
        closed_at=datetime(2026, 7, 20, 10, 16),
        reason_code="target_hit",
        message="Closed cleanly.",
        fresh_entry_required=False,
    )

    candidates = PaperOpenPositionDiscovery().find_positions_blocking_new_entry((tmp_path,))

    assert {candidate.state_directory.name for candidate in candidates} == {"open", "reverse"}


def test_paper_live_state_aliases_point_to_existing_s23_types() -> None:
    assert PaperLiveStateSettings is S23PaperLiveStateSettings
    assert PaperLiveStateStore is S23PaperLiveStateStore
    assert InMemoryPaperLiveStateStore is InMemoryS23PaperLiveStateStore
    assert FilesystemPaperLiveStateStore is FilesystemS23PaperLiveStateStore
    assert NullPaperLiveStateStore is NullS23PaperLiveStateStore
    assert RedisPaperLiveStateStore is RedisS23PaperLiveStateStore
    assert callable(build_paper_live_state_store)
    assert callable(build_paper_live_state_store_from_yaml)


def test_paper_live_state_owner_id_alias_returns_s23_owner_shape() -> None:
    assert paper_live_state_owner_id("tfis-test").startswith("tfis-test:")
    assert s23_live_state_owner_id("tfis-test").startswith("tfis-test:")


def test_phase3_supervisor_runtime_symbols_are_exported() -> None:
    assert PaperLifecycleSupervisorTargetSpec.__name__ == "PaperLifecycleSupervisorTargetSpec"
    assert PaperLifecycleSupervisorTargetDiscovery.__name__ == "PaperLifecycleSupervisorTargetDiscovery"
    assert PaperLifecycleSupervisorWatchTarget.__name__ == "PaperLifecycleSupervisorWatchTarget"
    assert callable(load_paper_lifecycle_supervisor_target_specs)
    assert PaperLifecycleBrokerConfig.__name__ == "PaperLifecycleBrokerConfig"
    assert PaperLifecycleCostConfig.__name__ == "PaperLifecycleCostConfig"
    assert PaperLifecycleRuntimeConfig.__name__ == "PaperLifecycleRuntimeConfig"
    assert PaperLifecycleRuntimeConfigError.__name__ == "PaperLifecycleRuntimeConfigError"
    assert callable(build_paper_broker_adapter)


def test_paper_expiry_governance_aliases_point_to_existing_s23_types() -> None:
    assert PaperExpiryGovernance is S23PaperExpiryGovernance
    assert PaperExpiryGovernanceDecision is S23PaperExpiryGovernanceDecision
    assert callable(build_paper_expiry_governance)


def test_paper_position_manager_aliases_point_to_existing_s23_types() -> None:
    assert PaperPositionManager is S23PaperPositionManager
    assert PaperPositionManagerError is S23PaperPositionManagerError
    assert PaperPositionManagerEvent is S23PaperPositionManagerEvent
    assert PaperPositionManagerResult is S23PaperPositionManagerResult
    assert PaperPositionManagerStatus is S23PaperPositionManagerStatus
    assert callable(build_paper_position_manager)


def test_paper_live_ingress_config_aliases_point_to_existing_s23_types() -> None:
    assert PaperBrokerAdapterConfig is S23BrokerAdapterConfig
    assert PaperBrokerScopeConfig is S23PaperBrokerScopeConfig
    assert PaperBrokerSelectionConfig is S23BrokerSelectionConfig
    assert PaperBrokerCostSettingsConfig is S23BrokerCostSettingsConfig
    assert PaperBrokerIngressThresholdConfig is S23BrokerIngressThresholdConfig
    assert PaperBrokerPaperIngressRunner is S23BrokerPaperIngressRunner
    assert PaperLiveIngressArtifactSet is S23LivePaperIngressArtifactSet
    assert PaperLiveIngressConfig is S23LivePaperIngressConfig
    assert PaperLiveIngressError is S23LivePaperIngressError
    assert PaperLiveIngressPreflightIssue is S23LivePaperIngressPreflightIssue
    assert PaperLiveIngressPreflightSummary is S23LivePaperIngressPreflightSummary
    assert PaperLiveIngressSummary is S23LivePaperIngressSummary


def test_paper_morning_decision_aliases_point_to_existing_s23_types() -> None:
    assert PaperMorningDecisionCheckpoint is S23MorningDecisionCheckpoint
    assert PaperMorningDecisionRunResult is S23MorningDecisionRunResult
    assert PaperMorningDecisionStageRun is S23MorningDecisionStageRun
    assert run_paper_morning_supervised_decision is run_s23_morning_supervised_decision


def test_paper_live_decision_aliases_point_to_existing_s23_types() -> None:
    assert PaperLiveDecisionRunResult is S23LiveDecisionRunResult
    assert run_paper_live_decision_check is run_s23_live_decision_check


def test_paper_live_decision_timeline_aliases_point_to_existing_s23_types() -> None:
    assert PaperLiveDecisionTimelineBuilder is S23LiveDecisionTimelineBuilder
    assert PaperLiveDecisionTimelineCheckpoint is S23LiveDecisionTimelineCheckpoint
    assert PaperLiveDecisionTimelineResult is S23LiveDecisionTimelineResult
    assert PaperLiveDecisionTimelineStage is S23LiveDecisionTimelineStage
    assert PaperLiveDecisionTimelineStageBuild is S23LiveDecisionTimelineStageBuild


def test_paper_snapshot_and_prelude_read_models_alias_existing_s23_types() -> None:
    assert PaperCollectedSnapshotInputs is S23CollectedSnapshotInputs
    assert PaperPreludeSessionContext is S23PaperPreludeSessionContext
    assert PaperSnapshotInput is S23PaperSnapshotInput


def test_paper_prelude_builder_aliases_point_to_existing_s23_types() -> None:
    assert PaperLivePreludeBuilder is S23PaperLivePreludeBuilder
    assert PaperLivePreludeError is S23LivePreludeError
    assert PaperLivePreludeRequest is S23PaperLivePreludeRequest
    assert PaperLivePreludeResult is S23PaperLivePreludeResult
    assert PaperPreludeMode is S23PaperPreludeMode


def test_paper_fyers_snapshot_aliases_point_to_existing_s23_types() -> None:
    assert PaperFyersSnapshotArtifactSet is S23FyersSnapshotArtifactSet
    assert PaperFyersSnapshotCollector is S23FyersSnapshotCollector
    assert PaperFyersSnapshotCollectorError is S23FyersSnapshotCollectorError
    assert PaperFyersSnapshotPreflightIssue is S23FyersSnapshotPreflightIssue
    assert PaperFyersSnapshotPreflightSummary is S23FyersSnapshotPreflightSummary
    assert PaperFyersSnapshotPreludeProvenance is S23FyersSnapshotPreludeProvenance


def test_paper_generated_prelude_dry_run_aliases_point_to_existing_s23_types() -> None:
    assert PaperGeneratedPreludeDryRunArtifactSet is S23GeneratedPreludeDryRunArtifactSet
    assert PaperGeneratedPreludeDryRunError is S23GeneratedPreludeDryRunError
    assert PaperGeneratedPreludeDryRunProvenance is S23GeneratedPreludeDryRunProvenance
    assert PaperGeneratedPreludeDryRunRunner is S23GeneratedPreludeDryRunRunner


def test_paper_guardrail_aliases_point_to_existing_s23_types() -> None:
    assert PaperGuardrailEvaluator is S23PaperGuardrailEvaluator
    assert PaperGuardrailSettings is S23PaperGuardrailSettings


def test_paper_runtime_input_aliases_point_to_existing_s23_types() -> None:
    assert PaperDecisionReferencePacket is S23DecisionReferencePacket
    assert PaperDerivedRuntimeInputs is S23DerivedRuntimeInputs
    assert PaperMarketReferencePacket is S23MarketReferencePacket
    assert PaperMonthlyStatusReferencePacket is S23MonthlyStatusReferencePacket
    assert PaperRuntimeInputDerivationError is S23RuntimeInputDerivationError
    assert PaperRuntimeInputDeriver is S23RuntimeInputDeriver
    assert load_paper_decision_reference_packet is load_s23_decision_reference_packet


def test_paper_live_reference_derivation_aliases_point_to_existing_s23_types() -> None:
    assert PaperLiveReferenceDerivationError is S23LiveReferenceDerivationError
    assert PaperLiveReferenceDerivationResult is S23LiveReferenceDerivationResult
    assert PaperLiveReferenceDeriver is S23LiveReferenceDeriver


def test_paper_validation_aliases_point_to_existing_s23_types() -> None:
    assert PaperContractValidator is S23PaperContractValidator
    assert PaperSessionManifestBuilder is S23PaperSessionManifestBuilder


def test_paper_review_aliases_point_to_existing_s23_types() -> None:
    assert PaperReviewError is S23PaperReviewError
    assert PaperReviewAuditStep is S23PaperReviewAuditStep
    assert PaperReviewGuardrail is S23PaperReviewGuardrail
    assert PaperReviewSelectedContract is S23PaperReviewSelectedContract
    assert PaperReviewOrderPlan is S23PaperReviewOrderPlan
    assert PaperReviewOrderIntent is S23PaperReviewOrderIntent
    assert PaperReviewFillPhase is S23PaperReviewFillPhase
    assert PaperReviewLifecyclePhase is S23PaperReviewLifecyclePhase
    assert PaperReviewDataProvenance is S23PaperReviewDataProvenance
    assert PaperReviewFreshness is S23PaperReviewFreshness
    assert PaperReviewBundleStatus is S23PaperReviewBundleStatus
    assert PaperReviewRuntimeContracts is S23PaperReviewRuntimeContracts
    assert PaperReviewSummary is S23PaperReviewSummary
    assert PaperSessionReviewer is S23PaperSessionReviewer


def test_paper_replay_bundle_aliases_point_to_existing_s23_types() -> None:
    assert PaperReplayBundleFile is S23PaperReplayBundleFile
    assert PaperReplayBundleManifest is S23PaperReplayBundleManifest
    assert PaperReplayBundleValidationResult is S23PaperReplayBundleValidationResult
    assert PaperReplayBundleSummary is S23PaperReplayBundleSummary
    assert PaperReplayBundleManager is S23PaperReplayBundleManager


def test_paper_historical_comparison_aliases_point_to_existing_s23_types() -> None:
    assert PaperHistoricalComparisonError is S23PaperHistoricalComparisonError
    assert PaperHistoricalFieldComparison is S23PaperHistoricalFieldComparison
    assert PaperHistoricalComparisonSummary is S23PaperHistoricalComparisonSummary


def test_paper_snapshot_validation_aliases_point_to_existing_s23_types() -> None:
    assert PaperSnapshotOptionChainStatistics is S23SnapshotOptionChainStatistics
    assert PaperSnapshotValidationAggregateMetrics is S23SnapshotValidationAggregateMetrics
    assert PaperSnapshotValidationArtifactSet is S23SnapshotValidationArtifactSet
    assert PaperSnapshotValidationHarness is S23SnapshotValidationHarness
    assert PaperSnapshotValidationReport is S23SnapshotValidationReport
    assert PaperSnapshotValidationSample is S23SnapshotValidationSample
    assert PaperSnapshotValidationWarning is S23SnapshotValidationWarning


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
    assert paper_order_trade_event_type(S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER) == "ORDER_WAITING"
    assert paper_order_trade_event_type(S23PaperOrderStatus.PAPER_ORDER_NOT_FILLED) == "ORDER_NOT_FILLED"
    assert paper_order_trade_lifecycle_status("PAPER_ORDER_WAITING_FOR_TRIGGER") == "ORDER_WAITING_FOR_TRIGGER"
    assert paper_order_trade_lifecycle_status("PAPER_ORDER_NOT_FILLED") == "ORDER_NOT_FILLED"
    assert (
        paper_order_trade_lifecycle_status(S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER)
        == "ORDER_WAITING_FOR_TRIGGER"
    )
    assert (
        paper_order_trade_lifecycle_status(S23PaperOrderStatus.PAPER_ORDER_NOT_FILLED)
        == "ORDER_NOT_FILLED"
    )
    assert paper_order_visible_in_trade_monitor("PAPER_ORDER_WAITING_FOR_TRIGGER") is True
    assert paper_order_visible_in_trade_monitor("PAPER_ORDER_NOT_FILLED") is True
    assert paper_order_visible_in_trade_monitor(S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER) is True
    assert paper_order_visible_in_trade_monitor(S23PaperOrderStatus.PAPER_ORDER_NOT_FILLED) is True
    assert paper_order_watchable_for_session(
        status="PAPER_ORDER_WAITING_FOR_TRIGGER",
        entry_date=date(2026, 7, 20),
        effective_session_date=date(2026, 7, 20),
    ) is True
    assert paper_order_watchable_for_session(
        status="PAPER_ORDER_WAITING_FOR_TRIGGER",
        entry_date=date(2026, 7, 17),
        effective_session_date=date(2026, 7, 20),
    ) is False
    assert paper_order_watchable_for_session(
        status="PAPER_ORDER_NOT_FILLED",
        entry_date=date(2026, 7, 20),
        effective_session_date=date(2026, 7, 20),
    ) is False
    assert paper_order_visible_for_latest_session(
        status="PAPER_ORDER_WAITING_FOR_TRIGGER",
        entry_date=date(2026, 7, 20),
        latest_session_date=date(2026, 7, 20),
    ) is True
    assert paper_order_visible_for_latest_session(
        status=S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER,
        entry_date=date(2026, 7, 20),
        latest_session_date=date(2026, 7, 20),
    ) is True
    assert paper_order_visible_for_latest_session(
        status="PAPER_ORDER_WAITING_FOR_TRIGGER",
        entry_date=date(2026, 7, 17),
        latest_session_date=date(2026, 7, 20),
    ) is False
    assert paper_order_visible_for_latest_session(
        status="PAPER_ORDER_NOT_FILLED",
        entry_date=date(2026, 7, 17),
        latest_session_date=date(2026, 7, 20),
    ) is False
    assert paper_order_visible_in_trade_monitor("PAPER_ORDER_FILLED") is False


def test_paper_order_state_discovery_finds_same_strategy_orders(tmp_path) -> None:
    order_dir = tmp_path / "orders" / "session-a"
    order_dir.mkdir(parents=True)
    (order_dir / "paper_order_state.json").write_text(
        """
{
  "artifact_version": 1,
  "strategy_code": "S23",
  "strategy_branch": "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
  "symbol": "NIFTY",
  "selected_contract_symbol": "NIFTY_20260721_23950_CE",
  "selected_contract_expiry": "2026-07-21",
  "selected_contract_option_type": "CALL",
  "selected_contract_strike": 23950,
  "expiry_type": "WEEKLY",
  "rollover_policy": "T_MINUS_1",
  "forced_close_time": "12:00:00",
  "no_carry_past_expiry": true,
  "order_side": "SELL",
  "trigger_rule": "SELL_TRIGGER_WHEN_PREMIUM_AT_OR_BELOW_ENTRY",
  "entry_date": "2026-07-20",
  "order_timestamp": "2026-07-20T09:30:00+05:30",
  "planned_entry_price": 212.75,
  "target_price": 85.10,
  "stoploss_price": 258.94,
  "fsl_price": null,
  "lots": 1,
  "quantity": 65,
  "status": "PAPER_ORDER_WAITING_FOR_TRIGGER",
  "last_updated_timestamp": "2026-07-20T09:30:00+05:30"
}
""".strip(),
        encoding="utf-8",
    )

    candidates = PaperOrderStateDiscovery().find_orders(
        (tmp_path / "orders",),
        strategy_code="S23",
    )

    assert len(candidates) == 1
    assert isinstance(candidates[0], PaperOrderStateCandidate)
    assert candidates[0].state_directory == order_dir.resolve()
    assert candidates[0].state.strategy_code == "S23"


def test_paper_order_state_candidate_paths_collect_and_sort_unique_paths(tmp_path) -> None:
    first = tmp_path / "a" / "paper_order_state.json"
    second = tmp_path / "b" / "nested" / "paper_order_state.json"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")

    result = paper_order_state_candidate_paths((tmp_path / "b", tmp_path / "a", tmp_path / "a"))

    assert result == tuple(sorted((first, second)))


def test_paper_trade_ledger_candidate_paths_include_session_and_global_ledgers(
    tmp_path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    session_dir = artifact_root / "2026-07-20" / "session-a"
    session_dir.mkdir(parents=True)
    session_ledger = session_dir / "paper_trade_ledger.jsonl"
    session_ledger.write_text("", encoding="utf-8")
    repo_root = tmp_path / "repo"
    global_dir = repo_root / "tmp" / "paper_trade_ledger"
    global_dir.mkdir(parents=True)
    global_ledger = global_dir / "s23_paper_trade_ledger.jsonl"
    global_ledger.write_text("", encoding="utf-8")

    result = paper_trade_ledger_candidate_paths(
        artifact_root=artifact_root,
        strategy_code="S23",
        repo_root=repo_root,
    )

    assert result == tuple(sorted((session_ledger, global_ledger)))


def test_paper_open_position_discovery_finds_latest_terminal_position(tmp_path) -> None:
    older_dir = tmp_path / "positions" / "older"
    newer_dir = tmp_path / "positions" / "newer"
    older_dir.mkdir(parents=True)
    newer_dir.mkdir(parents=True)
    (older_dir / "paper_position_state.json").write_text(
        """
{
  "artifact_version": 1,
  "strategy_code": "S23",
  "unique_code": "NIFTY_OP_SELL_WK_DIFF_2D_3D",
  "symbol": "NIFTY",
  "option_type": "CALL",
  "selected_contract_symbol": "NIFTY_20260721_24200_CE",
  "expiry_date": "2026-07-21",
  "expiry_type": "WEEKLY",
  "entry_date": "2026-07-08",
  "entry_timestamp": "2026-07-08T12:24:59+05:30",
  "entry_price": 209.0,
  "lots": 1,
  "quantity": 65,
  "side": "SELL",
  "target_price": 85.10,
  "stoploss_price": 258.94,
  "fsl_price": null,
  "trp_price": null,
  "carry_forward_allowed": true,
  "no_carry_past_expiry": true,
  "lifecycle_status": "PAPER_POSITION_CLOSED",
  "last_updated_timestamp": "2026-07-15T12:57:59+05:30",
  "provenance_source_ids": []
}
""".strip(),
        encoding="utf-8",
    )
    (newer_dir / "paper_position_state.json").write_text(
        """
{
  "artifact_version": 1,
  "strategy_code": "S23",
  "unique_code": "NIFTY_OP_SELL_WK_DIFF_2D_3D",
  "symbol": "NIFTY",
  "option_type": "PUT",
  "selected_contract_symbol": "NIFTY_20260721_24350_PE",
  "expiry_date": "2026-07-21",
  "expiry_type": "WEEKLY",
  "entry_date": "2026-07-09",
  "entry_timestamp": "2026-07-09T12:24:59+05:30",
  "entry_price": 194.25,
  "lots": 1,
  "quantity": 65,
  "side": "SELL",
  "target_price": 77.70,
  "stoploss_price": 242.0,
  "fsl_price": null,
  "trp_price": null,
  "carry_forward_allowed": true,
  "no_carry_past_expiry": true,
  "lifecycle_status": "PAPER_FRESH_ENTRY_REQUIRED",
  "last_updated_timestamp": "2026-07-16T12:57:59+05:30",
  "provenance_source_ids": []
}
""".strip(),
        encoding="utf-8",
    )

    candidate = PaperOpenPositionDiscovery().find_latest_terminal_position((tmp_path / "positions",))

    assert candidate is not None
    assert candidate.state_directory == newer_dir
    assert candidate.lifecycle_status == "PAPER_FRESH_ENTRY_REQUIRED"


def test_paper_position_status_helpers_cover_enum_and_string_inputs() -> None:
    assert paper_position_is_active(S23PaperPositionStateStatus.PAPER_POSITION_OPEN) is True
    assert paper_position_is_active("PAPER_POSITION_CARRIED_FORWARD") is True
    assert paper_position_is_active(S23PaperPositionStateStatus.PAPER_POSITION_CLOSED) is False
    assert paper_position_blocks_new_entry("PAPER_POSITION_RESUMED") is True
    assert paper_position_blocks_new_entry("PAPER_REVERSE_ENTRY_REQUIRED") is False
    assert paper_position_blocks_new_entry("PAPER_FRESH_ENTRY_REQUIRED") is False
    assert paper_position_is_no_longer_open(S23PaperPositionStateStatus.PAPER_POSITION_CLOSED) is True
    assert paper_position_is_no_longer_open("PAPER_REVERSE_ENTRY_REQUIRED") is True
    assert paper_position_is_no_longer_open("PAPER_POSITION_OPEN") is False


def test_paper_trade_latest_session_visibility_hides_terminal_rows() -> None:
    assert paper_trade_visible_for_latest_session(
        row_session_date=date(2026, 7, 17),
        event_timestamp=datetime(2026, 7, 17, 9, 17, 59),
        latest_session_date=date(2026, 7, 17),
        event_type="CLOSE",
        lifecycle_status="PAPER_REVERSE_ENTRY_REQUIRED",
        manager_status="PAPER_POSITION_REVERSE_ENTRY_REQUIRED",
        fresh_entry_required=False,
        reverse_entry_required=True,
        rollover_required=False,
    ) is False
    assert paper_trade_visible_for_latest_session(
        row_session_date=date(2026, 7, 17),
        event_timestamp=datetime(2026, 7, 17, 10, 23, 15),
        latest_session_date=date(2026, 7, 17),
        event_type="ORDER_WAITING",
        lifecycle_status="ORDER_WAITING_FOR_TRIGGER",
        manager_status="PAPER_ORDER_WAITING_FOR_TRIGGER",
        fresh_entry_required=False,
        reverse_entry_required=False,
        rollover_required=False,
    ) is True


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


def test_paper_trade_display_backing_allows_terminal_rows_without_live_state_file(
    tmp_path,
) -> None:
    terminal_dir = tmp_path / "terminal"
    terminal_dir.mkdir()
    active_dir = tmp_path / "active"
    active_dir.mkdir()
    (active_dir / "paper_position_state.json").write_text("{}", encoding="utf-8")

    assert paper_trade_has_display_backing(
        terminal_dir,
        event_type="CLOSE",
        lifecycle_status="PAPER_FRESH_ENTRY_REQUIRED",
        manager_status="PAPER_POSITION_FRESH_ENTRY_REQUIRED",
    ) is True
    assert paper_trade_has_display_backing(
        terminal_dir,
        event_type="HOLD",
        lifecycle_status="PAPER_POSITION_OPEN",
        manager_status="PAPER_POSITION_HELD",
    ) is False
    assert paper_trade_has_display_backing(
        active_dir,
        event_type="HOLD",
        lifecycle_status="PAPER_POSITION_OPEN",
        manager_status="PAPER_POSITION_HELD",
    ) is True


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
    ) is False
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
    trade_id: str = "T"
    strategy_code: str = "S23"


@dataclass(frozen=True)
class _StatusRow:
    event_timestamp: datetime | None
    event_type: str
    lifecycle_status: str
    manager_status: str
    fresh_entry_required: bool = False
    reverse_entry_required: bool = False
    rollover_required: bool = False
    trade_id: str = "T"
    strategy_code: str = "S23"


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


def test_paper_trade_latest_active_rows_use_shared_display_and_visibility_rules() -> None:
    latest_session_date = datetime.fromisoformat("2026-07-15T09:30:00+05:30").date()
    rows = [
        _StatusRow(
            trade_id="T1",
            event_timestamp=datetime.fromisoformat("2026-07-14T09:30:00+05:30"),
            event_type="OPEN",
            lifecycle_status="PAPER_POSITION_OPEN",
            manager_status="PAPER_POSITION_OPENED",
        ),
        _StatusRow(
            trade_id="T1",
            event_timestamp=datetime.fromisoformat("2026-07-15T12:57:59+05:30"),
            event_type="CLOSE",
            lifecycle_status="PAPER_POSITION_CLOSED",
            manager_status="PAPER_POSITION_CLOSED",
        ),
        _StatusRow(
            trade_id="T2",
            event_timestamp=datetime.fromisoformat("2026-07-14T12:00:00+05:30"),
            event_type="ACTION_REQUIRED",
            lifecycle_status="PAPER_FRESH_ENTRY_REQUIRED",
            manager_status="PAPER_POSITION_FRESH_ENTRY_REQUIRED",
            fresh_entry_required=True,
        ),
    ]

    latest_rows = paper_trade_latest_active_rows(
        rows,
        latest_session_date=latest_session_date,
    )

    assert [row.trade_id for row in latest_rows] == ["T2"]


def test_paper_trade_latest_historical_close_rows_keep_latest_close_per_strategy_trade() -> None:
    historical_rows = paper_trade_latest_historical_close_rows(
        [
            _StatusRow(
                trade_id="T1",
                strategy_code="S23",
                event_timestamp=datetime.fromisoformat("2026-07-15T12:57:59+05:30"),
                event_type="CLOSE",
                lifecycle_status="PAPER_POSITION_CLOSED",
                manager_status="PAPER_POSITION_CLOSED",
            ),
            _StatusRow(
                trade_id="T1",
                strategy_code="S23",
                event_timestamp=datetime.fromisoformat("2026-07-15T13:05:00+05:30"),
                event_type="CLOSE",
                lifecycle_status="PAPER_POSITION_CLOSED",
                manager_status="PAPER_POSITION_CLOSED",
            ),
            _StatusRow(
                trade_id="T1",
                strategy_code="S21",
                event_timestamp=datetime.fromisoformat("2026-07-15T12:57:59+05:30"),
                event_type="CLOSE",
                lifecycle_status="PAPER_POSITION_CLOSED",
                manager_status="PAPER_POSITION_CLOSED",
            ),
            _StatusRow(
                trade_id="T2",
                strategy_code="S23",
                event_timestamp=datetime.fromisoformat("2026-07-15T11:00:00+05:30"),
                event_type="HOLD",
                lifecycle_status="PAPER_POSITION_OPEN",
                manager_status="PAPER_POSITION_HELD",
            ),
        ]
    )

    assert [
        (row.strategy_code, row.trade_id, row.event_timestamp)
        for row in historical_rows
    ] == [
        ("S23", "T1", datetime.fromisoformat("2026-07-15T13:05:00+05:30")),
        ("S21", "T1", datetime.fromisoformat("2026-07-15T12:57:59+05:30")),
    ]


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
