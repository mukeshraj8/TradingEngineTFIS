from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
REFERENCE_ROOT = ROOT / "docs" / "reference_materials"
INDEX_PATH = REFERENCE_ROOT / "index.yaml"

REQUIRED_CATEGORIES = {
    "monthly_status",
    "option_selling",
    "option_buying",
    "rollover",
    "banknifty_backtesting",
    "companies_list",
    "session_notes",
}

ALLOWED_STATUSES = {"reference_only", "partially_reviewed", "reviewed"}


def test_reference_material_index_loads() -> None:
    with INDEX_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    assert isinstance(data, dict)
    assert "categories" in data


def test_reference_material_categories_exist() -> None:
    with INDEX_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    categories = data["categories"]
    assert REQUIRED_CATEGORIES.issubset(categories.keys())


def test_reference_material_file_entries_have_required_metadata() -> None:
    with INDEX_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    for category_name, category_data in data["categories"].items():
        assert "description" in category_data
        assert "files" in category_data
        assert isinstance(category_data["files"], list)

        for entry in category_data["files"]:
            assert {"filename", "type", "status", "related_topics"}.issubset(entry.keys())
            assert isinstance(entry["filename"], str) and entry["filename"].strip()
            assert entry["status"] in ALLOWED_STATUSES
            assert isinstance(entry["related_topics"], list)
            if "path" in entry:
                path = REFERENCE_ROOT / entry["path"]
                assert path.is_file(), f"Indexed reference material path does not exist: {path}"
