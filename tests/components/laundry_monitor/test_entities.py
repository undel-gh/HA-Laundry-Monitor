"""Test Laundry Monitor runtime and base entities."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.laundry_monitor.const import (
    CONF_CURRENT_SENSOR,
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


async def _setup_entry(
    hass: HomeAssistant,
    *,
    tracking: bool = True,
    with_current: bool = True,
) -> MockConfigEntry:
    """Create and set up a fully configured test entry."""
    hass.states.async_set("sensor.washing_machine_power", "0.25")
    if with_current:
        hass.states.async_set("sensor.washing_machine_current", "0.0")
    hass.states.async_set("binary_sensor.washing_machine_door", STATE_OFF)
    hass.states.async_set("binary_sensor.washing_machine_vibration", STATE_OFF)
    hass.states.async_set("binary_sensor.washing_machine_leak", STATE_OFF)
    hass.states.async_set("sensor.washing_machine_energy", "125.3")

    data = {
        CONF_NAME: "Washing Machine",
        CONF_POWER_SENSOR: "sensor.washing_machine_power",
        CONF_DOOR_SENSOR: "binary_sensor.washing_machine_door",
        CONF_VIBRATION_SENSOR: "binary_sensor.washing_machine_vibration",
        CONF_LEAK_SENSOR: "binary_sensor.washing_machine_leak",
        CONF_ENERGY_SENSOR: "sensor.washing_machine_energy",
        CONF_TRACK_LAUNDRY: tracking,
    }
    if with_current:
        data[CONF_CURRENT_SENSOR] = "sensor.washing_machine_current"

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washing Machine",
        data=data,
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
        ("sensor", "last_unloaded_at"): "unknown",
        ("sensor", "current"): "0.0",
        ("sensor", "last_current_activity"): "unknown",
        ("sensor", "last_power_activity"): "unknown",
        ("binary_sensor", "running"): STATE_OFF,
        ("binary_sensor", "finished"): STATE_OFF,
        ("binary_sensor", "leak"): STATE_OFF,
        ("binary_sensor", "laundry_present"): STATE_OFF,
        ("binary_sensor", "power_activity_detected"): STATE_OFF,
        ("binary_sensor", "current_activity_detected"): STATE_OFF,
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


async def test_current_entities_require_configured_source(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test current-specific diagnostics are conditionally created."""
    entry = await _setup_entry(hass, with_current=False)
    registry = er.async_get(hass)

    assert registry.async_get_entity_id(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_current",
    ) is None
    assert registry.async_get_entity_id(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_last_current_activity",
    ) is None
    assert registry.async_get_entity_id(
        "binary_sensor",
        DOMAIN,
        f"{entry.entry_id}_current_activity_detected",
    ) is None


async def test_runtime_tracks_source_entities(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test that source-state changes update the runtime and entities."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    assert runtime.power == 0.25
    assert runtime.current == 0.0
    assert runtime.door_open is False
    assert runtime.vibration_active is False
    assert runtime.leak_detected is False
    assert runtime.energy == 125.3

    hass.states.async_set("sensor.washing_machine_power", "48.5")
    hass.states.async_set("sensor.washing_machine_current", "0.8")
    hass.states.async_set("binary_sensor.washing_machine_door", STATE_ON)
    hass.states.async_set("binary_sensor.washing_machine_vibration", STATE_ON)
    hass.states.async_set("binary_sensor.washing_machine_leak", STATE_ON)
    hass.states.async_set("sensor.washing_machine_energy", "125.8")
    await hass.async_block_till_done()

    assert runtime.power == 48.5
    assert runtime.current == 0.8
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

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_cycle_started",
    )
    await hass.async_block_till_done()

    assert runtime.async_set_cycle_state(
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
    assert runtime.last_unloaded_at is not None
    assert runtime.cycle_state is LaundryCycleState.IDLE

    cycle_state = hass.states.get(
        _entity_id(hass, "sensor", entry, "cycle_state")
    )
    laundry_present = hass.states.get(
        _entity_id(hass, "binary_sensor", entry, "laundry_present")
    )
    last_unloaded_at = hass.states.get(
        _entity_id(hass, "sensor", entry, "last_unloaded_at")
    )

    assert cycle_state is not None
    assert cycle_state.state == LaundryCycleState.IDLE
    assert laundry_present is not None
    assert laundry_present.state == STATE_OFF
    assert last_unloaded_at is not None
    assert last_unloaded_at.state not in ("unknown", "unavailable")


async def test_last_unloaded_sensor_requires_tracking(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test the unload timestamp sensor exists only with tracking enabled."""
    entry = await _setup_entry(hass, tracking=False)

    assert (
        er.async_get(hass).async_get_entity_id(
            "sensor",
            DOMAIN,
            f"{entry.entry_id}_last_unloaded_at",
        )
        is None
    )


async def test_mark_unloaded_outside_finished_preserves_transition_metadata(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test unloading outside finished is not reported as a transition."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_cycle_started",
    )
    await hass.async_block_till_done()

    transition_reason = runtime.last_transition_reason
    state_change = runtime.last_state_change

    runtime.async_mark_unloaded()
    await hass.async_block_till_done()

    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.laundry_present is False
    assert runtime.last_unloaded_at is not None
    assert runtime.last_transition_reason == transition_reason
    assert runtime.last_state_change == state_change

    snapshot = await runtime.state_store.async_get(entry.entry_id)
    assert snapshot is not None
    assert snapshot.last_unloaded_at == runtime.last_unloaded_at
    assert snapshot.last_transition_reason == transition_reason
    assert snapshot.last_state_change == state_change

