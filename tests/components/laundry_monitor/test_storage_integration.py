"""Integration tests for Laundry Monitor runtime snapshot persistence."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME, STATE_OFF
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.laundry_monitor import DATA_STATE_STORE
from custom_components.laundry_monitor.const import (
    CONF_DOOR_SENSOR,
    CONF_POWER_SENSOR,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
    LaundryCycleState,
    REASON_STATE_RESTORED,
)
from custom_components.laundry_monitor.storage import LaundryStateStore


def _set_source_states(
    hass: HomeAssistant,
    *,
    prefix: str,
    power: float = 45.0,
) -> None:
    """Create source entity states for one washing machine."""
    hass.states.async_set(f"sensor.{prefix}_power", str(power))
    hass.states.async_set(
        f"binary_sensor.{prefix}_door",
        STATE_OFF,
    )
    hass.states.async_set(
        f"binary_sensor.{prefix}_vibration",
        STATE_OFF,
    )


def _create_entry(
    *,
    name: str,
    prefix: str,
) -> MockConfigEntry:
    """Create a Laundry Monitor config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={
            CONF_NAME: name,
            CONF_POWER_SENSOR: f"sensor.{prefix}_power",
            CONF_DOOR_SENSOR: f"binary_sensor.{prefix}_door",
            CONF_VIBRATION_SENSOR: (
                f"binary_sensor.{prefix}_vibration"
            ),
            CONF_TRACK_LAUNDRY: True,
        },
    )


async def _async_add_and_setup_entry(
    hass: HomeAssistant,
    entry: MockConfigEntry,
) -> None:
    """Add and set up a new config entry."""
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED


async def test_snapshot_is_restored_after_unload_and_setup(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test a real runtime snapshot survives unload and setup."""
    _set_source_states(hass, prefix="washing_machine")

    entry = _create_entry(
        name="Washing Machine",
        prefix="washing_machine",
    )
    await _async_add_and_setup_entry(hass, entry)

    original_runtime = entry.runtime_data

    assert original_runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_cycle_started",
    )
    await hass.async_block_till_done()

    original_started_at = original_runtime.cycle_started_at
    original_state_change = original_runtime.last_state_change
    original_store = original_runtime.state_store

    assert original_started_at is not None
    assert original_runtime.laundry_present is True

    stored = await original_store.async_get(entry.entry_id)
    assert stored is not None
    assert stored.cycle_state is LaundryCycleState.RUNNING
    assert stored.cycle_started_at == original_started_at
    assert stored.last_state_change == original_state_change
    assert stored.laundry_present is True

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED

    # Simulate process-level loss of the in-memory singleton. The new store
    # must load the serialized snapshot from Home Assistant storage.
    assert hass.data.pop(DATA_STATE_STORE) is original_store

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    restored_runtime = entry.runtime_data

    assert restored_runtime is not original_runtime
    assert restored_runtime.state_store is not original_store

    assert restored_runtime.cycle_state is LaundryCycleState.RUNNING
    assert (
        restored_runtime.state_machine.state
        is LaundryCycleState.RUNNING
    )
    assert (
        restored_runtime.last_transition_reason
        == REASON_STATE_RESTORED
    )
    assert restored_runtime.last_state_change == original_state_change
    assert restored_runtime.cycle_started_at == original_started_at
    assert restored_runtime.laundry_present is True


async def test_two_entries_share_store_and_restore_independently(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test two entries share one store without overwriting snapshots."""
    _set_source_states(hass, prefix="washer")
    _set_source_states(hass, prefix="dryer")

    washer_entry = _create_entry(
        name="Washer",
        prefix="washer",
    )
    dryer_entry = _create_entry(
        name="Dryer",
        prefix="dryer",
    )

    await _async_add_and_setup_entry(hass, washer_entry)
    await _async_add_and_setup_entry(hass, dryer_entry)

    washer_runtime = washer_entry.runtime_data
    dryer_runtime = dryer_entry.runtime_data

    assert isinstance(
        washer_runtime.state_store,
        LaundryStateStore,
    )
    assert (
        washer_runtime.state_store
        is dryer_runtime.state_store
    )

    # Schedule writes for both entries before yielding to the event loop.
    # This catches stale per-entry store copies and unsafe concurrent writes.
    assert washer_runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "washer_started",
    )
    assert dryer_runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "dryer_started",
    )
    await hass.async_block_till_done()

    assert dryer_runtime.async_set_cycle_state(
        LaundryCycleState.FINAL_SPIN,
        "dryer_final_spin",
    )
    await hass.async_block_till_done()

    shared_store = washer_runtime.state_store

    washer_snapshot = await shared_store.async_get(
        washer_entry.entry_id
    )
    dryer_snapshot = await shared_store.async_get(
        dryer_entry.entry_id
    )

    assert washer_snapshot is not None
    assert dryer_snapshot is not None
    assert (
        washer_snapshot.cycle_state
        is LaundryCycleState.RUNNING
    )
    assert (
        dryer_snapshot.cycle_state
        is LaundryCycleState.FINAL_SPIN
    )

    old_washer_runtime = washer_runtime
    old_dryer_runtime = dryer_runtime

    assert await hass.config_entries.async_unload(
        washer_entry.entry_id
    )
    assert await hass.config_entries.async_unload(
        dryer_entry.entry_id
    )
    await hass.async_block_till_done()

    assert hass.data.pop(DATA_STATE_STORE) is shared_store

    assert await hass.config_entries.async_setup(
        washer_entry.entry_id
    )
    assert await hass.config_entries.async_setup(
        dryer_entry.entry_id
    )
    await hass.async_block_till_done()

    restored_washer = washer_entry.runtime_data
    restored_dryer = dryer_entry.runtime_data

    assert restored_washer is not old_washer_runtime
    assert restored_dryer is not old_dryer_runtime
    assert restored_washer.state_store is restored_dryer.state_store
    assert restored_washer.state_store is not shared_store

    assert (
        restored_washer.cycle_state
        is LaundryCycleState.RUNNING
    )
    assert (
        restored_dryer.cycle_state
        is LaundryCycleState.FINAL_SPIN
    )
    assert (
        restored_washer.state_machine.state
        is LaundryCycleState.RUNNING
    )
    assert (
        restored_dryer.state_machine.state
        is LaundryCycleState.FINAL_SPIN
    )
    assert (
        restored_washer.last_transition_reason
        == REASON_STATE_RESTORED
    )
    assert (
        restored_dryer.last_transition_reason
        == REASON_STATE_RESTORED
    )
