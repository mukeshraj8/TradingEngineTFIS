from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

import yaml


class S23ExtractionError(ValueError):
    """Raised when required S23 workbook anchors are missing or invalid."""


@dataclass(frozen=True, slots=True)
class WorkbookAnchor:
    sheet: str
    cell: str
    expected_value: str


@dataclass(slots=True)
class S23ExcelExtractor:
    workbook_path: Path
    strategy_code: str = "S23"

    _AB2_ANCHORS: tuple[WorkbookAnchor, ...] = (
        WorkbookAnchor("AB2", "B28", "S23"),
        WorkbookAnchor("AB2", "C28", "OPTIONS SELL"),
        WorkbookAnchor("AB2", "E28", "NIFTY"),
        WorkbookAnchor("AB2", "F28", "WEEKLY"),
    )
    _AB6_OS_ANCHORS: tuple[WorkbookAnchor, ...] = (
        WorkbookAnchor("AB6 OS", "C163", "S23"),
        WorkbookAnchor("AB6 OS", "C164", "NIFTY_OP_SELL_WK_DIFF_2D_3D"),
    )

    def extract_candidate(self) -> dict[str, Any]:
        workbook_path = Path(self.workbook_path)
        if not workbook_path.exists():
            raise FileNotFoundError(f"Workbook not found: {workbook_path}")

        workbook = load_workbook(workbook_path, read_only=True, data_only=True)
        try:
            ab2_sheet = workbook["AB2"]
            ab6_sheet = workbook["AB6 OS"]

            source_anchors = [
                self._verify_anchor(ab2_sheet, anchor) for anchor in self._AB2_ANCHORS
            ]
            source_anchors.extend(
                self._verify_anchor(ab6_sheet, anchor) for anchor in self._AB6_OS_ANCHORS
            )

            strategy_code = self._normalized_text(ab2_sheet["B28"].value)
            segment = self._normalized_segment(ab2_sheet["C28"].value)
            symbol = self._normalized_text(ab2_sheet["E28"].value)
            expiry_type = self._normalized_text(ab2_sheet["F28"].value)
            unique_code = self._normalized_text(ab6_sheet["C164"].value)

            candidate = {
                "strategy_code": strategy_code,
                "unique_code": unique_code,
                "symbol": symbol,
                "segment": segment,
                "expiry_type": expiry_type,
                "diff_basis": self._normalized_text(ab2_sheet["H28"].value),
                "entry_window_basis": self._normalized_text(ab2_sheet["I28"].value),
                "reference_window_basis": self._normalized_text(ab2_sheet["J28"].value),
                "source_anchors": source_anchors,
                "extraction_confidence": "medium",
                "unresolved_fields": [
                    "allowed_monthly_statuses",
                    "option_type",
                    "entry_time",
                    "recalculation_time",
                    "start_strike_formula",
                    "end_strike_formula",
                    "ideal_premium_formula",
                    "minimum_premium_formula",
                    "entry_formula",
                    "target_formula",
                    "stoploss_formula",
                    "minimum_oi",
                    "carry_forward_allowed",
                ],
            }
            return candidate
        finally:
            workbook.close()

    def compare_with_manual_yaml(self, yaml_path: str | Path) -> dict[str, Any]:
        candidate = self.extract_candidate()
        manual = self._load_manual_yaml(yaml_path)

        matched_fields: dict[str, dict[str, Any]] = {}
        mismatched_fields: dict[str, dict[str, Any]] = {}
        fields_present_only_in_manual: dict[str, Any] = {}

        for key, candidate_value in candidate.items():
            if key not in manual:
                continue
            manual_value = manual[key]
            if candidate_value == manual_value:
                matched_fields[key] = {
                    "candidate": candidate_value,
                    "manual": manual_value,
                }
            else:
                mismatched_fields[key] = {
                    "candidate": candidate_value,
                    "manual": manual_value,
                }

        for key, manual_value in manual.items():
            if key not in candidate:
                fields_present_only_in_manual[key] = manual_value

        fields_missing_from_excel_extraction = list(candidate["unresolved_fields"])
        safe_to_generate_yaml = not fields_missing_from_excel_extraction and not mismatched_fields

        return {
            "strategy_code": candidate["strategy_code"],
            "candidate": candidate,
            "manual_yaml_path": str(Path(yaml_path)),
            "matched_fields": matched_fields,
            "mismatched_fields": mismatched_fields,
            "fields_missing_from_excel_extraction": fields_missing_from_excel_extraction,
            "fields_present_only_in_manual_yaml": fields_present_only_in_manual,
            "recommendation": {
                "safe_to_generate_yaml": safe_to_generate_yaml,
                "reason": (
                    "Formula, timing, and monthly-status fields are still unresolved."
                    if not safe_to_generate_yaml
                    else "Candidate is complete enough to generate YAML."
                ),
            },
        }

    @staticmethod
    def write_json(data: dict[str, Any], out_path: str | Path) -> Path:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def write_comparison_markdown(comparison: dict[str, Any], out_path: str | Path) -> Path:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            "# S23 Extraction Comparison",
            "",
            f"Manual YAML: `{comparison['manual_yaml_path']}`",
            "",
            "## Matched Fields",
        ]
        matched = comparison["matched_fields"]
        if matched:
            for key, values in matched.items():
                lines.append(f"- `{key}` = `{values['candidate']}`")
        else:
            lines.append("- None")

        lines.extend(["", "## Mismatched Fields"])
        mismatched = comparison["mismatched_fields"]
        if mismatched:
            for key, values in mismatched.items():
                lines.append(
                    f"- `{key}`: candidate=`{values['candidate']}` manual=`{values['manual']}`"
                )
        else:
            lines.append("- None")

        lines.extend(["", "## Fields Missing From Excel Extraction"])
        missing = comparison["fields_missing_from_excel_extraction"]
        if missing:
            for key in missing:
                lines.append(f"- `{key}`")
        else:
            lines.append("- None")

        lines.extend(["", "## Fields Present Only In Manual YAML"])
        manual_only = comparison["fields_present_only_in_manual_yaml"]
        if manual_only:
            for key in manual_only:
                lines.append(f"- `{key}`")
        else:
            lines.append("- None")

        recommendation = comparison["recommendation"]
        lines.extend(
            [
                "",
                "## Recommendation",
                f"- `safe_to_generate_yaml`: `{str(recommendation['safe_to_generate_yaml']).lower()}`",
                f"- Reason: {recommendation['reason']}",
                "",
            ]
        )
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def _verify_anchor(self, worksheet: Any, anchor: WorkbookAnchor) -> dict[str, str]:
        actual = self._normalized_text(worksheet[anchor.cell].value)
        if actual != anchor.expected_value:
            raise S23ExtractionError(
                f"Anchor mismatch at {anchor.sheet}!{anchor.cell}: "
                f"expected {anchor.expected_value!r}, found {actual!r}"
            )
        return {
            "sheet": anchor.sheet,
            "cell": anchor.cell,
            "value": actual,
        }

    @staticmethod
    def _normalized_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _normalized_segment(value: Any) -> str:
        return S23ExcelExtractor._normalized_text(value).replace(" ", "_").upper()

    @staticmethod
    def _load_manual_yaml(path: str | Path) -> dict[str, Any]:
        file_path = Path(path)
        with file_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Strategy YAML must contain a mapping: {file_path}")
        return data


def extract_s23_candidate(workbook_path: str | Path) -> dict[str, Any]:
    extractor = S23ExcelExtractor(Path(workbook_path))
    return extractor.extract_candidate()
