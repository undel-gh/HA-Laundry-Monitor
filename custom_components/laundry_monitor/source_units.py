"""Validated numeric source readings in Home Assistant canonical units."""

from __future__ import annotations

from math import isfinite

from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfElectricCurrent,
    UnitOfPower,
)
from homeassistant.core import State
from homeassistant.util.unit_conversion import (
    BaseUnitConverter,
    ElectricCurrentConverter,
    PowerConverter,
)


def state_as_float(state: State | None) -> float | None:
    """Return a finite raw numeric sensor value or None."""
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None

    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None

    return value if isfinite(value) else None


def _normalized_measurement(
    state: State | None,
    converter: type[BaseUnitConverter],
    target_unit: str,
) -> float | None:
    """Normalize an electrical measurement, rejecting unsupported units.

    Historical sources without a unit remain implicitly expressed in W/A.
    An explicitly declared but unsupported unit is never treated as W/A.
    """
    if state is None:
        return None

    value = state_as_float(state)
    if value is None:
        return None

    source_unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    if source_unit is None:
        source_unit = target_unit
    if not isinstance(source_unit, str) or source_unit not in converter.VALID_UNITS:
        return None

    converted = converter.convert(value, source_unit, target_unit)
    return converted if isfinite(converted) else None


def normalized_power(state: State | None) -> float | None:
    """Return source power in watts or None if unusable."""
    return _normalized_measurement(state, PowerConverter, UnitOfPower.WATT)


def normalized_current(state: State | None) -> float | None:
    """Return source current in amperes or None if unusable."""
    return _normalized_measurement(
        state, ElectricCurrentConverter, UnitOfElectricCurrent.AMPERE
    )
