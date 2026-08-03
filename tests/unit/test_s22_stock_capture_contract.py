from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "capture_s22_reliance_fyers_snapshot.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("capture_s22_stock_snapshot", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_s22_capture_contract_defaults_to_reliance_but_accepts_other_symbols() -> None:
    module = _load_script_module()

    assert module.DEFAULT_SYMBOL == "RELIANCE"
    assert module._normalized_symbol(" infy ") == "INFY"
    assert module._fyers_underlying_symbol("TCS") == "NSE:TCS-EQ"


def test_s22_capture_gap_codes_are_symbol_specific() -> None:
    module = _load_script_module()
    expiry = SimpleNamespace(near_monthly_expiry=None, next_monthly_expiry=None)
    history = SimpleNamespace(status=object(), payload=SimpleNamespace(candles=()))

    gaps = module._required_gaps("INFY", (), expiry, history, ())

    assert "INFY_SYMBOL_MASTER_RECORDS_MISSING" in gaps
    assert "INFY_OPTION_CONTRACTS_MISSING" in gaps
    assert "INFY_COMPLETED_DAILY_HISTORY_MISSING" in gaps
    assert "INFY_OPTION_CHAIN_MISSING" in gaps
