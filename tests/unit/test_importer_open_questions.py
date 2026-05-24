from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
OPEN_QUESTIONS_PATH = ROOT / "config" / "importer_open_questions.yaml"

ALLOWED_STATUSES = {"OPEN", "RESOLVED", "REJECTED"}


def test_importer_open_questions_yaml_loads() -> None:
    with OPEN_QUESTIONS_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    assert isinstance(data, dict)
    assert isinstance(data.get("open_questions"), list)
    assert data["open_questions"]


def test_importer_open_question_ids_are_unique() -> None:
    with OPEN_QUESTIONS_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    ids = [entry["id"] for entry in data["open_questions"]]
    assert len(ids) == len(set(ids))


def test_importer_open_question_statuses_are_valid() -> None:
    with OPEN_QUESTIONS_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    for entry in data["open_questions"]:
        assert {"id", "workbook_cells", "description", "current_behavior", "alternative_interpretation", "status"}.issubset(entry.keys())
        assert isinstance(entry["workbook_cells"], list)
        assert entry["workbook_cells"]
        assert entry["status"] in ALLOWED_STATUSES
