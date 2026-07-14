"""Test state-machine hardening inside the runtime."""

from homeassistant.const import CONF_NAME, STATE_OFF
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.laundry_monitor.const import (
    CONF_DOOR_SENSOR,
    CONF_POWER_SENSOR,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
    LaundryCycleState,
)


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
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
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_illegal_transition_does_not_change_runtime(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    changed = runtime.async_set_cycle_state(
        LaundryCycleState.FINISHED,
        "illegal_direct_finish",
    )
    await hass.async_block_till_done()

    assert changed is False
    assert runtime.cycle_state is LaundryCycleState.IDLE
    assert runtime.rejected_transition_count == 1
    assert runtime.last_rejected_transition == "idle->finished:illegal_direct_finish"


async def test_legal_transition_updates_both_state_holders(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    changed = runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_start",
    )
    await hass.async_block_till_done()

    assert changed is True
    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.state_machine.state is LaundryCycleState.RUNNING
    assert runtime.cycle_started_at is not None
