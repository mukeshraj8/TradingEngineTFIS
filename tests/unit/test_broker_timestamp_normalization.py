from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tfis.broker.timestamp_normalization import (
    TimestampConversionQuality,
    TimestampFailureClassification,
    TimestampNormalizationError,
    normalize_provider_timestamp,
)


IST = ZoneInfo("Asia/Kolkata")


def _epoch() -> int:
    return int(datetime(2026, 6, 30, 15, 30, tzinfo=IST).timestamp())


def test_normalizes_integer_epoch_seconds() -> None:
    result = normalize_provider_timestamp(_epoch())

    assert result.normalized_timestamp == datetime(2026, 6, 30, 15, 30, tzinfo=IST)
    assert result.epoch_seconds == _epoch()
    assert result.conversion_quality is TimestampConversionQuality.EPOCH_SECONDS


def test_normalizes_integer_epoch_milliseconds() -> None:
    result = normalize_provider_timestamp(_epoch() * 1000)

    assert result.normalized_timestamp == datetime(2026, 6, 30, 15, 30, tzinfo=IST)
    assert result.conversion_quality is TimestampConversionQuality.EPOCH_MILLISECONDS


def test_normalizes_numeric_string() -> None:
    result = normalize_provider_timestamp(str(_epoch()))

    assert result.normalized_timestamp == datetime(2026, 6, 30, 15, 30, tzinfo=IST)
    assert result.raw_value == str(_epoch())
    assert result.conversion_quality is TimestampConversionQuality.NUMERIC_STRING_SECONDS


def test_normalizes_iso_datetime_with_timezone() -> None:
    result = normalize_provider_timestamp("2026-06-30T10:00:00+00:00")

    assert result.normalized_timestamp == datetime(2026, 6, 30, 15, 30, tzinfo=IST)
    assert result.conversion_quality is TimestampConversionQuality.ISO_WITH_TIMEZONE


def test_normalizes_naive_iso_with_source_timezone_assumption() -> None:
    result = normalize_provider_timestamp("2026-06-30T15:30:00")

    assert result.normalized_timestamp == datetime(2026, 6, 30, 15, 30, tzinfo=IST)
    assert result.source_timezone_assumption == "Asia/Kolkata"
    assert result.conversion_quality is TimestampConversionQuality.ISO_ASSUMED_SOURCE_TIMEZONE


def test_naive_iso_can_fail_when_policy_disallows_assumption() -> None:
    with pytest.raises(TimestampNormalizationError) as exc:
        normalize_provider_timestamp(
            "2026-06-30T15:30:00",
            allow_naive_with_source_timezone=False,
        )

    assert exc.value.classification is TimestampFailureClassification.TIMESTAMP_TIMEZONE_AMBIGUOUS


@pytest.mark.parametrize(
    ("value", "classification"),
    [
        ("not-a-timestamp", TimestampFailureClassification.TIMESTAMP_FORMAT_UNSUPPORTED),
        (None, TimestampFailureClassification.TIMESTAMP_MISSING),
        (True, TimestampFailureClassification.MALFORMED_PROVIDER_PAYLOAD),
        ("32503680000000", TimestampFailureClassification.TIMESTAMP_OUT_OF_RANGE),
    ],
)
def test_timestamp_failures_are_classified(value: object, classification: TimestampFailureClassification) -> None:
    with pytest.raises(TimestampNormalizationError) as exc:
        normalize_provider_timestamp(value)

    assert exc.value.classification is classification


def test_timestamp_normalization_preserves_chronological_ordering() -> None:
    earlier = normalize_provider_timestamp("2026-06-30T15:29:59+05:30")
    later = normalize_provider_timestamp(_epoch())

    assert earlier.normalized_timestamp < later.normalized_timestamp
    assert earlier.epoch_seconds < later.epoch_seconds
