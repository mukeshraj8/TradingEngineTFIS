from __future__ import annotations

from pathlib import Path

from tfis.paper import (
    S23MorningSupervisedTaskSpec,
    build_s23_morning_runner_arguments,
    build_s23_morning_wrapper_command,
)


DURABLE_S23_ARTIFACT_ROOT = Path("data/strategies/S23/fyers_morning_supervised_decision")


def _spec() -> S23MorningSupervisedTaskSpec:
    return S23MorningSupervisedTaskSpec(
        task_name="TFIS S23 Morning Supervised Decision",
        repo_root=Path("D:/TradingEngineTFIS"),
        tfis_root=Path("D:/TradingEngineTFIS"),
        config_path=Path("config/paper.s23.fyers_connect_test.yaml"),
        strategy_path=Path("config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"),
        reference_packet_path=Path("config/reference_packets/s23_bear_put_live_decision_reference.json"),
        artifact_root=DURABLE_S23_ARTIFACT_ROOT,
        session_id_prefix="s23-fyers-morning-supervised-decision",
        skip_refresh=True,
    )


def test_build_runner_arguments_includes_required_paths() -> None:
    spec = _spec()

    args = build_s23_morning_runner_arguments(spec)

    assert args[0].endswith("python.exe") or args[0].endswith("python")
    assert args[1].endswith("scripts\\run_s23_fyers_0916_supervised_decision.py")
    assert "--tfis-root" in args
    assert "D:\\TradingEngineTFIS" in args
    assert str(DURABLE_S23_ARTIFACT_ROOT) in args
    assert "--skip-refresh" in args


def test_build_wrapper_command_targets_wrapper_script() -> None:
    spec = _spec()

    command = build_s23_morning_wrapper_command(spec)

    assert "start_s23_fyers_morning_supervised_decision.ps1" in command
    assert "-TfisRoot \"D:\\TradingEngineTFIS\"" in command
    assert "-SessionIdPrefix \"s23-fyers-morning-supervised-decision\"" in command
    assert " -SkipRefresh" in command


def test_build_wrapper_command_includes_optional_flags() -> None:
    spec = S23MorningSupervisedTaskSpec(
        task_name="TFIS S23 Morning Supervised Decision",
        repo_root=Path("D:/TradingEngineTFIS"),
        tfis_root=Path("D:/TradingEngineTFIS"),
        config_path=Path("config/paper.s23.fyers_connect_test.yaml"),
        strategy_path=Path("config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"),
        reference_packet_path=Path("config/reference_packets/s23_bear_put_live_decision_reference.json"),
        artifact_root=DURABLE_S23_ARTIFACT_ROOT,
        session_id_prefix="s23-fyers-morning-supervised-decision",
        skip_refresh=False,
        enable_smoke_override=True,
        carry_forward_state_dir=Path("tmp/state"),
    )

    command = build_s23_morning_wrapper_command(spec)

    assert " -EnableSmokeOverride" in command
    assert " -CarryForwardStateDir \"tmp\\state\"" in command


def test_build_runner_arguments_preserve_windows_carry_forward_path_as_one_argument() -> None:
    carry_forward_path = Path(
        "D:/TradingDataPaper/strategies/S23/fyers_morning_supervised_decision/"
        "2026-07-03/session/NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
    )
    spec = S23MorningSupervisedTaskSpec(
        task_name="TFIS S23 Morning Supervised Decision",
        repo_root=Path("D:/TradingEngineTFIS"),
        tfis_root=Path("D:/TradingEngineTFIS"),
        config_path=Path("config/paper.s23.fyers_connect_test.yaml"),
        strategy_path=Path("config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"),
        reference_packet_path=Path("config/reference_packets/s23_bear_put_live_decision_reference.json"),
        artifact_root=DURABLE_S23_ARTIFACT_ROOT,
        session_id_prefix="s23-fyers-morning-supervised-decision",
        carry_forward_state_dir=carry_forward_path,
    )

    args = build_s23_morning_runner_arguments(spec)

    carry_forward_index = args.index("--carry-forward-state-dir") + 1
    assert args[carry_forward_index] == str(carry_forward_path)
    assert args[carry_forward_index] != "D"


def test_build_wrapper_command_quotes_windows_carry_forward_path() -> None:
    carry_forward_path = Path(
        "D:/TradingDataPaper/strategies/S23/fyers_morning_supervised_decision/"
        "2026-07-03/session/NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
    )
    spec = S23MorningSupervisedTaskSpec(
        task_name="TFIS S23 Morning Supervised Decision",
        repo_root=Path("D:/TradingEngineTFIS"),
        tfis_root=Path("D:/TradingEngineTFIS"),
        config_path=Path("config/paper.s23.fyers_connect_test.yaml"),
        strategy_path=Path("config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"),
        reference_packet_path=Path("config/reference_packets/s23_bear_put_live_decision_reference.json"),
        artifact_root=DURABLE_S23_ARTIFACT_ROOT,
        session_id_prefix="s23-fyers-morning-supervised-decision",
        carry_forward_state_dir=carry_forward_path,
    )

    command = build_s23_morning_wrapper_command(spec)

    assert f' -CarryForwardStateDir "{carry_forward_path}"' in command
    assert ' -CarryForwardStateDir "D"' not in command
