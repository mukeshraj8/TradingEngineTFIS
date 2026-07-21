from __future__ import annotations

from typing import Any


EXECUTOR_ALIASES = {
    "s23_morning_supervised": "paper_morning_supervised",
}


def optional_executor_name(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def canonical_executor_name(value: Any) -> str | None:
    rendered = optional_executor_name(value)
    if rendered is None:
        return None
    return EXECUTOR_ALIASES.get(rendered, rendered)


__all__ = [
    "EXECUTOR_ALIASES",
    "canonical_executor_name",
    "optional_executor_name",
]
