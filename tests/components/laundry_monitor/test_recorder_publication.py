"""Ensure runtime updates do not create unnecessary HA state publications."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.const import EntityCategory

from custom_components.laundry_monitor.binary_sensor import (
    BINARY_SENSOR_DESCRIPTIONS,
    LaundryMonitorBinarySensor,
)
from custom_components.laundry_monitor.const import LaundryCycleState
from custom_components.laundry_monitor.sensor import (
    CURRENT_SENSOR_DESCRIPTIONS,
    ENERGY_SENSOR_DESCRIPTIONS,
    SENSOR_DESCRIPTIONS,
    LaundryMonitorSensor,
)


def _runtime(**values):
    """Create minimal runtime data for entity publication tests."""
    return SimpleNamespace(
        entry=SimpleNamespace(entry_id="recorder-test"),
        name="Test Washing Machine",
        **values,
    )


def _sensor_description(key):
    return next(
        description
        for description in (
            *SENSOR_DESCRIPTIONS,
            *CURRENT_SENSOR_DESCRIPTIONS,
            *ENERGY_SENSOR_DESCRIPTIONS,
        )
        if description.key == key
    )


def _binary_description(key):
    return next(
        description
        for description in BINARY_SENSOR_DESCRIPTIONS
        if description.key == key
    )


def test_unchanged_sensor_notifications_do_not_write_ha_state() -> None:
    """A global runtime update must not rewrite an unrelated sensor."""
    runtime = _runtime(cycle_state=LaundryCycleState.IDLE)
    sensor = LaundryMonitorSensor(runtime, _sensor_description("cycle_state"))
    sensor._last_published_signature = sensor._runtime_state_signature()

    with patch.object(LaundryMonitorSensor, "async_write_ha_state") as write:
        sensor._handle_runtime_update()
        write.assert_not_called()

        runtime.cycle_state = LaundryCycleState.RUNNING
        sensor._handle_runtime_update()
        assert write.call_count == 1

        sensor._handle_runtime_update()
        assert write.call_count == 1


def test_binary_sensor_updates_only_on_its_own_value_change() -> None:
    """The running flag changes on RUNNING, not every detector update."""
    runtime = _runtime(cycle_state=LaundryCycleState.IDLE)
    entity = LaundryMonitorBinarySensor(
        runtime, _binary_description("running")
    )
    entity._last_published_signature = entity._runtime_state_signature()

    with patch.object(
        LaundryMonitorBinarySensor, "async_write_ha_state"
    ) as write:
        entity._handle_runtime_update()
        write.assert_not_called()

        runtime.cycle_state = LaundryCycleState.RUNNING
        entity._handle_runtime_update()
        assert write.call_count == 1

        runtime.cycle_state = LaundryCycleState.FINAL_SPIN
        entity._handle_runtime_update()
        assert write.call_count == 1  # Running remains ON.

        runtime.cycle_state = LaundryCycleState.FINISHED
        entity._handle_runtime_update()
        assert write.call_count == 2


def test_legacy_duration_publishes_only_on_cycle_boundaries() -> None:
    """Time passing must never trigger a legacy duration state write."""
    start = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
    runtime = _runtime(
        cycle_state=LaundryCycleState.RUNNING,
        cycle_started_at=start,
        current_cycle_duration=95.5,
    )
    sensor = LaundryMonitorSensor(
        runtime, _sensor_description("current_cycle_duration")
    )
    sensor._last_published_signature = sensor._runtime_state_signature()

    with patch.object(LaundryMonitorSensor, "async_write_ha_state") as write:
        for elapsed in (248.3, 302.7, 360.9, 3000.0):
            runtime.current_cycle_duration = elapsed
            assert sensor.native_value == elapsed
            sensor._handle_runtime_update()
        write.assert_not_called()

        # A phase transition can still refresh an explicitly enabled
        # compatibility sensor, but its value is not a live clock.
        runtime.cycle_state = LaundryCycleState.FINAL_SPIN
        sensor._handle_runtime_update()
        assert write.call_count == 1

        runtime.cycle_state = LaundryCycleState.RUNNING
        sensor._handle_runtime_update()
        assert write.call_count == 2

        runtime.cycle_state = LaundryCycleState.FINISHED
        runtime.current_cycle_duration = None
        sensor._handle_runtime_update()
        assert write.call_count == 3

        runtime.cycle_state = LaundryCycleState.IDLE
        runtime.cycle_started_at = None
        sensor._handle_runtime_update()
        assert write.call_count == 4


def test_cycle_start_sensor_tracks_only_active_cycles() -> None:
    """One timestamp replaces repeated duration state publications."""
    start = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
    runtime = _runtime(
        cycle_state=LaundryCycleState.IDLE, cycle_started_at=None
    )
    sensor = LaundryMonitorSensor(runtime, _sensor_description("cycle_started_at"))
    assert sensor.native_value is None
    assert sensor.entity_description.entity_registry_enabled_default is True

    runtime.cycle_state = LaundryCycleState.RUNNING
    runtime.cycle_started_at = start
    assert sensor.native_value == start

    runtime.cycle_state = LaundryCycleState.FINAL_SPIN
    assert sensor.native_value == start

    runtime.cycle_state = LaundryCycleState.RUNNING
    assert sensor.native_value == start  # Revoked final-spin hypothesis.

    runtime.cycle_state = LaundryCycleState.FINISHED
    assert sensor.native_value is None


def test_dynamic_energy_unit_change_is_not_suppressed() -> None:
    """The same numeric value in a different unit is a real state change."""
    runtime = _runtime(last_cycle_energy=2.5, last_cycle_energy_unit="kWh")
    sensor = LaundryMonitorSensor(
        runtime, _sensor_description("last_cycle_energy")
    )
    sensor._last_published_signature = sensor._runtime_state_signature()

    with patch.object(LaundryMonitorSensor, "async_write_ha_state") as write:
        runtime.last_cycle_energy_unit = "Wh"
        sensor._handle_runtime_update()
        write.assert_called_once()


def test_high_churn_diagnostics_are_disabled_by_default() -> None:
    """Ordinary dashboards retain lifecycle entities without debug writes."""
    for key in (
        "current_power",
        "last_activity",
        "last_power_activity",
        "last_current_activity",
        "current",
        "final_spin_confidence",
        "final_spin_evidence_count",
        "finish_quiet_since",
        "finish_deadline",
        "finish_remaining",
    ):
        description = _sensor_description(key)
        assert description.entity_category is EntityCategory.DIAGNOSTIC
        assert description.entity_registry_enabled_default is False

    description = _binary_description("power_activity_detected")
    assert description.entity_category is EntityCategory.DIAGNOSTIC
    assert description.entity_registry_enabled_default is False

    duration = _sensor_description("current_cycle_duration")
    started_at = _sensor_description("cycle_started_at")
    assert duration.entity_registry_enabled_default is False
    assert started_at.entity_registry_enabled_default is True
    assert _sensor_description("cycle_state").entity_registry_enabled_default is True
    assert _binary_description("running").entity_registry_enabled_default is True
