from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from tfis.formulas import FormulaSafetyFinding, validate_strategy_rule_formula_safety

from .yaml_strategy_loader import load_strategy_rule


REQUIRED_FOLDER_FILES = (
    "strategy.yaml",
    "formulas.yaml",
    "parameters.yaml",
    "notes.md",
    "excel_crosscheck.yaml",
)


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a mapping: {path}")
    return data


def _validate_excel_crosscheck(
    strategy_file: Path,
    *,
    rule_strategy_code: str,
    rule_unique_code: str,
) -> None:
    folder = strategy_file.parent
    crosscheck_path = folder / "excel_crosscheck.yaml"
    data = _load_yaml(crosscheck_path)

    required_keys = (
        "strategy_code",
        "unique_code",
        "source_sheet",
        "source_branch",
        "source_cells",
        "sample_calculation",
    )
    missing_top_level = [key for key in required_keys if key not in data]
    if missing_top_level:
        raise ValueError(
            f"excel_crosscheck.yaml missing keys: {', '.join(missing_top_level)}"
        )

    if not isinstance(data["source_cells"], dict) or not data["source_cells"]:
        raise ValueError("excel_crosscheck.yaml source_cells must be a non-empty mapping")
    sample = data["sample_calculation"]
    if not isinstance(sample, dict):
        raise ValueError("excel_crosscheck.yaml sample_calculation must be a mapping")
    expected = sample.get("expected")
    if not isinstance(expected, dict) or not expected:
        raise ValueError(
            "excel_crosscheck.yaml sample_calculation.expected must be a non-empty mapping"
        )

    if data["strategy_code"] != rule_strategy_code:
        raise ValueError(
            "excel_crosscheck.yaml strategy_code does not match strategy.yaml"
        )
    if data["unique_code"] != rule_unique_code:
        raise ValueError(
            "excel_crosscheck.yaml unique_code does not match strategy.yaml"
        )


def _load_crosscheck(path: Path) -> dict[str, Any]:
    return _load_yaml(path)


def validate_legacy_strategy(path: Path) -> tuple[bool, str]:
    try:
        load_strategy_rule(path)
    except Exception as exc:
        return False, str(exc)
    return True, ""


def validate_folder_strategy(strategy_path: Path) -> tuple[bool, str]:
    ok, message, _warnings = validate_folder_strategy_detailed(strategy_path)
    return ok, message


def validate_folder_strategy_detailed(
    strategy_path: Path,
) -> tuple[bool, str, list[FormulaSafetyFinding]]:
    strategy_file = strategy_path if strategy_path.name == "strategy.yaml" else strategy_path / "strategy.yaml"
    folder = strategy_file.parent
    missing_files = [
        name for name in REQUIRED_FOLDER_FILES if not (folder / name).is_file()
    ]
    if missing_files:
        return (
            False,
            "missing required files: " + ", ".join(missing_files),
            [],
        )

    try:
        rule = load_strategy_rule(strategy_file)
        crosscheck = _load_crosscheck(folder / "excel_crosscheck.yaml")
        _validate_excel_crosscheck(
            strategy_file,
            rule_strategy_code=rule.strategy_code,
            rule_unique_code=rule.unique_code,
        )
        findings = validate_strategy_rule_formula_safety(
            rule,
            crosscheck=crosscheck,
        )
    except Exception as exc:
        return False, str(exc), []

    error_findings = [finding for finding in findings if finding.severity == "ERROR"]
    if error_findings:
        message = "; ".join(
            f"{finding.field_name}: {finding.message}" for finding in error_findings
        )
        return False, message, findings

    return True, "", findings


def discover_strategy_sources(strategy_dir: Path) -> tuple[list[Path], list[Path]]:
    legacy_dir = strategy_dir / "legacy"
    legacy_files = (
        sorted(path for path in legacy_dir.glob("*.yaml") if path.is_file())
        if legacy_dir.exists()
        else []
    )
    folder_files = sorted(
        path for path in strategy_dir.glob("**/strategy.yaml") if path.is_file()
    )
    return legacy_files, folder_files
