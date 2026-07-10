"""Test the Laundry Monitor config flow."""

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.laundry_monitor.const import (
    CONF_POWER_SENSOR,
    CONF_TRACK_LAUNDRY,
    DOMAIN,
)


async def test_user_flow(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test creating a Laundry Monitor config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Washing Machine",
            CONF_POWER_SENSOR: "sensor.washing_machine_power",
            CONF_TRACK_LAUNDRY: True,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Washing Machine"
    assert result["data"] == {
        CONF_NAME: "Washing Machine",
        CONF_POWER_SENSOR: "sensor.washing_machine_power",
        CONF_TRACK_LAUNDRY: True,
    }


async def test_duplicate_power_sensor_is_rejected(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test that the same power sensor cannot be configured twice."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        title="Existing washing machine",
        data={
            CONF_NAME: "Existing washing machine",
            CONF_POWER_SENSOR: "sensor.washing_machine_power",
            CONF_TRACK_LAUNDRY: False,
        },
    )
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={
            CONF_NAME: "Second washing machine",
            CONF_POWER_SENSOR: "sensor.washing_machine_power",
            CONF_TRACK_LAUNDRY: False,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "already_configured"}
