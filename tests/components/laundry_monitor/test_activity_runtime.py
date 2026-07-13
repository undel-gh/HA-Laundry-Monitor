"""Test Activity Detector integration with Laundry Monitor runtime."""

from datetime import timedelta

from homeassistant.const import CONF_NAME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.laundry_monitor.const import (
    CONF_DOOR_SENSOR,
    CONF_POWER_SENSOR,
    CONF_START_CONFIRMATION,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
    LaundryCycleState,
    REASON_DOOR_CLOSED,
    REASON_DOOR_OPENED_BEFORE_START,
    REASON_POWER_ABOVE_START_THRESHOLD,
)


async def _setup_entry(
    hass: HomeAssistant,
    *,
    confirmation_seconds: int = 30,
) -> MockConfigEntry:
    """Set up an entry with Activity Detector options."""
    hass.states.async_set("sensor.washing_machine_power", "0.25")
    hass.states.async_set("binary_sensor.washing_machine_door", STATE_OFF)
    hass.states.async_set("binary_sensor.washing_machine_vibration", STATE_OFF)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washing Machine",
        data={
            CONF_NAME: "Washing Machine",
            CONF_POWER_SENSOR: "sensor.washing_machine_power",
            CONF_DOOR_SENSOR: "binary_sensor.washing_machine_door",
            CONF_VIBRATION_SENSOR: "binary_sensor.washing_machine_vibration",
            CONF_TRACK_LAUNDRY: True,
        },
        options={
            CONF_START_CONFIRMATION: confirmation_seconds,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_door_close_arms_and_reopen_cancels(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test idle -> armed -> idle transitions from the door."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    # Initial closed state must not arm on integration startup.
    assert runtime.cycle_state is LaundryCycleState.IDLE

    hass.states.async_set("binary_sensor.washing_machine_door", STATE_ON)
    await hass.async_block_till_done()
    assert runtime.cycle_state is LaundryCycleState.IDLE

    hass.states.async_set("binary_sensor.washing_machine_door", STATE_OFF)
    await hass.async_block_till_done()
    assert runtime.cycle_state is LaundryCycleState.ARMED
    assert runtime.last_transition_reason == REASON_DOOR_CLOSED

    hass.states.async_set("binary_sensor.washing_machine_door", STATE_ON)
    await hass.async_block_till_done()
    assert runtime.cycle_state is LaundryCycleState.IDLE
    assert runtime.last_transition_reason == REASON_DOOR_OPENED_BEFORE_START


async def test_sustained_start_power_starts_cycle(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test sustained start-level power confirms a running cycle."""
    entry = await _setup_entry(hass, confirmation_seconds=30)
    runtime = entry.runtime_data

    hass.states.async_set("binary_sensor.washing_machine_door", STATE_ON)
    hass.states.async_set("binary_sensor.washing_machine_door", STATE_OFF)
    await hass.async_block_till_done()
    assert runtime.cycle_state is LaundryCycleState.ARMED

    now = dt_util.utcnow()
    hass.states.async_set("sensor.washing_machine_power", "45")
    await hass.async_block_till_done()

    assert runtime.activity_detected is True
    assert runtime.cycle_state is LaundryCycleState.ARMED

    async_fire_time_changed(hass, now + timedelta(seconds=31))
    await hass.async_block_till_done()

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert (
        runtime.last_transition_reason
        == REASON_POWER_ABOVE_START_THRESHOLD
    )
    assert runtime.laundry_present is True


async def test_start_candidate_is_cancelled_when_power_drops(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test a short power spike does not start a cycle."""
    entry = await _setup_entry(hass, confirmation_seconds=30)
    runtime = entry.runtime_data

    now = dt_util.utcnow()
    hass.states.async_set("sensor.washing_machine_power", "45")
    await hass.async_block_till_done()

    hass.states.async_set("sensor.washing_machine_power", "0.25")
    await hass.async_block_till_done()

    async_fire_time_changed(hass, now + timedelta(seconds=31))
    await hass.async_block_till_done()

    assert runtime.cycle_state is LaundryCycleState.IDLE
    assert runtime.activity_detected is False


async def test_idle_can_start_without_door_sequence(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test the documented idle -> running power fallback."""
    entry = await _setup_entry(hass, confirmation_seconds=5)
    runtime = entry.runtime_data

    now = dt_util.utcnow()
    hass.states.async_set("sensor.washing_machine_power", "45")
    await hass.async_block_till_done()

    async_fire_time_changed(hass, now + timedelta(seconds=6))
    await hass.async_block_till_done()

    assert runtime.cycle_state is LaundryCycleState.RUNNING
