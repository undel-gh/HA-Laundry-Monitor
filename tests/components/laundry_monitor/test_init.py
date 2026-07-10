"""Test Laundry Monitor setup and unloading."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.laundry_monitor.const import (
    CONF_POWER_SENSOR,
    CONF_TRACK_LAUNDRY,
    DOMAIN,
)

def test_integration_modules_can_be_imported() -> None:
    """Test that integration modules can be imported."""
    from custom_components.laundry_monitor import async_setup_entry
    from custom_components.laundry_monitor.config_flow import (
        LaundryMonitorConfigFlow,
    )

    assert async_setup_entry is not None
    assert LaundryMonitorConfigFlow is not None

async def test_setup_and_unload_entry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test that a config entry can be loaded and unloaded."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Washing Machine",
        data={
            CONF_NAME: "Washing Machine",
            CONF_POWER_SENSOR: "sensor.washing_machine_power",
            CONF_TRACK_LAUNDRY: False,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.entry_id in hass.data[DOMAIN]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert DOMAIN not in hass.data
