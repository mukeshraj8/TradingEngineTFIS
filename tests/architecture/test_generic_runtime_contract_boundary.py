from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_generic_runtime_contracts_remain_broker_and_strategy_neutral() -> None:
    source_path = REPO_ROOT / "src/tfis/domain/runtime_contracts.py"
    source = source_path.read_text(encoding="utf-8")

    forbidden_terms = (
        "S21",
        "S23",
        "FYERS",
        "NIFTY",
        "BANKNIFTY",
        "tfis.paper",
        "tfis.brokers",
        "tfis.broker",
    )

    assert all(term not in source for term in forbidden_terms)
