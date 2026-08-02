from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTH_ROOT = REPO_ROOT / "src" / "tfis" / "broker" / "authentication"
DIAGNOSTIC_ROOT = REPO_ROOT / "src" / "tfis" / "broker" / "diagnostics"


def _source_files(root: Path) -> tuple[Path, ...]:
    return tuple(path for path in root.rglob("*.py") if path.name != "__pycache__")


def test_broker_authentication_and_diagnostics_do_not_expose_order_write_surface() -> None:
    prohibited = (
        "place_order",
        "modify_order",
        "cancel_order",
        "exit_positions",
        "convert_position",
    )

    for path in _source_files(AUTH_ROOT) + _source_files(DIAGNOSTIC_ROOT):
        source = path.read_text(encoding="utf-8")
        assert not any(term in source for term in prohibited), path


def test_fyers_sdk_import_is_confined_to_fyers_authentication_adapter() -> None:
    sdk_mentions = [
        path
        for path in _source_files(AUTH_ROOT) + _source_files(DIAGNOSTIC_ROOT)
        if "fyers_apiv3" in path.read_text(encoding="utf-8")
    ]

    assert sdk_mentions == [AUTH_ROOT / "fyers.py"]
