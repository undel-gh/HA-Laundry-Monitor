"""Test Finish Detector integration."""
from datetime import timedelta
from homeassistant.const import CONF_NAME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from custom_components.laundry_monitor.const import (
    CONF_DOOR_SENSOR, CONF_FINISH_CONFIRMATION, CONF_POWER_SENSOR,
    CONF_TRACK_LAUNDRY, CONF_VIBRATION_SENSOR, DOMAIN,
    LaundryCycleState, REASON_FINISH_INACTIVITY_CONFIRMED,
)

async def _setup_final_spin_entry(
    hass: HomeAssistant,
    *,
    confirmation_seconds: int = 30,
) -> MockConfigEntry:
    """Set up an entry already placed in final_spin."""
    hass.states.async_set("sensor.washing_machine_power", "45")
    hass.states.async_set(
        "binary_sensor.washing_machine_door",
        STATE_OFF,
    )
    hass.states.async_set(
        "binary_sensor.washing_machine_vibration",
        STATE_ON,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washing Machine",
        data={
            CONF_NAME: "Washing Machine",
            CONF_POWER_SENSOR: "sensor.washing_machine_power",
            CONF_DOOR_SENSOR: "binary_sensor.washing_machine_door",
            CONF_VIBRATION_SENSOR:
                "binary_sensor.washing_machine_vibration",
            CONF_TRACK_LAUNDRY: True,
        },
        options={
            CONF_FINISH_CONFIRMATION: confirmation_seconds,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    runtime = entry.runtime_data

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_running",
    )
    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINAL_SPIN,
        "test_final_spin",
    )
    await hass.async_block_till_done()

    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN
    assert runtime.rejected_transition_count == 0

    return entry

async def test_quiet_period_transitions_to_finished(hass: HomeAssistant, enable_custom_integrations: None) -> None:
    entry=await _setup_final_spin_entry(hass)
    runtime=entry.runtime_data
    now=dt_util.utcnow()
    hass.states.async_set("sensor.washing_machine_power","0.25")
    hass.states.async_set("binary_sensor.washing_machine_vibration",STATE_OFF)
    await hass.async_block_till_done()
    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN
    assert runtime.finish_deadline is not None
    async_fire_time_changed(hass,now+timedelta(seconds=31))
    await hass.async_block_till_done()
    assert runtime.cycle_state is LaundryCycleState.FINISHED
    assert runtime.last_transition_reason == REASON_FINISH_INACTIVITY_CONFIRMED
    assert runtime.laundry_present is True

async def test_activity_cancels_finish_confirmation(hass: HomeAssistant, enable_custom_integrations: None) -> None:
    entry=await _setup_final_spin_entry(hass); runtime=entry.runtime_data; now=dt_util.utcnow()
    hass.states.async_set("sensor.washing_machine_power","0.25")
    hass.states.async_set("binary_sensor.washing_machine_vibration",STATE_OFF)
    await hass.async_block_till_done()
    hass.states.async_set("sensor.washing_machine_power","45")
    await hass.async_block_till_done()
    async_fire_time_changed(hass,now+timedelta(seconds=31)); await hass.async_block_till_done()
    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN
    assert runtime.finish_deadline is None

async def test_vibration_cancels_finish_confirmation(hass: HomeAssistant, enable_custom_integrations: None) -> None:
    entry=await _setup_final_spin_entry(hass); runtime=entry.runtime_data; now=dt_util.utcnow()
    hass.states.async_set("sensor.washing_machine_power","0.25")
    hass.states.async_set("binary_sensor.washing_machine_vibration",STATE_OFF)
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.washing_machine_vibration",STATE_ON)
    await hass.async_block_till_done()
    async_fire_time_changed(hass,now+timedelta(seconds=31)); await hass.async_block_till_done()
    assert runtime.cycle_state is LaundryCycleState.FINAL_SPIN
    assert runtime.finish_deadline is None

async def test_inactivity_does_not_finish_running_state(hass: HomeAssistant, enable_custom_integrations: None) -> None:
    entry=await _setup_final_spin_entry(hass, confirmation_seconds=5); runtime=entry.runtime_data
    runtime.async_set_cycle_state(LaundryCycleState.RUNNING,"test_running")
    now=dt_util.utcnow()
    hass.states.async_set("sensor.washing_machine_power","0.25")
    hass.states.async_set("binary_sensor.washing_machine_vibration",STATE_OFF)
    await hass.async_block_till_done()
    async_fire_time_changed(hass,now+timedelta(seconds=10)); await hass.async_block_till_done()
    assert runtime.cycle_state is LaundryCycleState.RUNNING
