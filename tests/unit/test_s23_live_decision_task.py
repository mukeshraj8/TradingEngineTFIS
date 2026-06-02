from __future__ import annotations

from pathlib import Path

from tfis.paper import (
    S23MorningSupervisedTaskSpec,
    build_s23_morning_runner_arguments,
    build_s23_morning_wrapper_command,
)


def _spec() -> S23MorningSupervisedTaskSpec:
    return S23MorningSupervisedTaskSpec(
        task_name="TFIS S23 Morning Supervised Decision",
        repo_root=Path("D:/TradingEngineTFIS"),
        tradingengine_root=Path("D:/TradingEngineProd"),
        config_path=Path("config/paper.s23.fyers_connect_test.yaml"),
        strategy_path=Path("config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"),
        reference_packet_path=Path("config/reference_packets/s23_bear_put_live_decision_reference.json"),
        artifact_root=Path("tmp/s23_fyers_morning_supervised_decision"),
        session_id_prefix="s23-fyers-morning-supervised-decision",
        skip_refresh=True,
    )


def test_build_runner_arguments_includes_required_paths() -> None:
    spec = _spec()

    args = build_s23_morning_runner_arguments(spec)

    assert args[0].endswith("python.exe") or args[0].endswith("python")
    assert args[1].endswith("scripts\\run_s23_fyers_0916_supervised_decision.py")
    assert "--tradingengine-root" in args
    assert "D:\\TradingEngineProd" in args
    assert "--skip-refresh" in args


def test_build_wrapper_command_targets_wrapper_script() -> None:
    spec = _spec()

    command = build_s23_morning_wrapper_command(spec)

    assert "start_s23_fyers_morning_supervised_decision.ps1" in command
    assert "-TradingEngineRoot \"D:\\TradingEngineProd\"" in command
    assert "-SessionIdPrefix \"s23-fyers-morning-supervised-decision\"" in command
    assert " -SkipRefresh" in command


def test_build_wrapper_command_includes_optional_flags() -> None:
    spec = S23MorningSupervisedTaskSpec(
        task_name="TFIS S23 Morning Supervised Decision",
        repo_root=Path("D:/TradingEngineTFIS"),
        tradingengine_root=Path("D:/TradingEngineProd"),
        config_path=Path("config/paper.s23.fyers_connect_test.yaml"),
        strategy_path=Path("config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"),
        reference_packet_path=Path("config/reference_packets/s23_bear_put_live_decision_reference.json"),
        artifact_root=Path("tmp/s23_fyers_morning_supervised_decision"),
        session_id_prefix="s23-fyers-morning-supervised-decision",
        skip_refresh=False,
        enable_smoke_override=True,
        carry_forward_state_dir=Path("tmp/state"),
    )

    command = build_s23_morning_wrapper_command(spec)

    assert " -EnableSmokeOverride" in command
    assert " -CarryForwardStateDir \"tmp\\state\"" in command
