"""Test Laundry Monitor sensor metadata."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower, UnitOfRatio, UnitOfTime

from custom_components.laundry_monitor.sensor import (
    SENSOR_DESCRIPTIONS,
    TRACKING_SENSOR_DESCRIPTIONS,
)


def test_sensor_descriptions_use_typed_home_assistant_constants() -> None:
    """Test units and state classes use Home Assistant enums."""
    descriptions = {
        description.key: description
        for description in SENSOR_DESCRIPTIONS
    }

    current_power = descriptions["current_power"]
    assert current_power.native_unit_of_measurement is UnitOfPower.WATT
    assert current_power.state_class is SensorStateClass.MEASUREMENT

    assert (
        descriptions["final_spin_confidence"].native_unit_of_measurement
        is UnitOfRatio.PERCENTAGE
    )
    assert (
        descriptions["finish_remaining"].native_unit_of_measurement
        is UnitOfTime.SECONDS
    )


def test_tracking_sensor_is_timestamp() -> None:
    """Test last_unloaded_at is described as a timestamp sensor."""
    assert len(TRACKING_SENSOR_DESCRIPTIONS) == 1
    description = TRACKING_SENSOR_DESCRIPTIONS[0]

    assert description.key == "last_unloaded_at"
    assert description.device_class is SensorDeviceClass.TIMESTAMP
