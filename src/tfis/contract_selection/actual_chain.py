from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping


class ActualOptionChainQualityCode(str, Enum):
    COMPLETE_FOR_REQUIRED_RANGE = "COMPLETE_FOR_REQUIRED_RANGE"
    PARTIAL_BUT_USABLE = "PARTIAL_BUT_USABLE"
    MISSING_REQUIRED_RANGE = "MISSING_REQUIRED_RANGE"
    EMPTY_CHAIN = "EMPTY_CHAIN"
    DUPLICATE_CONTRACT_IDENTITIES = "DUPLICATE_CONTRACT_IDENTITIES"
    MALFORMED_CONTRACT_IDENTITIES = "MALFORMED_CONTRACT_IDENTITIES"
    OPTION_TYPE_MISSING = "OPTION_TYPE_MISSING"
    EXPIRY_MISSING = "EXPIRY_MISSING"
    QUOTE_MISSING = "QUOTE_MISSING"
    OI_MISSING = "OI_MISSING"
    STALE_CHAIN = "STALE_CHAIN"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    UNSUPPORTED_CHAIN_QUALITY = "UNSUPPORTED_CHAIN_QUALITY"


@dataclass(frozen=True, slots=True)
class ActualOptionChainContract:
    contract_id: str
    exchange: str | None
    underlying: str | None
    product: str | None
    expiry: date
    option_type: str
    strike: Decimal
    tick_size: Decimal | None
    lot_size: int | None
    bid: Decimal | None
    ask: Decimal | None
    ltp: Decimal | None
    oi: Decimal | None
    oi_unit: str | None
    quote_timestamp: str | None
    source_timestamp: str | None
    data_quality: tuple[str, ...]
    metadata_version: str | None
    raw_contract: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ActualOptionChainTraversal:
    contracts: tuple[ActualOptionChainContract, ...]
    available_strikes: tuple[Decimal, ...]
    ordered_candidate_strikes: tuple[Decimal, ...]
    rejected_contracts: tuple[dict[str, Any], ...]
    quality_codes: tuple[ActualOptionChainQualityCode, ...]
    start_reference_strike: Decimal
    end_reference_strike: Decimal
    resolved_start_strike: Decimal | None
    resolved_end_strike: Decimal | None
    traversal_direction: str


def build_actual_option_chain_traversal(
    raw_contracts: Iterable[Mapping[str, Any]],
    *,
    expected_underlying: str,
    expiry: date,
    option_type: str,
    traversal_direction: str,
    start_reference_strike: Decimal,
    start_round_mode: str,
    end_reference_strike: Decimal,
    end_round_mode: str,
    end_offset_steps: int = 0,
    exchange: str | None = None,
    product: str | None = None,
    metadata_version: str | None = None,
    source_timestamp: str | None = None,
    chain_quality_flags: Iterable[str] = (),
) -> ActualOptionChainTraversal:
    raw_contract_list = list(raw_contracts)
    normalized: list[ActualOptionChainContract] = []
    rejected: list[dict[str, Any]] = []
    quality_codes: set[ActualOptionChainQualityCode] = set()
    expected_underlying_key = _canonical_underlying(expected_underlying)

    for raw in raw_contract_list:
        contract = _normalize_contract(
            raw,
            metadata_version=metadata_version,
            source_timestamp=source_timestamp,
        )
        if contract is None:
            rejected.append(
                {
                    "reason": ActualOptionChainQualityCode.MALFORMED_CONTRACT_IDENTITIES.value,
                    "contract": dict(raw),
                }
            )
            quality_codes.add(ActualOptionChainQualityCode.MALFORMED_CONTRACT_IDENTITIES)
            continue
        if _canonical_underlying(contract.underlying) != expected_underlying_key:
            rejected.append(_reject(contract, "UNDERLYING_MISMATCH"))
            continue
        if exchange is not None and contract.exchange != exchange:
            rejected.append(_reject(contract, "EXCHANGE_MISMATCH"))
            continue
        if product is not None and contract.product != product:
            rejected.append(_reject(contract, "PRODUCT_MISMATCH"))
            continue
        if contract.expiry != expiry:
            rejected.append(_reject(contract, "EXPIRY_MISMATCH"))
            continue
        if contract.option_type != option_type:
            rejected.append(_reject(contract, "OPTION_TYPE_MISMATCH"))
            continue
        normalized.append(contract)

    if not normalized:
        quality_codes.add(
            ActualOptionChainQualityCode.EMPTY_CHAIN
            if not raw_contract_list
            else ActualOptionChainQualityCode.EXPIRY_MISSING
        )
        return ActualOptionChainTraversal(
            contracts=(),
            available_strikes=(),
            ordered_candidate_strikes=(),
            rejected_contracts=tuple(rejected),
            quality_codes=tuple(sorted(quality_codes, key=lambda item: item.value)),
            start_reference_strike=start_reference_strike,
            end_reference_strike=end_reference_strike,
            resolved_start_strike=None,
            resolved_end_strike=None,
            traversal_direction=traversal_direction,
        )

    unique_contracts: dict[tuple[str, date, str, Decimal], ActualOptionChainContract] = {}
    duplicate_strikes: set[Decimal] = set()
    for contract in normalized:
        key = (contract.contract_id, contract.expiry, contract.option_type, contract.strike)
        existing = unique_contracts.get(key)
        if existing is not None:
            quality_codes.add(ActualOptionChainQualityCode.DUPLICATE_CONTRACT_IDENTITIES)
            rejected.append(_reject(contract, "DUPLICATE_CONTRACT_IDENTITY"))
            continue
        unique_contracts[key] = contract

    strike_index: dict[Decimal, ActualOptionChainContract] = {}
    for contract in unique_contracts.values():
        existing = strike_index.get(contract.strike)
        if existing is not None and existing.contract_id != contract.contract_id:
            duplicate_strikes.add(contract.strike)
            rejected.append(_reject(contract, "AMBIGUOUS_STRIKE_IDENTITY"))
            continue
        strike_index[contract.strike] = contract
    if duplicate_strikes:
        quality_codes.add(ActualOptionChainQualityCode.DUPLICATE_CONTRACT_IDENTITIES)

    available_strikes = tuple(sorted(strike_index))
    if not available_strikes:
        quality_codes.add(ActualOptionChainQualityCode.EMPTY_CHAIN)
        return ActualOptionChainTraversal(
            contracts=(),
            available_strikes=(),
            ordered_candidate_strikes=(),
            rejected_contracts=tuple(rejected),
            quality_codes=tuple(sorted(quality_codes, key=lambda item: item.value)),
            start_reference_strike=start_reference_strike,
            end_reference_strike=end_reference_strike,
            resolved_start_strike=None,
            resolved_end_strike=None,
            traversal_direction=traversal_direction,
        )

    if option_type not in {contract.option_type for contract in strike_index.values()}:
        quality_codes.add(ActualOptionChainQualityCode.OPTION_TYPE_MISSING)
    if any(contract.ltp is None for contract in strike_index.values()):
        quality_codes.add(ActualOptionChainQualityCode.QUOTE_MISSING)
    if any(contract.oi is None for contract in strike_index.values()):
        quality_codes.add(ActualOptionChainQualityCode.OI_MISSING)
    if any("stale" in flag.lower() for flag in chain_quality_flags):
        quality_codes.add(ActualOptionChainQualityCode.STALE_CHAIN)

    start_index = _resolve_boundary_index(
        available_strikes,
        reference=start_reference_strike,
        round_mode=start_round_mode,
    )
    end_anchor = _resolve_boundary_index(
        available_strikes,
        reference=end_reference_strike,
        round_mode=end_round_mode,
    )
    if start_index is None or end_anchor is None:
        quality_codes.add(ActualOptionChainQualityCode.MISSING_REQUIRED_RANGE)
        return ActualOptionChainTraversal(
            contracts=tuple(strike_index[strike] for strike in available_strikes),
            available_strikes=available_strikes,
            ordered_candidate_strikes=(),
            rejected_contracts=tuple(rejected),
            quality_codes=tuple(sorted(quality_codes, key=lambda item: item.value)),
            start_reference_strike=start_reference_strike,
            end_reference_strike=end_reference_strike,
            resolved_start_strike=available_strikes[start_index] if start_index is not None else None,
            resolved_end_strike=available_strikes[end_anchor] if end_anchor is not None else None,
            traversal_direction=traversal_direction,
        )

    end_index = end_anchor + end_offset_steps
    if end_index < 0 or end_index >= len(available_strikes):
        quality_codes.add(ActualOptionChainQualityCode.MISSING_REQUIRED_RANGE)
        return ActualOptionChainTraversal(
            contracts=tuple(strike_index[strike] for strike in available_strikes),
            available_strikes=available_strikes,
            ordered_candidate_strikes=(),
            rejected_contracts=tuple(rejected),
            quality_codes=tuple(sorted(quality_codes, key=lambda item: item.value)),
            start_reference_strike=start_reference_strike,
            end_reference_strike=end_reference_strike,
            resolved_start_strike=available_strikes[start_index],
            resolved_end_strike=None,
            traversal_direction=traversal_direction,
        )

    if traversal_direction.startswith("DESC"):
        low, high = sorted((end_index, start_index))
        ordered_strikes = tuple(reversed(available_strikes[low : high + 1]))
    else:
        low, high = sorted((start_index, end_index))
        ordered_strikes = tuple(available_strikes[low : high + 1])

    if not ordered_strikes:
        quality_codes.add(ActualOptionChainQualityCode.MISSING_REQUIRED_RANGE)
    elif quality_codes & {
        ActualOptionChainQualityCode.QUOTE_MISSING,
        ActualOptionChainQualityCode.OI_MISSING,
        ActualOptionChainQualityCode.STALE_CHAIN,
    }:
        quality_codes.add(ActualOptionChainQualityCode.PARTIAL_BUT_USABLE)
    else:
        quality_codes.add(ActualOptionChainQualityCode.COMPLETE_FOR_REQUIRED_RANGE)

    return ActualOptionChainTraversal(
        contracts=tuple(strike_index[strike] for strike in ordered_strikes),
        available_strikes=available_strikes,
        ordered_candidate_strikes=ordered_strikes,
        rejected_contracts=tuple(rejected),
        quality_codes=tuple(sorted(quality_codes, key=lambda item: item.value)),
        start_reference_strike=start_reference_strike,
        end_reference_strike=end_reference_strike,
        resolved_start_strike=available_strikes[start_index],
        resolved_end_strike=available_strikes[end_index],
        traversal_direction=traversal_direction,
    )


def _normalize_contract(
    raw: Mapping[str, Any],
    *,
    metadata_version: str | None,
    source_timestamp: str | None,
) -> ActualOptionChainContract | None:
    contract_id = _string_value(raw.get("symbol")) or _string_value(raw.get("source_symbol"))
    expiry_text = _string_value(raw.get("expiry"))
    option_type = _string_value(raw.get("option_type"))
    underlying = _string_value(raw.get("underlying"))
    strike = _decimal_value(raw.get("strike"))
    if contract_id is None or expiry_text is None or option_type is None or underlying is None or strike is None:
        return None
    try:
        expiry = date.fromisoformat(expiry_text)
    except ValueError:
        return None
    exchange = _string_value(raw.get("exchange"))
    if exchange is None and ":" in contract_id:
        exchange = contract_id.split(":", 1)[0]
    return ActualOptionChainContract(
        contract_id=contract_id,
        exchange=exchange,
        underlying=underlying,
        product=_string_value(raw.get("product")) or _string_value(raw.get("instrument_type")),
        expiry=expiry,
        option_type=option_type,
        strike=strike,
        tick_size=_decimal_value(raw.get("tick_size")),
        lot_size=_int_value(raw.get("lot_size")),
        bid=_decimal_value(raw.get("bid")),
        ask=_decimal_value(raw.get("ask")),
        ltp=_decimal_value(raw.get("ltp")),
        oi=_decimal_value(raw.get("oi")),
        oi_unit=_string_value(raw.get("oi_unit")),
        quote_timestamp=_string_value(raw.get("quote_timestamp")),
        source_timestamp=source_timestamp or _string_value(raw.get("source_timestamp")),
        data_quality=tuple(str(flag) for flag in raw.get("data_quality", ()) if flag is not None),
        metadata_version=metadata_version,
        raw_contract=raw,
    )


def _resolve_boundary_index(
    strikes: tuple[Decimal, ...],
    *,
    reference: Decimal,
    round_mode: str,
) -> int | None:
    if round_mode == "DOWN":
        for index in range(len(strikes) - 1, -1, -1):
            if strikes[index] <= reference:
                return index
        return None
    for index, strike in enumerate(strikes):
        if strike >= reference:
            return index
    return None


def _reject(contract: ActualOptionChainContract, reason: str) -> dict[str, Any]:
    return {
        "contract_id": contract.contract_id,
        "expiry": contract.expiry.isoformat(),
        "option_type": contract.option_type,
        "strike": str(contract.strike),
        "reason": reason,
    }


def _decimal_value(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _int_value(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _string_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _canonical_underlying(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.upper()
    if ":" in text:
        text = text.split(":", 1)[1]
    for suffix in ("-EQ", "-FUT", "-FUT-CONT"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text
