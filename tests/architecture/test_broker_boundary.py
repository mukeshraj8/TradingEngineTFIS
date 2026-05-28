from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE_DIRS = [
    ROOT / "src" / "tfis" / "domain",
    ROOT / "src" / "tfis" / "formulas",
    ROOT / "src" / "tfis" / "rules",
    ROOT / "src" / "tfis" / "strategy",
    ROOT / "src" / "tfis" / "market_structure",
    ROOT / "src" / "tfis" / "risk",
]
FORBIDDEN_TERMS = (
    "fyers",
    "zerodha",
    "kite",
    "angel",
    "upstox",
    "PaperBroker",
    "tfis.broker.paper_broker",
    "place_order(",
    "get_positions(",
    "access_token",
    "client_id",
    "fyersModel",
    "KiteConnect",
    "SmartConnect",
    "Upstox",
)


def _python_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        files.extend(sorted(path.rglob("*.py")))
    return files


def test_core_modules_do_not_reference_forbidden_broker_terms() -> None:
    violations: list[str] = []

    for file_path in _python_files(CORE_DIRS):
        content = file_path.read_text(encoding="utf-8")
        lowered = content.lower()
        for term in FORBIDDEN_TERMS:
            haystack = content if any(ch.isupper() for ch in term) else lowered
            needle = term if any(ch.isupper() for ch in term) else term.lower()
            if needle in haystack:
                violations.append(
                    f"Forbidden term '{term}' found in {file_path.relative_to(ROOT)}"
                )

    assert not violations, "\n".join(violations)


def test_strategy_evaluator_does_not_import_from_tfis_broker_layers() -> None:
    strategy_evaluator = ROOT / "src" / "tfis" / "strategy" / "strategy_evaluator.py"
    content = strategy_evaluator.read_text(encoding="utf-8")

    assert "from tfis.broker" not in content, (
        "Forbidden term 'from tfis.broker' found in "
        f"{strategy_evaluator.relative_to(ROOT)}"
    )
    assert "import tfis.broker" not in content, (
        "Forbidden term 'import tfis.broker' found in "
        f"{strategy_evaluator.relative_to(ROOT)}"
    )
    assert "from tfis.brokers" not in content, (
        "Forbidden term 'from tfis.brokers' found in "
        f"{strategy_evaluator.relative_to(ROOT)}"
    )
    assert "import tfis.brokers" not in content, (
        "Forbidden term 'import tfis.brokers' found in "
        f"{strategy_evaluator.relative_to(ROOT)}"
    )
