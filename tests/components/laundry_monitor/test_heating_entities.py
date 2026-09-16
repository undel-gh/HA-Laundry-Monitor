"""Tests for heating diagnostic entities."""

from types import SimpleNamespace

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import EntityCategory

from custom_components.laundry_monitor.binary_sensor import (
    BINARY_SENSOR_DESCRIPTIONS,
)
from custom_components.laundry_monitor.heating import HeatingState
from custom_components.laundry_monitor.sensor import SENSOR_DESCRIPTIONS


def _sensor_description(key: str):
    return next(description for description in SENSOR_DESCRIPTIONS if description.key == key)


def _binary_description(key: str):
    return next(
        description
        for description in BINARY_SENSOR_DESCRIPTIONS
        if description.key == key
    )


def test_heating_state_sensor_description() -> None:
    """Heating state is a disabled-by-default diagnostic enum sensor."""
    description = _sensor_description("heating_state")

    assert description.translation_key == "heating_state"
    assert description.device_class is SensorDeviceClass.ENUM
    assert description.options == ["unknown", "not_seen", "detected"]
    assert description.entity_category is EntityCategory.DIAGNOSTIC
    assert description.entity_registry_enabled_default is False

    runtime = SimpleNamespace(heating_state=HeatingState.DETECTED)
    assert description.value_fn(runtime) == "detected"


def test_heating_active_binary_sensor_description() -> None:
    """Heating active exposes the detector's transient heater-level state."""
    description = _binary_description("heating_active")

    assert description.translation_key == "heating_active"
    assert description.entity_category is EntityCategory.DIAGNOSTIC
    assert description.entity_registry_enabled_default is False
    assert description.device_class is None

    runtime = SimpleNamespace(
        heating_detector=SimpleNamespace(heating_active=True)
    )
    assert description.value_fn(runtime) is True

    runtime.heating_detector.heating_active = False
    assert description.value_fn(runtime) is False
