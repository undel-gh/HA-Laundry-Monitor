"""Test Laundry Monitor setup and unloading."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.laundry_monitor.const import (
    CONF_DOOR_SENSOR,
    CONF_POWER_SENSOR,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
)


def test_integration_modules_can_be_imported() -> None:
    """Test that integration modules can be imported."""
    from custom_components.laundry_monitor import async_setup_entry
    from custom_components.laundry_monitor.binary_sensor import (
        LaundryMonitorBinarySensor,
    )
    from custom_components.laundry_monitor.button import (
        LaundryMonitorMarkUnloadedButton,
    )
    from custom_components.laundry_monitor.config_flow import (
        LaundryMonitorConfigFlow,
    )
    from custom_components.laundry_monitor.runtime import LaundryMonitorRuntime
    from custom_components.laundry_monitor.sensor import LaundryMonitorSensor

    assert async_setup_entry is not None
    assert LaundryMonitorConfigFlow is not None
    assert LaundryMonitorRuntime is not None
    assert LaundryMonitorSensor is not None
    assert LaundryMonitorBinarySensor is not None
    assert LaundryMonitorMarkUnloadedButton is not None


async def test_setup_and_unload_entry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test that a config entry and all platforms load and unload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washing Machine",
        data={
            CONF_NAME: "Washing Machine",
            CONF_POWER_SENSOR: "sensor.washing_machine_power",
            CONF_DOOR_SENSOR: "binary_sensor.washing_machine_door",
            CONF_VIBRATION_SENSOR: "binary_sensor.washing_machine_vibration",
            CONF_TRACK_LAUNDRY: False,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
