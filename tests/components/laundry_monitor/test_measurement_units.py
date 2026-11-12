"""Test canonical power/current units at the Home Assistant source boundary."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.laundry_monitor.sensor import (
    CURRENT_SENSOR_DESCRIPTIONS,
    SENSOR_DESCRIPTIONS,
    LaundryMonitorSensor,
)
from custom_components.laundry_monitor.const import (
    CONF_CURRENT_SENSOR,
    CONF_ENERGY_SENSOR,
    CONF_POWER_SENSOR,
    CONF_START_CONFIRMATION,
    CONF_TRACK_LAUNDRY,
    DOMAIN,
    LaundryCycleState,
)


_POWER_ENTITY = "sensor.washer_power"
_CURRENT_ENTITY = "sensor.washer_current"


async def _setup_entry(
    hass: HomeAssistant, *, with_energy: bool = False
) -> MockConfigEntry:
    """Create an integration with power, current and optional energy sources."""
    hass.states.async_set(_POWER_ENTITY, "0.25")
    hass.states.async_set(_CURRENT_ENTITY, "0")
    data = {
        CONF_NAME: "Washer",
        CONF_POWER_SENSOR: _POWER_ENTITY,
        CONF_CURRENT_SENSOR: _CURRENT_ENTITY,
        CONF_TRACK_LAUNDRY: False,
    }
    if with_energy:
        hass.states.async_set(
            "sensor.washer_energy",
            "125.3",
            {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
        )
        data[CONF_ENERGY_SENSOR] = "sensor.washer_energy"

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washer",
        data=data,
        options={CONF_START_CONFIRMATION: 5},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    return entry


def _diagnostic_state(
    hass: HomeAssistant, entry: MockConfigEntry, key: str
):
    """Inspect a debug sensor value even when HA registry disables it."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert entity_id is not None
    description = next(
        description
        for description in (*SENSOR_DESCRIPTIONS, *CURRENT_SENSOR_DESCRIPTIONS)
        if description.key == key
    )
    # The sensor's value/unit contract remains usable when explicitly
    # enabled, but new installs do not publish this mirror to Recorder.
    sensor = LaundryMonitorSensor(entry.runtime_data, description)
    value = sensor.native_value
    return SimpleNamespace(
        state="unknown" if value is None else str(value),
        attributes={
            ATTR_UNIT_OF_MEASUREMENT: sensor.native_unit_of_measurement
        },
    )


def _set_measurement(
    hass: HomeAssistant,
    entity_id: str,
    value: str,
    unit: str | None,
) -> None:
    """Set a source with or without an explicit unit."""
    attrs = {} if unit is None else {ATTR_UNIT_OF_MEASUREMENT: unit}
    hass.states.async_set(entity_id, value, attrs)


@pytest.mark.parametrize(
    ("raw", "unit", "expected"),
    [
        ("0", UnitOfPower.MILLIWATT, 0.0),
        ("250", UnitOfPower.MILLIWATT, 0.25),
        ("7.5", UnitOfPower.WATT, 7.5),
        ("0.12", UnitOfPower.KILO_WATT, 120.0),
        ("0.002", UnitOfPower.MEGA_WATT, 2000.0),
        ("15", None, 15.0),
    ],
)
async def test_power_is_normalized_to_watts(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    raw: str,
    unit: str | None,
    expected: float,
) -> None:
    """Activity and the public power diagnostic use actual watts."""
    entry = await _setup_entry(hass)

    _set_measurement(hass, _POWER_ENTITY, raw, unit)
    await hass.async_block_till_done()

    runtime = entry.runtime_data
    assert runtime.power == pytest.approx(expected)
    state = _diagnostic_state(hass, entry, "current_power")
    assert float(state.state) == pytest.approx(expected)
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfPower.WATT
    assert runtime.activity_detector.start_candidate is (expected >= 10.0)


@pytest.mark.parametrize(
    ("raw", "unit", "expected"),
    [
        ("0", UnitOfElectricCurrent.MILLIAMPERE, 0.0),
        ("500", UnitOfElectricCurrent.MILLIAMPERE, 0.5),
        ("250000", UnitOfElectricCurrent.MICROAMPERE, 0.25),
        ("0.8", UnitOfElectricCurrent.AMPERE, 0.8),
        ("0.4", None, 0.4),
    ],
)
async def test_current_is_normalized_to_amperes(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    raw: str,
    unit: str | None,
    expected: float,
) -> None:
    """Current assists activity but cannot independently start a cycle."""
    entry = await _setup_entry(hass)

    _set_measurement(hass, _CURRENT_ENTITY, raw, unit)
    await hass.async_block_till_done()

    runtime = entry.runtime_data
    assert runtime.current == pytest.approx(expected)
    state = _diagnostic_state(hass, entry, "current")
    assert float(state.state) == pytest.approx(expected)
    assert (
        state.attributes[ATTR_UNIT_OF_MEASUREMENT]
        == UnitOfElectricCurrent.AMPERE
    )
    assert runtime.current_activity_detected is (expected >= 0.1)
    assert runtime.activity_detector.start_candidate is False
    assert runtime.cycle_state is LaundryCycleState.IDLE


@pytest.mark.parametrize("unit", ["V", "kWh", "", "not-a-unit"])
async def test_invalid_power_unit_is_unavailable(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    unit: str,
) -> None:
    """Unsupported power units must not silently pass as watts."""
    entry = await _setup_entry(hass)
    _set_measurement(hass, _POWER_ENTITY, "45", unit)
    await hass.async_block_till_done()

    runtime = entry.runtime_data
    assert runtime.power is None
    assert runtime.power_activity_detected is False
    assert runtime.activity_detector.start_candidate is False
    assert _diagnostic_state(hass, entry, "current_power").state == "unknown"


@pytest.mark.parametrize("unit", ["W", "kWh", "", "not-a-unit"])
async def test_invalid_current_unit_degrades_to_power_only(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    unit: str,
) -> None:
    """Unsupported current units do not fabricate electrical activity."""
    entry = await _setup_entry(hass)
    _set_measurement(hass, _CURRENT_ENTITY, "500", unit)
    await hass.async_block_till_done()

    runtime = entry.runtime_data
    assert runtime.current is None
    assert runtime.current_activity_detected is None
    assert runtime.activity_detected is False
    assert _diagnostic_state(hass, entry, "current").state == "unknown"


async def test_unit_change_is_processed_even_if_raw_number_is_unchanged(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Changing W to kW with identical raw text changes the real value."""
    entry = await _setup_entry(hass)
    _set_measurement(hass, _POWER_ENTITY, "1", UnitOfPower.WATT)
    await hass.async_block_till_done()
    assert entry.runtime_data.power == 1.0

    _set_measurement(hass, _POWER_ENTITY, "1", UnitOfPower.KILO_WATT)
    await hass.async_block_till_done()
    assert entry.runtime_data.power == 1000.0
    assert entry.runtime_data.activity_detector.start_candidate is True


async def test_kilowatt_source_can_start_cycle(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Cycle-start confirmation must use normalized watts."""
    entry = await _setup_entry(hass)
    now = dt_util.utcnow()

    _set_measurement(hass, _POWER_ENTITY, "0.02", UnitOfPower.KILO_WATT)
    await hass.async_block_till_done()
    assert entry.runtime_data.power == 20.0

    async_fire_time_changed(hass, now + timedelta(seconds=6))
    await hass.async_block_till_done()
    assert entry.runtime_data.cycle_state is LaundryCycleState.RUNNING


async def test_overflow_after_conversion_is_unavailable(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """A finite raw number must not become infinite after conversion."""
    entry = await _setup_entry(hass)
    _set_measurement(hass, _POWER_ENTITY, "1e308", UnitOfPower.KILO_WATT)
    await hass.async_block_till_done()

    assert entry.runtime_data.power is None
    assert entry.runtime_data.activity_detector.start_candidate is False


async def test_energy_source_units_are_not_affected(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Power/current normalization leaves energy-source statistics unchanged."""
    entry = await _setup_entry(hass, with_energy=True)
    assert entry.runtime_data.energy == 125.3
    assert entry.runtime_data.energy_unit == UnitOfEnergy.KILO_WATT_HOUR

    hass.states.async_set(
        "sensor.washer_energy",
        "125.8",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
    )
    await hass.async_block_till_done()
    assert entry.runtime_data.energy == 125.8
    assert entry.runtime_data.energy_unit == UnitOfEnergy.KILO_WATT_HOUR
