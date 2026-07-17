"""Test the Laundry Monitor config flow."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.laundry_monitor.const import (
    CONF_CURRENT_SENSOR,
    CONF_DOOR_SENSOR,
    CONF_POWER_SENSOR,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
)


async def test_user_flow(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test creating an entry with all recommended sources."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    user_input = {
        CONF_NAME: "Washing Machine",
        CONF_POWER_SENSOR: "sensor.washing_machine_power",
        CONF_CURRENT_SENSOR: "sensor.washing_machine_current",
        CONF_DOOR_SENSOR: "binary_sensor.washing_machine_door",
        CONF_VIBRATION_SENSOR: "binary_sensor.washing_machine_vibration",
        CONF_TRACK_LAUNDRY: True,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Washing Machine"
    assert result["data"] == user_input


async def test_power_only_configuration_is_allowed(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test basic operation needs only the power sensor."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    user_input = {
        CONF_NAME: "Washing Machine",
        CONF_POWER_SENSOR: "sensor.washing_machine_power",
        CONF_TRACK_LAUNDRY: False,
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input,
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == user_input


async def test_duplicate_power_sensor_is_rejected(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test the same required power sensor cannot be reused."""
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
    assert result["errors"] == {"base": "already_configured"}


async def test_only_power_sensor_is_required_in_schema(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> None:
    """Test only the power selector is required."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    markers = {
        marker.schema: marker
        for marker in result["data_schema"].schema
    }

    assert isinstance(markers[CONF_POWER_SENSOR], vol.Required)
    assert isinstance(markers[CONF_CURRENT_SENSOR], vol.Optional)
    assert isinstance(markers[CONF_DOOR_SENSOR], vol.Optional)
    assert isinstance(markers[CONF_VIBRATION_SENSOR], vol.Optional)
