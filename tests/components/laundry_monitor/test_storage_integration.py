"""Integration tests for Laundry Monitor runtime snapshot persistence."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, CONF_NAME, STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from ._ha_compat import MockConfigEntry

from custom_components.laundry_monitor import DATA_STATE_STORE
from custom_components.laundry_monitor.const import (
    CONF_DOOR_SENSOR,
    CONF_ENERGY_SENSOR,
    CONF_HEATING_POWER_THRESHOLD,
    CONF_POWER_SENSOR,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
    EVENT_CYCLE_FINISHED,
    EVENT_CYCLE_STARTED,
    EVENT_FINAL_SPIN_DETECTED,
    EVENT_MACHINE_UNLOADED,
    EVENT_STATE_CHANGED,
    LaundryCycleState,
    REASON_STATE_RECOVERY_FALLBACK,
    REASON_STATE_RESTORED,
)
from custom_components.laundry_monitor.heating import HeatingState
from custom_components.laundry_monitor.storage import (
    STORAGE_KEY,
    STORAGE_VERSION,
    LaundryStateStore,
    RuntimeSnapshot,
)


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
        is LaundryCycleState.RUNNING
    )
    assert (
        restored_washer.state_machine.state
        is LaundryCycleState.RUNNING
    )
    assert (
        restored_dryer.state_machine.state
        is LaundryCycleState.RUNNING
    )
    assert (
        restored_washer.last_transition_reason
        == REASON_STATE_RESTORED
    )
    assert (
        restored_dryer.last_transition_reason
        == REASON_STATE_RECOVERY_FALLBACK
    )


async def test_last_unloaded_at_is_restored_after_unload_and_setup(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test the unload timestamp survives a real storage reload."""
    _set_source_states(
        hass,
        prefix="washing_machine_unload_timestamp",
        power=0.25,
    )

    entry = _create_entry(
        name="Washing Machine Timestamp",
        prefix="washing_machine_unload_timestamp",
    )
    await _async_add_and_setup_entry(hass, entry)

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

    runtime.async_mark_unloaded()
    await hass.async_block_till_done()

    unloaded_at = runtime.last_unloaded_at
    original_store = runtime.state_store

    assert unloaded_at is not None
    assert runtime.cycle_state is LaundryCycleState.IDLE

    stored = await original_store.async_get(entry.entry_id)
    assert stored is not None
    assert stored.last_unloaded_at == unloaded_at

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED

    assert hass.data.pop(DATA_STATE_STORE) is original_store

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    restored_runtime = entry.runtime_data
    assert restored_runtime.state_store is not original_store
    assert restored_runtime.cycle_state is LaundryCycleState.IDLE
    assert restored_runtime.last_unloaded_at == unloaded_at

@pytest.mark.parametrize(
    ("corrupt_field", "expected_laundry_present"),
    [
        ("last_state_change", True),
        ("cycle_started_at", True),
    ],
)
async def test_naive_snapshot_timestamp_does_not_block_entry_setup(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    corrupt_field: str,
    expected_laundry_present: bool,
) -> None:
    """An invalid stored timestamp must not make a config entry fail setup."""
    _set_source_states(hass, prefix="naive_snapshot", power=0.25)
    entry = _create_entry(
        name="Washer With Invalid Snapshot",
        prefix="naive_snapshot",
    )

    now = dt_util.utcnow()
    stored = RuntimeSnapshot(
        cycle_state=LaundryCycleState.RUNNING,
        last_transition_reason="stored_running",
        last_state_change=now - timedelta(minutes=1),
        cycle_started_at=now - timedelta(minutes=20),
        laundry_present=True,
        last_cycle_duration=3600.0,
        last_cycle_energy=0.61,
        last_cycle_energy_unit="kWh",
        last_unloaded_at=now - timedelta(days=1),
    ).as_storage_dict()
    stored[corrupt_field] = "2026-01-01T00:00:00"

    await Store(hass, STORAGE_VERSION, STORAGE_KEY).async_save(
        {entry.entry_id: stored}
    )

    # Recovery must not fabricate any public lifecycle event.
    emitted: list[str] = []
    for event_name in (
        EVENT_CYCLE_STARTED,
        EVENT_FINAL_SPIN_DETECTED,
        EVENT_CYCLE_FINISHED,
        EVENT_MACHINE_UNLOADED,
        EVENT_STATE_CHANGED,
    ):
        hass.bus.async_listen(
            event_name, lambda event: emitted.append(event.event_type)
        )

    await _async_add_and_setup_entry(hass, entry)
    assert emitted == []

    runtime = entry.runtime_data
    assert entry.state is ConfigEntryState.LOADED
    assert runtime.cycle_state is LaundryCycleState.IDLE
    assert runtime.laundry_present is expected_laundry_present
    assert runtime.last_cycle_duration == 3600.0
    assert runtime.last_cycle_energy == 0.61
    assert runtime.last_cycle_energy_unit == "kWh"
    assert runtime.last_unloaded_at == now - timedelta(days=1)
    assert runtime.last_transition_reason == REASON_STATE_RECOVERY_FALLBACK
    assert runtime.cycle_started_at is None
    assert runtime.cycle_energy_start is None

    # The fallback snapshot must be immediately re-persisted with valid
    # transition timing, so a subsequent restart cannot revive the cycle.
    healed = await runtime.state_store.async_get(entry.entry_id)
    assert healed is not None
    assert healed.cycle_state is LaundryCycleState.IDLE
    assert healed.last_state_change is not None
    assert healed.laundry_present is True
    assert healed.last_cycle_duration == 3600.0

    original_store = runtime.state_store
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data.pop(DATA_STATE_STORE) is original_store

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    restarted = entry.runtime_data
    assert restarted.cycle_state is LaundryCycleState.IDLE
    assert restarted.last_cycle_duration == 3600.0
    assert restarted.last_unloaded_at == now - timedelta(days=1)
    assert restarted.laundry_present is True


@pytest.mark.parametrize(
    "bad_unload_time",
    ["not-a-date", "2026-01-01T00:00:00", 123],
)
async def test_corrupt_optional_unload_time_preserves_active_cycle_and_history(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    bad_unload_time: object,
) -> None:
    """Invalid optional unload history cannot poison an otherwise safe cycle."""
    _set_source_states(hass, prefix="corrupt_unload", power=45.0)
    entry = _create_entry(name="Washer Bad Unload", prefix="corrupt_unload")
    now = dt_util.utcnow()

    stored = RuntimeSnapshot(
        cycle_state=LaundryCycleState.RUNNING,
        last_transition_reason="stored_running",
        last_state_change=now - timedelta(minutes=1),
        cycle_started_at=now - timedelta(minutes=20),
        laundry_present=True,
        last_unloaded_at=now - timedelta(days=1),
        last_cycle_duration=1900.0,
        last_cycle_energy=0.43,
        last_cycle_energy_unit="kWh",
    ).as_storage_dict()
    stored["last_unloaded_at"] = bad_unload_time
    await Store(hass, STORAGE_VERSION, STORAGE_KEY).async_save(
        {entry.entry_id: stored}
    )

    await _async_add_and_setup_entry(hass, entry)

    runtime = entry.runtime_data
    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.last_transition_reason == REASON_STATE_RESTORED
    assert runtime.cycle_started_at is not None
    assert runtime.last_unloaded_at is None
    assert runtime.laundry_present is True
    assert runtime.last_cycle_duration == 1900.0
    assert runtime.last_cycle_energy == 0.43


async def test_corrupt_optional_types_restore_cycle_without_fabricating_proof(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Real storage recovery must not coerce optional data into evidence."""
    prefix = "corrupt_optional_types"
    _set_source_states(hass, prefix=prefix, power=0.25)
    energy_entity = f"sensor.{prefix}_energy"
    # Deliberately use a string matching the old coerced integer unit.
    # Even such a live value cannot legitimize a corrupt stored unit.
    hass.states.async_set(
        energy_entity, "126.0", {ATTR_UNIT_OF_MEASUREMENT: "123"}
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washer With Corrupt Optional Types",
        data={
            CONF_NAME: "Washer With Corrupt Optional Types",
            CONF_POWER_SENSOR: f"sensor.{prefix}_power",
            CONF_DOOR_SENSOR: f"binary_sensor.{prefix}_door",
            CONF_VIBRATION_SENSOR: f"binary_sensor.{prefix}_vibration",
            CONF_ENERGY_SENSOR: energy_entity,
            CONF_TRACK_LAUNDRY: True,
        },
        # The old float(True) would match this configured threshold.
        options={CONF_HEATING_POWER_THRESHOLD: 1.0},
    )

    now = dt_util.utcnow()
    stored = RuntimeSnapshot(
        cycle_state=LaundryCycleState.RUNNING,
        last_transition_reason="stored_running",
        last_state_change=now - timedelta(minutes=1),
        cycle_started_at=now - timedelta(minutes=20),
        laundry_present=True,
        last_unloaded_at=now - timedelta(days=1),
        cycle_energy_start=125.3,
        last_cycle_duration=1900.0,
        last_cycle_energy=0.43,
        last_cycle_energy_unit="kWh",
        heating_not_seen=True,
        heating_detector_version=1,
        heating_power_threshold_w=1.0,
        heating_confirmation_seconds=30,
        heating_observation_seconds=300,
        heating_max_source_age_seconds=30,
    ).as_storage_dict()
    stored.update(
        cycle_energy_start="125.3",
        cycle_energy_unit=123,
        last_cycle_energy=True,
        heating_power_threshold_w=True,
    )
    await Store(hass, STORAGE_VERSION, STORAGE_KEY).async_save(
        {entry.entry_id: stored}
    )

    emitted: list[str] = []
    for event_name in (
        EVENT_CYCLE_STARTED,
        EVENT_FINAL_SPIN_DETECTED,
        EVENT_CYCLE_FINISHED,
        EVENT_MACHINE_UNLOADED,
        EVENT_STATE_CHANGED,
    ):
        hass.bus.async_listen(
            event_name, lambda event: emitted.append(event.event_type)
        )

    await _async_add_and_setup_entry(hass, entry)
    runtime = entry.runtime_data

    assert emitted == []
    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.last_transition_reason == REASON_STATE_RESTORED
    assert runtime.laundry_present is True
    assert runtime.last_unloaded_at == now - timedelta(days=1)
    assert runtime.cycle_started_at == now - timedelta(minutes=20)
    assert runtime.last_cycle_duration == 1900.0
    assert runtime.last_cycle_energy is None
    assert runtime.last_cycle_energy_unit is None
    assert runtime.cycle_energy_start == 125.3
    assert runtime.cycle_energy_unit is None
    assert runtime.energy == 126.0
    assert runtime.energy_unit == "123"
    assert runtime.heating_state is HeatingState.UNKNOWN
    assert runtime.heating_detector.power_threshold_w == 1.0
    assert runtime.spin_electrical_candidate is False

    # Graceful unload checkpoints the sanitized data to real HA storage.
    original_store = runtime.state_store
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data.pop(DATA_STATE_STORE) is original_store

    raw = await Store(hass, STORAGE_VERSION, STORAGE_KEY).async_load()
    assert raw is not None
    saved = raw[entry.entry_id]
    assert saved["cycle_energy_start"] == 125.3
    assert saved["cycle_energy_unit"] is None
    assert saved["last_cycle_energy"] is None
    assert saved["last_cycle_energy_unit"] is None
    assert saved["heating_not_seen"] is False

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry.runtime_data
    assert emitted == []
    assert runtime.cycle_state is LaundryCycleState.RUNNING
    assert runtime.cycle_energy_unit is None
    assert runtime.last_cycle_duration == 1900.0
    assert runtime.heating_state is HeatingState.UNKNOWN

    # No fabricated consumption when the original unit is unknown.
    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINISHED, "test_finished"
    )
    await hass.async_block_till_done()
    assert runtime.last_cycle_energy is None
    assert runtime.last_cycle_energy_unit is None
