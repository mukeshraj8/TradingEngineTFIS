from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_generic_runtime_contracts_remain_broker_and_strategy_neutral() -> None:
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

    for source_path in (
        REPO_ROOT / "src/tfis/domain/runtime_contracts.py",
        REPO_ROOT / "src/tfis/domain/decision_evidence.py",
    ):
        source = source_path.read_text(encoding="utf-8")
        assert all(term not in source for term in forbidden_terms), source_path
