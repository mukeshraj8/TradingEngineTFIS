from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Final

from tfis.domain.market_levels import MarketLevels


class FormulaEvaluationError(ValueError):
    """Raised when a TFIS formula is invalid or cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: str


class _FormulaParser:
    _TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(
        r"""
        (?P<SPACE>\s+)
        |(?P<NUMBER>\d+(?:\.\d+)?)
        |(?P<NAME>[A-Za-z_][A-Za-z0-9_]*)
        |(?P<LPAREN>\()
        |(?P<RPAREN>\))
        |(?P<COMMA>,)
        |(?P<PLUS>\+)
        |(?P<MINUS>-)
        |(?P<STAR>\*)
        |(?P<PERCENT>%)
        """,
        re.VERBOSE,
    )

    _FUNCTIONS: Final[set[str]] = {"MIN", "MAX", "ROUND_UP", "ROUND_DOWN", "PARAM"}

    def __init__(
        self,
        formula: str,
        *,
        market_levels: MarketLevels,
        runtime_values: dict[str, Any],
        parameters: dict[str, float],
    ) -> None:
        self._formula = str(formula or "").strip()
        self._market_levels = market_levels
        self._runtime_values = runtime_values
        self._parameters = parameters
        self._tokens = self._tokenize(self._formula)
        self._index = 0

    def parse(self) -> float:
        if not self._formula:
            raise FormulaEvaluationError("Formula must be a non-empty string")
        value = self._parse_expression()
        if self._current().kind != "EOF":
            raise FormulaEvaluationError(
                f"Unexpected token at end of formula: {self._current().value}"
            )
        return value

    def _tokenize(self, formula: str) -> list[_Token]:
        tokens: list[_Token] = []
        position = 0
        while position < len(formula):
            match = self._TOKEN_PATTERN.match(formula, position)
            if match is None:
                raise FormulaEvaluationError(
                    f"Unsupported token near position {position}: {formula[position:]}"
                )
            kind = match.lastgroup
            assert kind is not None
            value = match.group()
            position = match.end()
            if kind == "SPACE":
                continue
            tokens.append(_Token(kind=kind, value=value))
        tokens.append(_Token(kind="EOF", value=""))
        return tokens

    def _parse_expression(self) -> float:
        value = self._parse_term()
        while self._current().kind in {"PLUS", "MINUS"}:
            operator = self._advance().kind
            delta = self._parse_adjustment(base_value=value)
            if operator == "PLUS":
                value += delta
            else:
                value -= delta
        return value

    def _parse_term(self) -> float:
        value = self._parse_primary()
        while self._current().kind == "STAR":
            self._advance()
            multiplier = self._parse_multiplier()
            value *= multiplier
        return value

    def _parse_primary(self) -> float:
        token = self._current()
        if token.kind == "NAME":
            if token.value.upper() in self._FUNCTIONS:
                return self._parse_function_call()
            self._advance()
            return self._resolve_alias(token.value)
        if token.kind == "NUMBER":
            self._advance()
            return float(token.value)
        if token.kind == "LPAREN":
            self._advance()
            value = self._parse_expression()
            self._expect("RPAREN")
            return value
        raise FormulaEvaluationError(f"Unexpected token in formula: {token.value}")

    def _parse_multiplier(self) -> float:
        value = self._parse_primary()
        if self._current().kind == "PERCENT":
            self._advance()
            return value / 100.0
        return value

    def _parse_function_call(self) -> float:
        name = self._expect("NAME").value.upper()
        self._expect("LPAREN")
        if name in {"MIN", "MAX"}:
            left = self._parse_expression()
            self._expect("COMMA")
            right = self._parse_expression()
            self._expect("RPAREN")
            return min(left, right) if name == "MIN" else max(left, right)
        if name in {"ROUND_UP", "ROUND_DOWN"}:
            value = self._parse_expression()
            self._expect("RPAREN")
            return (
                float(math.ceil(value))
                if name == "ROUND_UP"
                else float(math.floor(value))
            )
        if name == "PARAM":
            param_name = self._expect("NAME").value
            self._expect("RPAREN")
            return self._resolve_parameter(param_name)
        raise FormulaEvaluationError(f"Unsupported function: {name}")

    def _parse_percent_literal(self) -> float:
        number = self._expect("NUMBER").value
        self._expect("PERCENT")
        return float(number)

    def _parse_adjustment(self, *, base_value: float) -> float:
        token = self._current()
        if token.kind == "NUMBER":
            number = float(self._advance().value)
        elif token.kind == "NAME" and token.value.upper() == "PARAM":
            number = self._parse_function_call()
        else:
            raise FormulaEvaluationError(
                f"Expected numeric adjustment or PARAM(...), got {token.kind} ({token.value})"
            )
        if self._current().kind == "PERCENT":
            self._advance()
            return base_value * (number / 100.0)
        return number

    def _resolve_alias(self, alias: str) -> float:
        alias = alias.upper()
        if alias == "ENTRY":
            entry = self._runtime_values.get("ENTRY")
            if entry is None:
                raise FormulaEvaluationError("ENTRY is not available in runtime_values")
            return float(entry)

        if alias in FormulaEngine.OPTION_ALIAS_NAMES:
            return self._resolve_option_alias(alias)

        field_name = FormulaEngine.ALIAS_TO_MARKET_LEVEL.get(alias)
        if field_name is None:
            raise FormulaEvaluationError(f"Unsupported reference: {alias}")
        value = getattr(self._market_levels, field_name)
        if value is None:
            raise FormulaEvaluationError(f"Market level {alias} is not available")
        return float(value)

    def _resolve_option_alias(self, alias: str) -> float:
        direct_value = self._runtime_values.get(alias)
        if direct_value is not None:
            return float(direct_value)

        for container_name in ("OPT_LEVELS", "OPTION_LEVELS"):
            container = self._runtime_values.get(container_name)
            if container is None:
                continue
            if not isinstance(container, dict):
                raise FormulaEvaluationError(
                    f"runtime_values['{container_name}'] must be a mapping"
                )
            if alias in container:
                return float(container[alias])

        raise FormulaEvaluationError(f"Missing option reference: {alias}")

    def _resolve_parameter(self, parameter_name: str) -> float:
        value = self._parameters.get(parameter_name)
        if value is None:
            raise FormulaEvaluationError(f"Missing parameter: {parameter_name}")
        return float(value)

    def _current(self) -> _Token:
        return self._tokens[self._index]

    def _advance(self) -> _Token:
        token = self._tokens[self._index]
        self._index += 1
        return token

    def _expect(self, kind: str) -> _Token:
        token = self._current()
        if token.kind != kind:
            raise FormulaEvaluationError(
                f"Expected token {kind}, got {token.kind} ({token.value})"
            )
        return self._advance()


class FormulaEngine:
    """Closed formula evaluator for the approved TFIS mini-language."""

    ALIAS_TO_MARKET_LEVEL: Final[dict[str, str]] = {
        "PRV_2DHH": "d2hh",
        "PRV_2DLL": "d2ll",
        "PRV_3DHH": "d3hh",
        "PRV_3DLL": "d3ll",
        "PRV_4DHH": "d4hh",
        "PRV_4DLL": "d4ll",
        "CDHH": "current_day_high",
        "CDLL": "current_day_low",
    }
    OPTION_ALIAS_NAMES: Final[set[str]] = {
        "OPT_PRV_2DHH",
        "OPT_PRV_2DLL",
        "OPT_PRV_3DHH",
        "OPT_PRV_3DLL",
    }

    def evaluate(
        self,
        formula: str,
        *,
        market_levels: MarketLevels,
        runtime_values: dict[str, Any] | None = None,
        parameters: dict[str, float] | None = None,
    ) -> float:
        runtime_data = dict(runtime_values or {})
        merged_parameters = dict(parameters or {})
        runtime_parameters = runtime_data.get("PARAMS")
        if runtime_parameters is not None:
            if not isinstance(runtime_parameters, dict):
                raise FormulaEvaluationError("runtime_values['PARAMS'] must be a mapping")
            for key, value in runtime_parameters.items():
                merged_parameters[str(key)] = float(value)
        parser = _FormulaParser(
            formula,
            market_levels=market_levels,
            runtime_values=runtime_data,
            parameters=merged_parameters,
        )
        return parser.parse()
