from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, date
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo


class TimestampFailureClassification(str, Enum):
    TIMESTAMP_MISSING = "TIMESTAMP_MISSING"
    TIMESTAMP_FORMAT_UNSUPPORTED = "TIMESTAMP_FORMAT_UNSUPPORTED"
    TIMESTAMP_OUT_OF_RANGE = "TIMESTAMP_OUT_OF_RANGE"
    TIMESTAMP_TIMEZONE_AMBIGUOUS = "TIMESTAMP_TIMEZONE_AMBIGUOUS"
    MALFORMED_PROVIDER_PAYLOAD = "MALFORMED_PROVIDER_PAYLOAD"


class TimestampConversionQuality(str, Enum):
    EPOCH_SECONDS = "EPOCH_SECONDS"
    EPOCH_MILLISECONDS = "EPOCH_MILLISECONDS"
    NUMERIC_STRING_SECONDS = "NUMERIC_STRING_SECONDS"
    NUMERIC_STRING_MILLISECONDS = "NUMERIC_STRING_MILLISECONDS"
    ISO_WITH_TIMEZONE = "ISO_WITH_TIMEZONE"
    ISO_ASSUMED_SOURCE_TIMEZONE = "ISO_ASSUMED_SOURCE_TIMEZONE"
    DATETIME_WITH_TIMEZONE = "DATETIME_WITH_TIMEZONE"
    DATETIME_ASSUMED_SOURCE_TIMEZONE = "DATETIME_ASSUMED_SOURCE_TIMEZONE"


class TimestampNormalizationError(ValueError):
    def __init__(self, classification: TimestampFailureClassification, message: str) -> None:
        super().__init__(message)
        self.classification = classification


@dataclass(frozen=True, slots=True)
class NormalizedProviderTimestamp:
    raw_value: Any
    raw_value_type: str
    normalized_timestamp: datetime
    epoch_seconds: int
    source_timezone: str
    source_timezone_assumption: str | None
    conversion_quality: TimestampConversionQuality
    failure_classification: None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_value": self.raw_value,
            "raw_value_type": self.raw_value_type,
            "normalized_timestamp": self.normalized_timestamp.isoformat(),
            "epoch_seconds": self.epoch_seconds,
            "source_timezone": self.source_timezone,
            "source_timezone_assumption": self.source_timezone_assumption,
            "conversion_quality": self.conversion_quality.value,
            "failure_classification": self.failure_classification,
        }


def normalize_provider_timestamp(
    value: Any,
    *,
    source_timezone: str = "Asia/Kolkata",
    allow_naive_with_source_timezone: bool = True,
    min_year: int = 2000,
    max_year: int = 2100,
) -> NormalizedProviderTimestamp:
    tzinfo = ZoneInfo(source_timezone)
    raw_type = type(value).__name__
    if value in (None, ""):
        raise TimestampNormalizationError(
            TimestampFailureClassification.TIMESTAMP_MISSING,
            "Provider timestamp is missing.",
        )
    if isinstance(value, bool):
        raise TimestampNormalizationError(
            TimestampFailureClassification.MALFORMED_PROVIDER_PAYLOAD,
            "Boolean value is not a timestamp.",
        )
    if isinstance(value, datetime):
        quality = (
            TimestampConversionQuality.DATETIME_WITH_TIMEZONE
            if value.tzinfo is not None
            else TimestampConversionQuality.DATETIME_ASSUMED_SOURCE_TIMEZONE
        )
        normalized = value.astimezone(tzinfo) if value.tzinfo is not None else value.replace(tzinfo=tzinfo)
        assumption = None if value.tzinfo is not None else source_timezone
        return _validated_result(value, raw_type, normalized, source_timezone, assumption, quality, min_year, max_year)
    if isinstance(value, (int, float)):
        return _from_epoch_number(value, raw_type, source_timezone, tzinfo, min_year, max_year)

    text = str(value).strip()
    if not text:
        raise TimestampNormalizationError(
            TimestampFailureClassification.TIMESTAMP_MISSING,
            "Provider timestamp is blank.",
        )
    if text.lstrip("+-").isdigit():
        return _from_epoch_number(text, raw_type, source_timezone, tzinfo, min_year, max_year, numeric_string=True)

    parsed_text = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(parsed_text)
    except ValueError as exc:
        raise TimestampNormalizationError(
            TimestampFailureClassification.TIMESTAMP_FORMAT_UNSUPPORTED,
            f"Unsupported provider timestamp format: {text!r}",
        ) from exc
    if parsed.tzinfo is None:
        if not allow_naive_with_source_timezone:
            raise TimestampNormalizationError(
                TimestampFailureClassification.TIMESTAMP_TIMEZONE_AMBIGUOUS,
                "Naive provider timestamp requires an explicit source timezone policy.",
            )
        normalized = parsed.replace(tzinfo=tzinfo)
        return _validated_result(
            value,
            raw_type,
            normalized,
            source_timezone,
            source_timezone,
            TimestampConversionQuality.ISO_ASSUMED_SOURCE_TIMEZONE,
            min_year,
            max_year,
        )
    return _validated_result(
        value,
        raw_type,
        parsed.astimezone(tzinfo),
        source_timezone,
        None,
        TimestampConversionQuality.ISO_WITH_TIMEZONE,
        min_year,
        max_year,
    )


def provider_epoch_seconds_for_datetime(moment: datetime, *, source_timezone: str = "Asia/Kolkata") -> int:
    tzinfo = ZoneInfo(source_timezone)
    normalized = moment.astimezone(tzinfo) if moment.tzinfo is not None else moment.replace(tzinfo=tzinfo)
    return int(normalized.timestamp())


def provider_epoch_seconds_for_expiry(
    expiry: date,
    *,
    source_timezone: str = "Asia/Kolkata",
    expiry_time: time = time(15, 30),
) -> int:
    return provider_epoch_seconds_for_datetime(
        datetime.combine(expiry, expiry_time, tzinfo=ZoneInfo(source_timezone)),
        source_timezone=source_timezone,
    )


def _from_epoch_number(
    value: Any,
    raw_type: str,
    source_timezone: str,
    tzinfo: ZoneInfo,
    min_year: int,
    max_year: int,
    *,
    numeric_string: bool = False,
) -> NormalizedProviderTimestamp:
    numeric_value = float(value)
    absolute = abs(numeric_value)
    milliseconds = absolute >= 1_000_000_000_000
    epoch_seconds = int(numeric_value / 1000) if milliseconds else int(numeric_value)
    try:
        normalized = datetime.fromtimestamp(epoch_seconds, tz=tzinfo)
    except (OverflowError, OSError, ValueError) as exc:
        raise TimestampNormalizationError(
            TimestampFailureClassification.TIMESTAMP_OUT_OF_RANGE,
            f"Provider timestamp is outside supported datetime range: {value!r}",
        ) from exc
    quality = (
        TimestampConversionQuality.NUMERIC_STRING_MILLISECONDS
        if numeric_string and milliseconds
        else TimestampConversionQuality.NUMERIC_STRING_SECONDS
        if numeric_string
        else TimestampConversionQuality.EPOCH_MILLISECONDS
        if milliseconds
        else TimestampConversionQuality.EPOCH_SECONDS
    )
    return _validated_result(value, raw_type, normalized, source_timezone, None, quality, min_year, max_year)


def _validated_result(
    raw_value: Any,
    raw_type: str,
    normalized: datetime,
    source_timezone: str,
    source_timezone_assumption: str | None,
    quality: TimestampConversionQuality,
    min_year: int,
    max_year: int,
) -> NormalizedProviderTimestamp:
    if normalized.year < min_year or normalized.year > max_year:
        raise TimestampNormalizationError(
            TimestampFailureClassification.TIMESTAMP_OUT_OF_RANGE,
            f"Provider timestamp year {normalized.year} is outside supported range {min_year}-{max_year}.",
        )
    return NormalizedProviderTimestamp(
        raw_value=raw_value,
        raw_value_type=raw_type,
        normalized_timestamp=normalized,
        epoch_seconds=int(normalized.timestamp()),
        source_timezone=source_timezone,
        source_timezone_assumption=source_timezone_assumption,
        conversion_quality=quality,
    )
