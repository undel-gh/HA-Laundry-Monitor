"""Test Laundry Monitor cycle statistics."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.laundry_monitor import DATA_STATE_STORE
from custom_components.laundry_monitor.const import (
    CONF_ENERGY_SENSOR,
    CONF_POWER_SENSOR,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
    LaundryCycleState,
)
from custom_components.laundry_monitor.diagnostics import (
    async_get_config_entry_diagnostics,
)


def _entity_id(
    hass: HomeAssistant,
    platform: str,
    entry: MockConfigEntry,
    key: str,
) -> str:
    """Return an entity ID by integration unique ID."""
    entity_id = er.async_get(hass).async_get_entity_id(
        platform,
        DOMAIN,
        f"{entry.entry_id}_{key}",
    )
    assert entity_id is not None
    return entity_id


async def _async_setup_entry(
    hass: HomeAssistant,
    *,
    include_energy: bool = True,
    include_vibration: bool = True,
    energy: str = "125.3",
    energy_unit: str = UnitOfEnergy.KILO_WATT_HOUR,
) -> MockConfigEntry:
    """Set up one entry with optional cycle-statistics sources."""
    hass.states.async_set("sensor.washing_machine_power", "45")

    data: dict[str, object] = {
        CONF_NAME: "Washing Machine",
        CONF_POWER_SENSOR: "sensor.washing_machine_power",
        CONF_TRACK_LAUNDRY: True,
    }

    if include_vibration:
        hass.states.async_set(
            "binary_sensor.washing_machine_vibration",
            STATE_OFF,
        )
        data[CONF_VIBRATION_SENSOR] = (
            "binary_sensor.washing_machine_vibration"
        )

    if include_energy:
        hass.states.async_set(
            "sensor.washing_machine_energy",
            energy,
            {ATTR_UNIT_OF_MEASUREMENT: energy_unit},
        )
        data[CONF_ENERGY_SENSOR] = "sensor.washing_machine_energy"

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


async def test_duration_statistics_and_periodic_entity_update(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test live duration updates and duration finalization."""
    entry = await _async_setup_entry(hass)
    runtime = entry.runtime_data

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_started",
    )
    await hass.async_block_till_done()

    runtime.cycle_started_at = dt_util.utcnow() - timedelta(seconds=65)
    async_fire_time_changed(
        hass,
        dt_util.utcnow() + timedelta(seconds=31),
    )
    await hass.async_block_till_done()

    current_duration = hass.states.get(
        _entity_id(hass, "sensor", entry, "current_cycle_duration")
    )
    assert current_duration is not None
    assert float(current_duration.state) >= 65

    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINISHED,
        "test_finished",
    )
    await hass.async_block_till_done()

    assert runtime.current_cycle_duration is None
    assert runtime.last_cycle_duration is not None
    assert runtime.last_cycle_duration >= 65

    last_duration = hass.states.get(
        _entity_id(hass, "sensor", entry, "last_cycle_duration")
    )
    assert last_duration is not None
    assert float(last_duration.state) >= 65


async def test_cycle_energy_is_finalized_in_source_unit(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test optional energy delta is captured for one completed cycle."""
    entry = await _async_setup_entry(hass)
    runtime = entry.runtime_data

    assert runtime.energy == 125.3
    assert runtime.energy_unit == UnitOfEnergy.KILO_WATT_HOUR

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_started",
    )
    await hass.async_block_till_done()

    assert runtime.cycle_energy_start == 125.3
    assert runtime.cycle_energy_unit == UnitOfEnergy.KILO_WATT_HOUR

    hass.states.async_set(
        "sensor.washing_machine_energy",
        "126.12",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
    )
    await hass.async_block_till_done()

    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINISHED,
        "test_finished",
    )
    await hass.async_block_till_done()

    assert runtime.last_cycle_energy == 0.82
    assert runtime.last_cycle_energy_unit == UnitOfEnergy.KILO_WATT_HOUR
    assert runtime.cycle_energy_start is None
    assert runtime.cycle_energy_unit is None

    energy_state = hass.states.get(
        _entity_id(hass, "sensor", entry, "last_cycle_energy")
    )
    assert energy_state is not None
    assert float(energy_state.state) == 0.82
    assert (
        energy_state.attributes[ATTR_UNIT_OF_MEASUREMENT]
        == UnitOfEnergy.KILO_WATT_HOUR
    )


async def test_energy_reset_does_not_create_negative_consumption(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test a reset cumulative source produces unknown cycle energy."""
    entry = await _async_setup_entry(hass, energy="10")
    runtime = entry.runtime_data

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_started",
    )
    hass.states.async_set(
        "sensor.washing_machine_energy",
        "0.2",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
    )
    await hass.async_block_till_done()

    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINISHED,
        "test_finished",
    )
    await hass.async_block_till_done()

    assert runtime.last_cycle_energy is None
    assert runtime.last_cycle_energy_unit is None


async def test_last_cycle_energy_entity_requires_energy_source(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test the optional energy statistic has no source-less entity."""
    entry = await _async_setup_entry(
        hass,
        include_energy=False,
    )

    assert (
        er.async_get(hass).async_get_entity_id(
            "sensor",
            DOMAIN,
            f"{entry.entry_id}_last_cycle_energy",
        )
        is None
    )


async def test_final_spin_detected_is_preserved_until_next_cycle(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test the final-spin result describes the current or last cycle."""
    entry = await _async_setup_entry(hass)
    runtime = entry.runtime_data
    entity_id = _entity_id(
        hass,
        "binary_sensor",
        entry,
        "final_spin_detected",
    )

    initial_state = hass.states.get(entity_id)
    assert initial_state is not None
    assert initial_state.state == STATE_OFF

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_started",
    )
    assert runtime.final_spin_detected is False

    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINAL_SPIN,
        "test_final_spin",
    )
    await hass.async_block_till_done()
    assert runtime.final_spin_detected is True
    detected_state = hass.states.get(entity_id)
    assert detected_state is not None
    assert detected_state.state == STATE_ON

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_activity_resumed",
    )
    assert runtime.final_spin_detected is True

    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINISHED,
        "test_finished",
    )
    assert runtime.async_set_cycle_state(
        LaundryCycleState.IDLE,
        "test_unloaded",
    )
    await hass.async_block_till_done()
    assert runtime.final_spin_detected is True

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "next_cycle",
    )
    await hass.async_block_till_done()
    assert runtime.final_spin_detected is False
    reset_state = hass.states.get(entity_id)
    assert reset_state is not None
    assert reset_state.state == STATE_OFF


async def test_active_cycle_statistics_survive_real_store_reload(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test active baselines restore and can finalize after reload."""
    entry = await _async_setup_entry(
        hass,
        energy="100",
    )
    runtime = entry.runtime_data

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_started",
    )
    runtime.cycle_started_at = dt_util.utcnow() - timedelta(hours=1)
    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINAL_SPIN,
        "test_final_spin",
    )
    await hass.async_block_till_done()

    hass.states.async_set(
        "binary_sensor.washing_machine_vibration",
        STATE_ON,
    )
    hass.states.async_set(
        "sensor.washing_machine_energy",
        "100.4",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
    )
    await hass.async_block_till_done()

    original_store = runtime.state_store
    # Persist the adjusted start timestamp together with the active baseline.
    runtime._schedule_snapshot_save()
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data.pop(DATA_STATE_STORE) is original_store

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    restored = entry.runtime_data
    assert restored.state_store is not original_store
    assert restored.cycle_state is LaundryCycleState.FINAL_SPIN
    assert restored.cycle_energy_start == 100
    assert restored.cycle_energy_unit == UnitOfEnergy.KILO_WATT_HOUR
    assert restored.final_spin_detected is True
    assert restored.current_cycle_duration is not None
    assert restored.current_cycle_duration >= 3600

    assert restored.async_set_cycle_state(
        LaundryCycleState.FINISHED,
        "test_finished",
    )
    await hass.async_block_till_done()

    assert restored.last_cycle_duration is not None
    assert restored.last_cycle_duration >= 3600
    assert restored.last_cycle_energy == 0.4
    assert (
        restored.last_cycle_energy_unit
        == UnitOfEnergy.KILO_WATT_HOUR
    )


async def test_cycle_statistics_are_in_diagnostics(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test diagnostics expose active and completed statistics."""
    entry = await _async_setup_entry(hass, energy="20")
    runtime = entry.runtime_data

    assert runtime.async_set_cycle_state(
        LaundryCycleState.RUNNING,
        "test_started",
    )
    runtime.cycle_started_at = dt_util.utcnow() - timedelta(seconds=90)
    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINAL_SPIN,
        "test_final_spin",
    )
    hass.states.async_set(
        "sensor.washing_machine_energy",
        "20.25",
        {ATTR_UNIT_OF_MEASUREMENT: UnitOfEnergy.KILO_WATT_HOUR},
    )
    await hass.async_block_till_done()
    assert runtime.async_set_cycle_state(
        LaundryCycleState.FINISHED,
        "test_finished",
    )
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    statistics = diagnostics["runtime"]["statistics"]

    assert statistics["current_cycle_duration"] is None
    assert statistics["last_cycle_duration"] >= 90
    assert statistics["last_cycle_energy"] == 0.25
    assert statistics["last_cycle_energy_unit"] == "kWh"
    assert statistics["final_spin_detected"] is True
