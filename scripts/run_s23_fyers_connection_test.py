from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tfis.paper import S23FyersSnapshotCollector, S23FyersSnapshotCollectorError


DEFAULT_TRADINGENGINE_ROOT = Path(r"D:\TradingEngineProd")
DEFAULT_CONFIG = REPO_ROOT / "config" / "paper.s23.fyers_connect_test.yaml"
DEFAULT_STRATEGY = (
    REPO_ROOT
    / "config"
    / "strategies"
    / "options_sell"
    / "nifty"
    / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh FYERS auth via TradingEngine automation and run a one-shot "
            "TFIS S23 paper snapshot connection test."
        )
    )
    parser.add_argument(
        "--tradingengine-root",
        default=str(DEFAULT_TRADINGENGINE_ROOT),
        help="Path to the existing TradingEngine project that owns FYERS auth automation.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="TFIS paper snapshot config to use for the connection test.",
    )
    parser.add_argument(
        "--strategy-path",
        default=str(DEFAULT_STRATEGY),
        help="TFIS strategy folder or strategy YAML path.",
    )
    parser.add_argument(
        "--artifact-root",
        default="tmp/s23_fyers_connection_test",
        help="Artifact root for TFIS snapshot outputs.",
    )
    parser.add_argument(
        "--session-id",
        default="s23-fyers-connection-test",
        help="Stable session id for the connection test run.",
    )
    parser.add_argument(
        "--runtime-fixture",
        help=(
            "Optional runtime fixture JSON. When provided with "
            "--dry-run-build-prelude, the script rebases the fixture to the "
            "current session date before building the generated prelude."
        ),
    )
    parser.add_argument(
        "--dry-run-build-prelude",
        action="store_true",
        help="Build generated live prelude artifacts from the collected FYERS snapshot.",
    )
    parser.add_argument(
        "--carry-forward-state-dir",
        help="Optional directory containing paper_position_state.json for resume-mode preludes.",
    )
    parser.add_argument(
        "--enable-smoke-override",
        action="store_true",
        help="Allow config.market.selected_contract_symbol to act as an explicit smoke override.",
    )
    parser.add_argument(
        "--skip-refresh",
        action="store_true",
        help="Use the existing TradingEngine token_store.json without refreshing the token first.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    te_root = Path(args.tradingengine_root)
    env_path = te_root / ".env"
    token_path = te_root / "data" / "token_store.json"
    refresh_script = te_root / "scripts" / "fyers_token_refresh.py"
    te_python = te_root / ".venv" / "Scripts" / "python.exe"

    _require_exists(te_root, "TradingEngine root")
    _require_exists(env_path, "TradingEngine .env")
    _require_exists(token_path, "TradingEngine token_store.json")
    _require_exists(refresh_script, "TradingEngine FYERS token refresh script")

    if not args.skip_refresh:
        refresh_python = te_python if te_python.exists() else Path(sys.executable)
        result = subprocess.run(
            [str(refresh_python), str(refresh_script)],
            cwd=str(te_root),
            check=False,
            text=True,
        )
        if result.returncode != 0:
            print(
                "ERROR: TradingEngine FYERS token refresh failed. "
                "Fix that first before testing TFIS connectivity.",
                file=sys.stderr,
            )
            return result.returncode

    env_values = _read_env_file(env_path)
    token_payload = json.loads(token_path.read_text(encoding="utf-8"))
    access_token = str(token_payload.get("access_token") or "").strip()
    app_id = str(env_values.get("FYERS_APP_ID") or "").strip()
    client_id = str(env_values.get("FYERS_CLIENT_ID") or "").strip()
    if not app_id or not access_token:
        print(
            "ERROR: TradingEngine auth artifacts are incomplete. "
            "Need FYERS_APP_ID in .env and access_token in token_store.json.",
            file=sys.stderr,
        )
        return 1

    os.environ["FYERS_APP_ID"] = app_id
    os.environ["FYERS_ACCESS_TOKEN"] = access_token
    if client_id:
        os.environ["FYERS_CLIENT_ID"] = client_id

    collector = S23FyersSnapshotCollector(artifact_root=args.artifact_root)
    runtime_fixture_path = args.runtime_fixture
    if args.dry_run_build_prelude:
        if not runtime_fixture_path:
            print(
                "ERROR: --dry-run-build-prelude requires --runtime-fixture.",
                file=sys.stderr,
            )
            return 1
        runtime_fixture_path = _prepare_runtime_fixture_for_current_session(
            Path(runtime_fixture_path),
            artifact_root=Path(args.artifact_root),
            session_id=args.session_id,
        )
    try:
        artifact_set = collector.collect_from_files(
            config_path=args.config,
            strategy_path=args.strategy_path,
            runtime_fixture_path=runtime_fixture_path,
            carry_forward_state_dir=args.carry_forward_state_dir,
            session_id=args.session_id,
            dry_run_build_prelude=args.dry_run_build_prelude,
            enable_smoke_override=args.enable_smoke_override,
        )
    except S23FyersSnapshotCollectorError as exc:
        print(f"ERROR [{exc.code}]: {exc}", file=sys.stderr)
        return 1

    print("FYERS connection test succeeded.")
    print(f"Snapshot session directory: {artifact_set.session_directory}")
    print(f"Snapshot summary: {artifact_set.summary_path}")
    print(f"Normalized underlying snapshot: {artifact_set.normalized_underlying_snapshot_path}")
    print(f"Normalized option-chain snapshot: {artifact_set.normalized_option_chain_snapshot_path}")
    if artifact_set.generated_prelude_events_path is not None:
        print(f"Generated prelude events: {artifact_set.generated_prelude_events_path}")
    if artifact_set.generated_prelude_provenance_path is not None:
        print(f"Generated prelude provenance: {artifact_set.generated_prelude_provenance_path}")
    if artifact_set.generated_governance_events_path is not None:
        print(f"Generated governance events: {artifact_set.generated_governance_events_path}")
    summary_json_path, summary_md_path = _write_operator_summary(
        artifact_set=artifact_set,
        tradingengine_root=te_root,
        token_path=token_path,
        dry_run_build_prelude=args.dry_run_build_prelude,
    )
    print(f"Operator summary (JSON): {summary_json_path}")
    print(f"Operator summary (Markdown): {summary_md_path}")
    return 0


def _require_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"Missing {label}: {path}")


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _prepare_runtime_fixture_for_current_session(
    source_path: Path,
    *,
    artifact_root: Path,
    session_id: str,
) -> Path:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    timezone_name = str(payload.get("timezone") or "Asia/Kolkata")
    tzinfo = ZoneInfo(timezone_name)
    now = datetime.now(tz=tzinfo)
    session_date = now.date().isoformat()
    payload["session_date"] = session_date
    payload["generated_at"] = now.isoformat()
    if payload.get("weekly_expiry"):
        payload["weekly_expiry"] = str(payload["weekly_expiry"])
    for snapshot in payload.get("snapshots", []):
        if not isinstance(snapshot, dict):
            continue
        for key in ("bar_start", "bar_end"):
            value = snapshot.get(key)
            if not value:
                continue
            timestamp = datetime.fromisoformat(str(value))
            snapshot[key] = timestamp.replace(
                year=now.year,
                month=now.month,
                day=now.day,
            ).isoformat()

    prepared_dir = artifact_root / "_prepared_runtime_fixtures"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    prepared_path = prepared_dir / f"{session_id}_runtime_fixture.json"
    prepared_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return prepared_path


def _write_operator_summary(
    *,
    artifact_set,
    tradingengine_root: Path,
    token_path: Path,
    dry_run_build_prelude: bool,
) -> tuple[Path, Path]:
    summary = artifact_set.summary
    prelude = artifact_set.prelude_result
    selected_contract = None
    selection_reason = None
    selection_failure_code = None
    if prelude is not None and prelude.contract_selection is not None:
        selected_contract = prelude.contract_selection.selected_contract_symbol
        selection_reason = prelude.contract_selection.selection_reason
        selection_failure_code = (
            prelude.contract_selection.failure_code.value
            if prelude.contract_selection.failure_code is not None
            else None
        )
    selected_payload = None
    if prelude is not None and prelude.selected_contract_event is not None:
        selected_payload = {
            "symbol": prelude.selected_contract_event.symbol,
            "expiry": prelude.selected_contract_event.expiry.isoformat(),
            "strike": prelude.selected_contract_event.strike,
            "option_type": prelude.selected_contract_event.option_type.value,
            "ltp": prelude.selected_contract_event.ltp,
            "oi": prelude.selected_contract_event.oi,
            "bid": prelude.selected_contract_event.bid,
            "ask": prelude.selected_contract_event.ask,
        }

    payload = {
        "status": "READY" if summary.can_run else "NO_GO",
        "session_id": summary.session_id,
        "session_date": summary.session_date.isoformat(),
        "provider": summary.provider,
        "strategy_code": summary.strategy_code,
        "strategy_branch_reference": summary.strategy_branch_reference,
        "symbol": summary.symbol,
        "weekly_expiry": summary.weekly_expiry.isoformat(),
        "underlying_quote_collected": summary.underlying_quote_collected,
        "option_chain_collected": summary.option_chain_collected,
        "option_chain_contract_count": summary.option_chain_contract_count,
        "option_chain_has_complete_oi": summary.option_chain_has_complete_oi,
        "prelude_generated": summary.prelude_generated,
        "prelude_mode": prelude.mode.value if prelude is not None else None,
        "contract_selection_source": (
            "runtime_option_chain_selector"
            if prelude is not None and prelude.selected_contract_provenance == "runtime_option_chain_selection"
            else prelude.selected_contract_provenance
            if prelude is not None
            else None
        ),
        "selected_contract": selected_payload,
        "selection_reason": selection_reason,
        "selection_failure_code": selection_failure_code,
        "token_source": str(token_path),
        "tradingengine_root": str(tradingengine_root),
        "snapshot_summary_path": str(artifact_set.summary_path),
        "normalized_underlying_snapshot_path": str(artifact_set.normalized_underlying_snapshot_path),
        "normalized_option_chain_snapshot_path": str(artifact_set.normalized_option_chain_snapshot_path),
        "generated_prelude_events_path": (
            str(artifact_set.generated_prelude_events_path)
            if artifact_set.generated_prelude_events_path is not None
            else None
        ),
        "generated_prelude_provenance_path": (
            str(artifact_set.generated_prelude_provenance_path)
            if artifact_set.generated_prelude_provenance_path is not None
            else None
        ),
        "notes": [
            "This is a one-shot live snapshot plus paper-prelude readiness check.",
            "No FYERS socket loop is started.",
            "No broker order is placed.",
            "No lifecycle execution is performed.",
            (
                "Generated S23 prelude was built from live FYERS normalized data and a runtime smoke fixture."
                if dry_run_build_prelude
                else "Only live FYERS snapshot preflight was run."
            ),
        ],
    }

    json_path = artifact_set.session_directory / "operator_readiness_summary.json"
    md_path = artifact_set.session_directory / "operator_readiness_summary.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    md_lines = [
        "# S23 FYERS Operator Readiness Summary",
        "",
        "## Status",
        f"- Status: `{payload['status']}`",
        f"- Session Date: `{payload['session_date']}`",
        f"- Session ID: `{payload['session_id']}`",
        f"- Strategy: `{payload['strategy_code']}` / `{payload['strategy_branch_reference']}`",
        f"- Symbol: `{payload['symbol']}`",
        f"- Weekly Expiry: `{payload['weekly_expiry']}`",
        "",
        "## Market Data Checks",
        f"- Underlying Quote Collected: `{payload['underlying_quote_collected']}`",
        f"- Option Chain Collected: `{payload['option_chain_collected']}`",
        f"- Option Chain Contract Count: `{payload['option_chain_contract_count']}`",
        f"- Complete OI Available: `{payload['option_chain_has_complete_oi']}`",
        "",
        "## Prelude",
        f"- Prelude Generated: `{payload['prelude_generated']}`",
        f"- Prelude Mode: `{payload['prelude_mode'] or 'n/a'}`",
        f"- Contract Selection Source: `{payload['contract_selection_source'] or 'n/a'}`",
    ]
    if selected_payload is not None:
        md_lines.extend(
            [
                "",
                "## Selected Contract",
                f"- Symbol: `{selected_payload['symbol']}`",
                f"- Expiry: `{selected_payload['expiry']}`",
                f"- Strike: `{selected_payload['strike']}`",
                f"- Option Type: `{selected_payload['option_type']}`",
                f"- LTP: `{selected_payload['ltp']}`",
                f"- OI: `{selected_payload['oi']}`",
                f"- Bid / Ask: `{selected_payload['bid']}` / `{selected_payload['ask']}`",
                f"- Selection Reason: `{selection_reason or 'n/a'}`",
            ]
        )
    else:
        md_lines.extend(
            [
                "",
                "## Selected Contract",
                f"- Selection Failure Code: `{selection_failure_code or 'n/a'}`",
                f"- Selection Reason: `{selection_reason or 'n/a'}`",
            ]
        )
    md_lines.extend(
        [
            "",
            "## Artifacts",
            f"- Snapshot Summary: `{artifact_set.summary_path}`",
            f"- Underlying Snapshot: `{artifact_set.normalized_underlying_snapshot_path}`",
            f"- Option Chain Snapshot: `{artifact_set.normalized_option_chain_snapshot_path}`",
            f"- Generated Prelude Events: `{artifact_set.generated_prelude_events_path or 'n/a'}`",
            f"- Generated Prelude Provenance: `{artifact_set.generated_prelude_provenance_path or 'n/a'}`",
            "",
            "## Safety",
            "- No socket loop was started.",
            "- No broker order was placed.",
            "- No lifecycle execution was performed.",
            "",
            "## Credential Source",
            f"- TradingEngine Root: `{tradingengine_root}`",
            f"- Token Store: `{token_path}`",
        ]
    )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return json_path, md_path


if __name__ == "__main__":
    raise SystemExit(main())
