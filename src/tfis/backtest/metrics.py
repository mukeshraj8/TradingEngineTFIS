from __future__ import annotations

from tfis.backtest.models import BacktestMetrics, BacktestTradeResult


def build_backtest_metrics(results: list[BacktestTradeResult]) -> BacktestMetrics:
    rejection_reasons: dict[str, int] = {}
    accepted = 0
    rejected = 0

    for result in results:
        if result.accepted:
            accepted += 1
            continue
        rejected += 1
        rejection_reasons[result.reason] = rejection_reasons.get(result.reason, 0) + 1

    return BacktestMetrics(
        total_candidates=len(results),
        accepted_trades=accepted,
        rejected_trades=rejected,
        rejection_reasons=rejection_reasons,
    )
