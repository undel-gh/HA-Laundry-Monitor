"""Config flow for Laundry Monitor."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntityFilterSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    CONF_DOOR_SENSOR,
    CONF_ENERGY_SENSOR,
    CONF_LEAK_SENSOR,
    CONF_PLUG_SWITCH,
    CONF_POWER_SENSOR,
    CONF_TEMPERATURE_SENSOR,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DEFAULT_NAME,
    DEFAULT_TRACK_LAUNDRY,
    DOMAIN,
)


def _suggested_value(value: Any) -> dict[str, Any]:
    """Return a schema description containing a suggested value."""
    return {"suggested_value": value}


def _entity_selector(
    *,
    domain: str,
    device_class: str | list[str] | None = None,
) -> EntitySelector:
    """Create an entity selector using the current filter syntax."""
    entity_filter = EntityFilterSelectorConfig(domain=domain)

    if device_class is not None:
        entity_filter["device_class"] = device_class

    return EntitySelector(
        EntitySelectorConfig(filter=entity_filter),
    )


def _config_schema(
    defaults: Mapping[str, Any] | None = None,
) -> vol.Schema:
    """Build the configuration schema."""
    defaults = defaults or {}

    return vol.Schema(
        {
            vol.Required(
                CONF_NAME,
                default=defaults.get(CONF_NAME, DEFAULT_NAME),
            ): TextSelector(
                TextSelectorConfig(type="text"),
            ),
            vol.Required(
                CONF_POWER_SENSOR,
                description=_suggested_value(
                    defaults.get(CONF_POWER_SENSOR)
                ),
            ): _entity_selector(
                domain="sensor",
                device_class=SensorDeviceClass.POWER,
            ),
            vol.Optional(
                CONF_DOOR_SENSOR,
                description=_suggested_value(
                    defaults.get(CONF_DOOR_SENSOR)
                ),
            ): _entity_selector(
                domain="binary_sensor",
                device_class=[
                    BinarySensorDeviceClass.DOOR,
                    BinarySensorDeviceClass.OPENING,
                ],
            ),
            vol.Optional(
                CONF_VIBRATION_SENSOR,
                description=_suggested_value(
                    defaults.get(CONF_VIBRATION_SENSOR)
                ),
            ): _entity_selector(
                domain="binary_sensor",
                device_class=BinarySensorDeviceClass.VIBRATION,
            ),
            vol.Optional(
                CONF_LEAK_SENSOR,
                description=_suggested_value(
                    defaults.get(CONF_LEAK_SENSOR)
                ),
            ): _entity_selector(
                domain="binary_sensor",
                device_class=BinarySensorDeviceClass.MOISTURE,
            ),
            vol.Optional(
                CONF_ENERGY_SENSOR,
                description=_suggested_value(
                    defaults.get(CONF_ENERGY_SENSOR)
                ),
            ): _entity_selector(
                domain="sensor",
                device_class=SensorDeviceClass.ENERGY,
            ),
            vol.Optional(
                CONF_TEMPERATURE_SENSOR,
                description=_suggested_value(
                    defaults.get(CONF_TEMPERATURE_SENSOR)
                ),
            ): _entity_selector(
                domain="sensor",
                device_class=SensorDeviceClass.TEMPERATURE,
            ),
            vol.Optional(
                CONF_PLUG_SWITCH,
                description=_suggested_value(
                    defaults.get(CONF_PLUG_SWITCH)
                ),
            ): _entity_selector(domain="switch"),
            vol.Optional(
                CONF_TRACK_LAUNDRY,
                default=defaults.get(
                    CONF_TRACK_LAUNDRY,
                    DEFAULT_TRACK_LAUNDRY,
                ),
            ): BooleanSelector(),
        }
    )


class LaundryMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Laundry Monitor."""

    VERSION = CONFIG_ENTRY_VERSION
    MINOR_VERSION = CONFIG_ENTRY_MINOR_VERSION

    def _power_sensor_is_configured(
        self,
        power_sensor: str,
        *,
        exclude_entry_id: str | None = None,
    ) -> bool:
        """Return whether a power sensor is used by another entry."""
        return any(
            entry.entry_id != exclude_entry_id
            and entry.data.get(CONF_POWER_SENSOR) == power_sensor
            for entry in self._async_current_entries()
        )

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial user configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if self._power_sensor_is_configured(
                user_input[CONF_POWER_SENSOR]
            ):
                errors["base"] = "already_configured"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_config_schema(user_input),
            errors=errors,
        )

    async def test_user_flow(
       hass: HomeAssistant,
       enable_custom_integrations: None,
    ) -> None:

    async def test_duplicate_power_sensor_is_rejected(
       hass: HomeAssistant,
       enable_custom_integrations: None,
    ) -> None:
    
    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing config entry."""
        entry: ConfigEntry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            if self._power_sensor_is_configured(
                user_input[CONF_POWER_SENSOR],
                exclude_entry_id=entry.entry_id,
            ):
                errors["base"] = "already_configured"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    title=user_input[CONF_NAME],
                    data=user_input,
                    reload_even_if_entry_is_unchanged=False,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_config_schema(
                user_input if user_input is not None else entry.data
            ),
            errors=errors,
        )
