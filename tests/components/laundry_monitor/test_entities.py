"""Test Laundry Monitor runtime and base entities."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.laundry_monitor.const import (
    CONF_DOOR_SENSOR,
    CONF_ENERGY_SENSOR,
    CONF_LEAK_SENSOR,
    CONF_POWER_SENSOR,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
    LaundryCycleState,
)


def _entity_id(
    hass: HomeAssistant,
    platform: str,
    entry: MockConfigEntry,
    key: str,
) -> str:
    """Return an entity ID by its integration unique ID."""
    entity_id = er.async_get(hass).async_get_entity_id(
        platform,
        DOMAIN,
        f"{entry.entry_id}_{key}",
    )
    assert entity_id is not None
    return entity_id


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create and set up a fully configured test entry."""
    hass.states.async_set("sensor.washing_machine_power", "0.25")
    hass.states.async_set("binary_sensor.washing_machine_door", STATE_OFF)
    hass.states.async_set("binary_sensor.washing_machine_vibration", STATE_OFF)
    hass.states.async_set("binary_sensor.washing_machine_leak", STATE_OFF)
    hass.states.async_set("sensor.washing_machine_energy", "125.3")

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washing Machine",
        data={
            CONF_NAME: "Washing Machine",
            CONF_POWER_SENSOR: "sensor.washing_machine_power",
            CONF_DOOR_SENSOR: "binary_sensor.washing_machine_door",
            CONF_VIBRATION_SENSOR: "binary_sensor.washing_machine_vibration",
            CONF_LEAK_SENSOR: "binary_sensor.washing_machine_leak",
            CONF_ENERGY_SENSOR: "sensor.washing_machine_energy",
            CONF_TRACK_LAUNDRY: True,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def test_base_entities_are_created(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test creation of the base entity set."""
    entry = await _setup_entry(hass)

    expected = {
        ("sensor", "cycle_state"): "idle",
        ("sensor", "last_transition_reason"): "initial_setup",
        ("binary_sensor", "running"): STATE_OFF,
        ("binary_sensor", "finished"): STATE_OFF,
        ("binary_sensor", "leak"): STATE_OFF,
        ("binary_sensor", "laundry_present"): STATE_OFF,
        ("button", "mark_unloaded"): "unknown",
    }

    for (platform, key), expected_state in expected.items():
        state = hass.states.get(_entity_id(hass, platform, entry, key))
        assert state is not None
        assert state.state == expected_state

    timestamp_state = hass.states.get(
        _entity_id(hass, "sensor", entry, "last_state_change")
    )
    assert timestamp_state is not None
    assert timestamp_state.state not in ("unknown", "unavailable")


async def test_runtime_tracks_source_entities(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test that source-state changes update the runtime and entities."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    assert runtime.power == 0.25
    assert runtime.door_open is False
    assert runtime.vibration_active is False
    assert runtime.leak_detected is False
    assert runtime.energy == 125.3

    hass.states.async_set("sensor.washing_machine_power", "48.5")
    hass.states.async_set("binary_sensor.washing_machine_door", STATE_ON)
    hass.states.async_set("binary_sensor.washing_machine_vibration", STATE_ON)
    hass.states.async_set("binary_sensor.washing_machine_leak", STATE_ON)
    hass.states.async_set("sensor.washing_machine_energy", "125.8")
    await hass.async_block_till_done()

    assert runtime.power == 48.5
    assert runtime.door_open is True
    assert runtime.vibration_active is True
    assert runtime.leak_detected is True
    assert runtime.energy == 125.8

    leak_state = hass.states.get(_entity_id(hass, "binary_sensor", entry, "leak"))
    assert leak_state is not None
    assert leak_state.state == STATE_ON


async def test_cycle_state_updates_base_entities(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test the future state-machine update interface."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_cycle_started",
    )
    await hass.async_block_till_done()

    cycle_state = hass.states.get(
        _entity_id(hass, "sensor", entry, "cycle_state")
    )
    running = hass.states.get(
        _entity_id(hass, "binary_sensor", entry, "running")
    )
    laundry_present = hass.states.get(
        _entity_id(hass, "binary_sensor", entry, "laundry_present")
    )

    assert cycle_state is not None
    assert cycle_state.state == LaundryCycleState.RUNNING
    assert running is not None
    assert running.state == STATE_ON
    assert laundry_present is not None
    assert laundry_present.state == STATE_ON


async def test_mark_unloaded_button(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test explicit unloading through the button entity."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    runtime.async_set_cycle_state(
        LaundryCycleState.FINISHED,
        "test_cycle_finished",
    )
    await hass.async_block_till_done()

    button_entity_id = _entity_id(hass, "button", entry, "mark_unloaded")
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": button_entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert runtime.laundry_present is False
    assert runtime.cycle_state is LaundryCycleState.IDLE

    cycle_state = hass.states.get(
        _entity_id(hass, "sensor", entry, "cycle_state")
    )
    laundry_present = hass.states.get(
        _entity_id(hass, "binary_sensor", entry, "laundry_present")
    )

    assert cycle_state is not None
    assert cycle_state.state == LaundryCycleState.IDLE
    assert laundry_present is not None
    assert laundry_present.state == STATE_OFF
