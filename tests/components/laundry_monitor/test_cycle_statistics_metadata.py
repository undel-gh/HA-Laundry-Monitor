"""Test Cycle Statistics entity metadata."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime

from custom_components.laundry_monitor.sensor import (
    ENERGY_SENSOR_DESCRIPTIONS,
    SENSOR_DESCRIPTIONS,
)


def test_duration_statistics_use_duration_metadata() -> None:
    """Test duration sensors use typed Home Assistant metadata."""
    descriptions = {
        description.key: description
        for description in SENSOR_DESCRIPTIONS
    }

    for key in ("current_cycle_duration", "last_cycle_duration"):
        description = descriptions[key]
        assert description.device_class is SensorDeviceClass.DURATION
        assert (
            description.native_unit_of_measurement
            is UnitOfTime.SECONDS
        )
        assert description.state_class is SensorStateClass.MEASUREMENT


def test_last_cycle_energy_uses_total_energy_metadata() -> None:
    """Test completed-cycle energy is a source-unit total."""
    assert len(ENERGY_SENSOR_DESCRIPTIONS) == 1
    description = ENERGY_SENSOR_DESCRIPTIONS[0]
    assert description.key == "last_cycle_energy"
    assert description.device_class is SensorDeviceClass.ENERGY
    assert description.state_class is SensorStateClass.TOTAL
    assert description.unit_fn is not None
