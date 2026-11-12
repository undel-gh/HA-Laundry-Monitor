"""Ensure runtime updates do not create unnecessary HA state publications."""

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


def test_duration_publication_is_bucketed_but_native_value_is_exact() -> None:
    """Five-minute HA publication cadence does not round detector time."""
    runtime = _runtime(
        cycle_state=LaundryCycleState.RUNNING,
        current_cycle_duration=95.5,
    )
    sensor = LaundryMonitorSensor(
        runtime, _sensor_description("current_cycle_duration")
    )
    sensor._last_published_signature = sensor._runtime_state_signature()

    with patch.object(LaundryMonitorSensor, "async_write_ha_state") as write:
        runtime.current_cycle_duration = 248.3
        assert sensor.native_value == 248.3
        sensor._handle_runtime_update()
        write.assert_not_called()

        runtime.current_cycle_duration = 302.7
        sensor._handle_runtime_update()
        assert write.call_count == 1

        runtime.current_cycle_duration = 360.9
        sensor._handle_runtime_update()
        assert write.call_count == 1

        # Terminal-phase transitions remain immediately observable.
        runtime.cycle_state = LaundryCycleState.FINAL_SPIN
        sensor._handle_runtime_update()
        assert write.call_count == 2

        # Leaving the active cycle clears the published duration immediately.
        runtime.cycle_state = LaundryCycleState.FINISHED
        runtime.current_cycle_duration = None
        sensor._handle_runtime_update()
        assert write.call_count == 3


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

    assert _sensor_description("current_cycle_duration").entity_registry_enabled_default is True
    assert _sensor_description("cycle_state").entity_registry_enabled_default is True
    assert _binary_description("running").entity_registry_enabled_default is True
