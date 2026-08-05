from __future__ import annotations

from importlib import import_module
from typing import Any

from .registry import EnabledStrategyInstance, EnabledStrategyRegistry, load_enabled_strategy_registry


__all__ = [
    "AuthoritativeReadinessProjectionResult",
    "CompleteSessionPreflightResult",
    "ContinuousSupervisorRunResult",
    "EnabledStrategyInstance",
    "EnabledStrategyRegistry",
    "LiveObservationResult",
    "LiveMarketInternalPaperReportResult",
    "MultiStrategyRuntimeCoordinator",
    "build_live_market_internal_paper_reports",
    "build_unified_runtime_reports",
    "build_authoritative_readiness_projection",
    "load_enabled_strategy_registry",
    "run_complete_session_preflight",
    "run_continuous_supervisor",
    "run_live_observation",
]


_LAZY_IMPORTS = {
    "AuthoritativeReadinessProjectionResult": (".supervisor", "AuthoritativeReadinessProjectionResult"),
    "CompleteSessionPreflightResult": (".supervisor", "CompleteSessionPreflightResult"),
    "ContinuousSupervisorRunResult": (".supervisor", "ContinuousSupervisorRunResult"),
    "build_authoritative_readiness_projection": (".supervisor", "build_authoritative_readiness_projection"),
    "run_complete_session_preflight": (".supervisor", "run_complete_session_preflight"),
    "run_continuous_supervisor": (".supervisor", "run_continuous_supervisor"),
    "LiveMarketInternalPaperReportResult": (".live_market_internal_paper", "LiveMarketInternalPaperReportResult"),
    "build_live_market_internal_paper_reports": (".live_market_internal_paper", "build_live_market_internal_paper_reports"),
    "LiveObservationResult": (".live_observation", "LiveObservationResult"),
    "run_live_observation": (".live_observation", "run_live_observation"),
    "MultiStrategyRuntimeCoordinator": (".coordinator", "MultiStrategyRuntimeCoordinator"),
    "build_unified_runtime_reports": (".coordinator", "build_unified_runtime_reports"),
}


def __getattr__(name: str) -> Any:
    module_info = _LAZY_IMPORTS.get(name)
    if module_info is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = module_info
    module = import_module(module_name, __name__)
    value = getattr(module, attribute)
    globals()[name] = value
    return value
