"""Test Spin Detector integration with Laundry Monitor runtime."""

from datetime import timedelta

from homeassistant.const import CONF_NAME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.laundry_monitor.const import (
    CONF_CURRENT_ACTIVITY_THRESHOLD,
    CONF_CURRENT_SENSOR,
    CONF_DOOR_SENSOR,
    CONF_POWER_SENSOR,
    CONF_SPIN_MIN_CYCLE_TIME,
    CONF_SPIN_REQUIRED_EVENTS,
    CONF_SPIN_WINDOW,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
    LaundryCycleState,
    REASON_FINAL_SPIN_CONFIRMED,
)


async def _setup_entry(
    hass: HomeAssistant,
    *,
    start_running: bool = True,
    with_current: bool = False,
) -> MockConfigEntry:
    """Set up a Spin Detector test entry."""
    hass.states.async_set(
        "sensor.washing_machine_power",
        "0.25" if with_current else "45",
    )
    if with_current:
        hass.states.async_set("sensor.washing_machine_current", "0.5")
    hass.states.async_set(
        "binary_sensor.washing_machine_door",
        STATE_OFF,
    )
    hass.states.async_set(
        "binary_sensor.washing_machine_vibration",
        STATE_OFF,
    )

    data = {
        CONF_NAME: "Washing Machine",
        CONF_POWER_SENSOR: "sensor.washing_machine_power",
        CONF_DOOR_SENSOR: "binary_sensor.washing_machine_door",
        CONF_VIBRATION_SENSOR:
            "binary_sensor.washing_machine_vibration",
        CONF_TRACK_LAUNDRY: True,
    }
    if with_current:
        data[CONF_CURRENT_SENSOR] = "sensor.washing_machine_current"

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washing Machine",
        data=data,
        options={
            CONF_SPIN_REQUIRED_EVENTS: 3,
            CONF_SPIN_WINDOW: 180,
            CONF_SPIN_MIN_CYCLE_TIME: 0,
            **(
                {CONF_CURRENT_ACTIVITY_THRESHOLD: 0.1}
                if with_current
                else {}
            ),
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    if start_running:
        assert entry.runtime_data.async_set_cycle_state(
            LaundryCycleState.RUNNING,
            "test_running",
        )
        await hass.async_block_till_done()

    return entry


async def _vibration_pulse(hass: HomeAssistant) -> None:
    """Generate one binary vibration pulse."""
    hass.states.async_set(
        "binary_sensor.washing_machine_vibration",
        STATE_ON,
    )
    await hass.async_block_till_done()
    hass.states.async_set(
        "binary_sensor.washing_machine_vibration",
        STATE_OFF,
    )
    await hass.async_block_till_done()


async def test_repeated_vibration_transitions_to_final_spin(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test running -> final_spin after repeated vibration."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    await _vibration_pulse(hass)
    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.final_spin_evidence_count == 1

    await _vibration_pulse(hass)
    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.final_spin_evidence_count == 2

    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN
    assert runtime.last_transition_reason == REASON_FINAL_SPIN_CONFIRMED
    assert runtime.final_spin_evidence_count == 3
    assert runtime.final_spin_confidence == 1.0


async def test_vibration_is_ignored_outside_running(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test that vibration cannot change idle state."""
    entry = await _setup_entry(
        hass,
        start_running=False,
    )
    runtime = entry.runtime_data

    assert runtime.cycle_state is LaundryCycleState.IDLE

    await _vibration_pulse(hass)
    await _vibration_pulse(hass)
    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.IDLE
    assert runtime.final_spin_evidence_count == 0
    assert runtime.rejected_transition_count == 0


async def test_current_activity_can_support_spin_context(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test current supports vibration evidence when power is quiet."""
    entry = await _setup_entry(hass, with_current=True)
    runtime = entry.runtime_data

    assert runtime.power_activity_detected is False
    assert runtime.current_activity_detected is True

    await _vibration_pulse(hass)
    await _vibration_pulse(hass)
    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN
    assert runtime.last_transition_reason == REASON_FINAL_SPIN_CONFIRMED


async def test_current_cannot_replace_unavailable_power_for_spin(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test current cannot confirm spin without the required power source."""
    entry = await _setup_entry(hass, with_current=True)
    runtime = entry.runtime_data

    hass.states.async_set(
        "sensor.washing_machine_power",
        "unavailable",
    )
    await hass.async_block_till_done()

    assert runtime.power is None
    assert runtime.current_activity_detected is True

    await _vibration_pulse(hass)
    await _vibration_pulse(hass)
    await _vibration_pulse(hass)

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.final_spin_evidence_count == 0
    assert runtime.final_spin_confidence == 0.0

