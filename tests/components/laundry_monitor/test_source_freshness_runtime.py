"""Regressions for identical electrical sensor observations (issue #6)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
    UnitOfElectricCurrent,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.laundry_monitor.const import (
    CONF_CURRENT_SENSOR,
    CONF_ELECTRICAL_SPIN_POWER_THRESHOLD,
    CONF_HEATING_OBSERVATION,
    CONF_HEATING_POWER_THRESHOLD,
    CONF_HYBRID_SPIN_ENABLED,
    CONF_POWER_SENSOR,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
    LaundryCycleState,
)
from custom_components.laundry_monitor.heating import HeatingState
from custom_components.laundry_monitor.runtime import LaundryMonitorRuntime


POWER = "sensor.washer_power"
CURRENT = "sensor.washer_current"
VIBRATION = "binary_sensor.washer_vibration"


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Start a running cycle with both electrical channels configured."""
    hass.states.async_set(
        POWER, "0.25", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}
    )
    hass.states.async_set(
        CURRENT, "0.2", {ATTR_UNIT_OF_MEASUREMENT: UnitOfElectricCurrent.AMPERE}
    )
    hass.states.async_set(VIBRATION, STATE_OFF)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washer",
        data={
            CONF_NAME: "Washer",
            CONF_POWER_SENSOR: POWER,
            CONF_CURRENT_SENSOR: CURRENT,
            CONF_VIBRATION_SENSOR: VIBRATION,
            CONF_TRACK_LAUNDRY: False,
        },
        options={
            CONF_HEATING_POWER_THRESHOLD: 1000.0,
            CONF_HEATING_OBSERVATION: 20,
            CONF_HYBRID_SPIN_ENABLED: True,
            CONF_ELECTRICAL_SPIN_POWER_THRESHOLD: 100.0,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.async_set_cycle_state(
        LaundryCycleState.RUNNING, "test_cycle_started"
    )
    await hass.async_block_till_done()
    return entry


async def test_same_value_attribute_change_is_a_fresh_power_observation(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Changed attributes with the same numeric power still seed freshness."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data
    assert runtime.heating_detector.power_source_fresh is False

    hass.states.async_set(
        POWER,
        "0.25",
        {
            ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
            "report_sequence": 1,
        },
    )
    await hass.async_block_till_done()

    assert runtime.power == 0.25
    assert runtime.heating_detector.power_source_fresh is True
    assert runtime.heating_detector._last_power_update_at is not None
    assert runtime.electrical_spin_detector.power_source_fresh is True

    previous_time = runtime.heating_detector._last_power_update_at
    hass.states.async_set(
        POWER,
        "0.25",
        {
            ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
            "report_sequence": 2,
        },
    )
    await hass.async_block_till_done()

    assert runtime.heating_detector._last_power_update_at >= previous_time


async def test_identical_state_report_refreshes_heating_coverage(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """A real repeated low-power report can establish heating NOT_SEEN."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    # First report after setup creates a fresh anchor despite unchanged power.
    hass.states.async_set(
        POWER, "0.25", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}
    )
    await hass.async_block_till_done()
    detector = runtime.heating_detector
    assert detector.power_source_fresh is True
    assert detector._last_power_update_at is not None
    assert detector.state is HeatingState.UNKNOWN

    # Simulate 25 s since the last real observation without waiting in CI.
    stale_anchor = dt_util.utcnow() - timedelta(seconds=25)
    detector._last_power_update_at = stale_anchor
    detector._last_evaluated_at = stale_anchor

    # No state or attribute change: Home Assistant emits state_reported.
    hass.states.async_set(
        POWER, "0.25", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}
    )
    await hass.async_block_till_done()

    assert detector.state is HeatingState.NOT_SEEN
    assert detector.observation_coverage_seconds >= 20
    assert detector.power_source_fresh is True
    assert detector._last_power_update_at > stale_anchor


async def test_same_value_report_establishes_electrical_spin_candidate(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Repeated stable power reports supply rolling coverage for hybrid."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    hass.states.async_set(
        POWER, "150", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}
    )
    await hass.async_block_till_done()

    earlier = dt_util.utcnow() - timedelta(seconds=25)
    runtime.electrical_spin_detector.reset(now=earlier, power=150.0)
    assert runtime.electrical_spin_detector.candidate is False

    hass.states.async_set(
        POWER, "150", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}
    )
    await hass.async_block_till_done()

    detector = runtime.electrical_spin_detector
    assert detector.power_source_fresh is True
    assert detector.power_coverage_seconds >= 20.0
    assert detector.candidate is True
    assert runtime.spin_electrical_candidate is True
    assert runtime.cycle_state is LaundryCycleState.RUNNING


async def test_identical_current_report_refreshes_electrical_freshness(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Repeated current readings stay fresh but remain corroboration only."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    hass.states.async_set(
        CURRENT,
        "500",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfElectricCurrent.MILLIAMPERE},
    )
    await hass.async_block_till_done()
    assert runtime.current == 0.5

    earlier = dt_util.utcnow() - timedelta(seconds=25)
    runtime.electrical_spin_detector._current_samples.clear()
    runtime.electrical_spin_detector._current_samples.append((earlier, 0.5))

    hass.states.async_set(
        CURRENT,
        "500",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfElectricCurrent.MILLIAMPERE},
    )
    await hass.async_block_till_done()

    detector = runtime.electrical_spin_detector
    assert detector.current_source_fresh is True
    assert detector.current_coverage_seconds >= 20.0
    assert runtime.current == 0.5
    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.spin_electrical_candidate is False


async def test_no_reports_means_no_fabricated_freshness(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Periodic timer evaluations must not turn cached data into reports."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    hass.states.async_set(
        POWER, "0.25", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}
    )
    await hass.async_block_till_done()

    now = dt_util.utcnow()
    old = now - timedelta(seconds=45)
    runtime.heating_detector._last_power_update_at = old
    runtime.heating_detector._last_evaluated_at = old
    runtime.electrical_spin_detector._power_samples.clear()
    runtime.electrical_spin_detector._power_samples.append((old, 0.25))

    runtime._async_cycle_statistics_tick(now)

    assert runtime.heating_detector.power_source_fresh is False
    assert runtime.electrical_spin_detector.power_source_fresh is False
    assert runtime.heating_detector._last_power_update_at == old


async def test_repeated_power_report_does_not_publish_all_entities(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unchanged telemetry updates internal freshness, not Recorder states."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    hass.states.async_set(
        POWER, "0.25", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}
    )
    await hass.async_block_till_done()

    published: list[str] = []
    original_notify = LaundryMonitorRuntime._notify_entities

    def collect_notify(self: LaundryMonitorRuntime) -> None:
        """Collect dispatcher notifications from the runtime under test."""
        if self is runtime:
            published.append(self.signal)
        original_notify(self)

    monkeypatch.setattr(LaundryMonitorRuntime, "_notify_entities", collect_notify)

    hass.states.async_set(
        POWER, "0.25", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}
    )
    await hass.async_block_till_done()

    assert published == []


async def test_repeated_vibration_report_does_not_create_an_edge(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Repeated ON reports must not inflate vibration evidence."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    hass.states.async_set(VIBRATION, STATE_ON)
    await hass.async_block_till_done()
    assert runtime.final_spin_evidence_count == 1

    for _ in range(3):
        hass.states.async_set(VIBRATION, STATE_ON)
        await hass.async_block_till_done()

    assert runtime.final_spin_evidence_count == 1
    assert runtime.cycle_state is LaundryCycleState.RUNNING


async def test_repeated_electrical_reports_stop_after_unload(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Unloading removes both source-change and state-report listeners."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    hass.states.async_set(
        POWER, "0.25", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}
    )
    await hass.async_block_till_done()
    before = runtime.heating_detector._last_power_update_at

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set(
        POWER, "0.25", {ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT}
    )
    await hass.async_block_till_done()
    assert runtime.heating_detector._last_power_update_at == before
