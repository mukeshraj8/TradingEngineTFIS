from __future__ import annotations

from datetime import date
from pathlib import Path

from tfis.paper.session_discovery import (
    PaperSupervisedStageArtifactPaths,
    find_latest_supervised_session_dir,
    find_preferred_supervised_stage_dir,
    find_supervised_final_session_dir,
    find_supervised_stage_dirs,
    iter_session_branch_dirs,
    iter_session_branch_explainer_paths,
    iter_strategy_day_dirs,
    iter_trade_decision_summary_paths,
    resolve_supervised_stage_artifact_paths,
    supervised_session_is_complete,
    supervised_session_metadata_path,
)


def test_iter_strategy_day_dirs_filters_and_sorts_descending(tmp_path: Path) -> None:
    (tmp_path / "2026-07-19").mkdir()
    (tmp_path / "2026-07-20").mkdir()
    (tmp_path / "notes").mkdir()

    result = iter_strategy_day_dirs(tmp_path)

    assert result == (
        tmp_path / "2026-07-20",
        tmp_path / "2026-07-19",
    )


def test_find_supervised_session_dirs_and_summary_paths(tmp_path: Path) -> None:
    day_dir = tmp_path / "2026-07-20"
    day_dir.mkdir()
    final_dir = day_dir / "s23-fyers-morning-supervised-decision-2026-07-20"
    final_dir.mkdir()
    stage_dir = day_dir / "s23-fyers-morning-supervised-decision-0916-2026-07-20"
    stage_dir.mkdir()
    (stage_dir / "snapshot_preflight_summary.json").write_text("{}", encoding="utf-8")
    branch_dir = final_dir / "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    branch_dir.mkdir()
    summary_path = branch_dir / "trade_decision_summary.json"
    summary_path.write_text("{}", encoding="utf-8")

    assert find_supervised_final_session_dir(
        day_dir,
        session_id_prefix="s23-fyers-morning-supervised-decision",
    ) == final_dir
    assert find_supervised_stage_dirs(
        day_dir,
        session_id_prefix="s23-fyers-morning-supervised-decision",
    ) == (stage_dir,)
    assert iter_trade_decision_summary_paths(final_dir) == (summary_path,)


def test_iter_session_branch_dirs_and_explainer_paths(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    branch_a = session_dir / "A_BRANCH"
    branch_b = session_dir / "B_BRANCH"
    branch_a.mkdir()
    branch_b.mkdir()
    final_explainer = branch_a / "trade_decision_explainer.json"
    final_explainer.write_text("{}", encoding="utf-8")
    stage_explainer = branch_b / "trade_decision_explainer_stage_0930.json"
    stage_explainer.write_text("{}", encoding="utf-8")

    assert iter_session_branch_dirs(session_dir) == (branch_a, branch_b)
    assert iter_session_branch_explainer_paths(session_dir) == (
        final_explainer,
        stage_explainer,
    )


def test_find_latest_supervised_session_dir_prefers_latest_matching_session(tmp_path: Path) -> None:
    day_dir = tmp_path / "2026-07-20"
    day_dir.mkdir()
    earlier = day_dir / "s23-fyers-morning-supervised-decision-2026-07-20"
    earlier.mkdir()
    later = day_dir / "s23-fyers-morning-supervised-decision-rerun-2026-07-20"
    later.mkdir()
    earlier.touch()
    later.touch()

    result = find_latest_supervised_session_dir(
        day_dir,
        session_date=date(2026, 7, 20),
        session_id_prefix="s23-fyers-morning-supervised-decision",
    )

    assert result == later


def test_find_preferred_supervised_stage_dir_prefers_0930_then_latest(tmp_path: Path) -> None:
    day_dir = tmp_path / "2026-07-21"
    day_dir.mkdir()
    stage_0916 = day_dir / "s23-fyers-morning-supervised-decision-0916-2026-07-21"
    stage_0925 = day_dir / "s23-fyers-morning-supervised-decision-0925-2026-07-21"
    stage_0930 = day_dir / "s23-fyers-morning-supervised-decision-0930-2026-07-21"
    for path in (stage_0916, stage_0925, stage_0930):
        path.mkdir()
        (path / "snapshot_preflight_summary.json").write_text("{}", encoding="utf-8")

    assert find_preferred_supervised_stage_dir(
        day_dir,
        session_id_prefix="s23-fyers-morning-supervised-decision",
    ) == stage_0930

    stage_0930.joinpath("snapshot_preflight_summary.json").unlink()

    assert find_preferred_supervised_stage_dir(
        day_dir,
        session_id_prefix="s23-fyers-morning-supervised-decision",
    ) == stage_0925


def test_resolve_supervised_stage_artifact_paths_builds_expected_names(tmp_path: Path) -> None:
    final_session_dir = tmp_path / "s23-fyers-morning-supervised-decision-2026-07-21"
    final_session_dir.mkdir()

    result = resolve_supervised_stage_artifact_paths(
        final_session_dir,
        stage_key="0925",
    )

    assert result == PaperSupervisedStageArtifactPaths(
        monthly_status_stage_json=final_session_dir / "monthly_status_stage_0925.json",
        trade_decision_explainer_stage_json=(
            final_session_dir / "trade_decision_explainer_stage_0925.json"
        ),
    )


def test_supervised_session_metadata_helpers_follow_metadata_presence(tmp_path: Path) -> None:
    session_dir = tmp_path / "s23-fyers-morning-supervised-decision-2026-07-21"
    session_dir.mkdir()

    assert supervised_session_metadata_path(session_dir) == (
        session_dir / "scheduled_run_metadata.json"
    )
    assert supervised_session_is_complete(session_dir) is False

    (session_dir / "scheduled_run_metadata.json").write_text("{}", encoding="utf-8")

    assert supervised_session_is_complete(session_dir) is True
