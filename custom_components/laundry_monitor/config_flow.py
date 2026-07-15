"""Config and options flows for Laundry Monitor."""

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
    OptionsFlowWithReload,
)
from homeassistant.const import (
    CONF_NAME,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntityFilterSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    CONF_ACTIVITY_THRESHOLD,
    CONF_ARMING_TIMEOUT,
    CONF_DOOR_SENSOR,
    CONF_ENERGY_SENSOR,
    CONF_FINISHED_RETENTION,
    CONF_FINISH_CONFIRMATION,
    CONF_LEAK_SENSOR,
    CONF_PLUG_SWITCH,
    CONF_POWER_SENSOR,
    CONF_POWER_UNAVAILABLE_GRACE,
    CONF_RUNNING_FINISH_CONFIRMATION,
    CONF_SNAPSHOT_MAX_AGE,
    CONF_SPIN_ACTIVITY_MAX_AGE,
    CONF_SPIN_MIN_CYCLE_TIME,
    CONF_SPIN_REQUIRED_EVENTS,
    CONF_SPIN_WINDOW,
    CONF_START_CONFIRMATION,
    CONF_START_THRESHOLD,
    CONF_TRACK_LAUNDRY,
    CONF_VIBRATION_SENSOR,
    DEFAULT_ACTIVITY_THRESHOLD,
    DEFAULT_ARMING_TIMEOUT,
    DEFAULT_FINISHED_RETENTION,
    DEFAULT_FINISH_CONFIRMATION,
    DEFAULT_POWER_UNAVAILABLE_GRACE,
    DEFAULT_RUNNING_FINISH_CONFIRMATION,
    DEFAULT_SNAPSHOT_MAX_AGE,
    DEFAULT_NAME,
    DEFAULT_SPIN_ACTIVITY_MAX_AGE,
    DEFAULT_SPIN_MIN_CYCLE_TIME,
    DEFAULT_SPIN_REQUIRED_EVENTS,
    DEFAULT_SPIN_WINDOW,
    DEFAULT_START_CONFIRMATION,
    DEFAULT_START_THRESHOLD,
    DEFAULT_TRACK_LAUNDRY,
    DOMAIN,
)

_INTEGER_OPTION_KEYS = (
    CONF_START_CONFIRMATION,
    CONF_SPIN_REQUIRED_EVENTS,
    CONF_SPIN_WINDOW,
    CONF_SPIN_MIN_CYCLE_TIME,
    CONF_SPIN_ACTIVITY_MAX_AGE,
    CONF_FINISH_CONFIRMATION,
    CONF_RUNNING_FINISH_CONFIRMATION,
    CONF_ARMING_TIMEOUT,
    CONF_FINISHED_RETENTION,
    CONF_POWER_UNAVAILABLE_GRACE,
    CONF_SNAPSHOT_MAX_AGE,
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


def _number_selector(
    *,
    minimum: float,
    maximum: float,
    step: float,
    unit: str | None = None,
) -> NumberSelector:
    """Create a box-mode number selector."""
    config = NumberSelectorConfig(
        min=minimum,
        max=maximum,
        step=step,
        mode=NumberSelectorMode.BOX,
    )

    if unit is not None:
        config["unit_of_measurement"] = unit

    return NumberSelector(config)


def _config_schema(
    defaults: Mapping[str, Any] | None = None,
) -> vol.Schema:
    """Build the integration configuration schema."""
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


def _options_schema(
    defaults: Mapping[str, Any] | None = None,
) -> vol.Schema:
    """Build the detector-options schema."""
    defaults = defaults or {}

    return vol.Schema(
        {
            vol.Required(
                CONF_ACTIVITY_THRESHOLD,
                default=defaults.get(
                    CONF_ACTIVITY_THRESHOLD,
                    DEFAULT_ACTIVITY_THRESHOLD,
                ),
            ): _number_selector(
                minimum=0.1,
                maximum=10000,
                step=0.1,
                unit=UnitOfPower.WATT,
            ),
            vol.Required(
                CONF_START_THRESHOLD,
                default=defaults.get(
                    CONF_START_THRESHOLD,
                    DEFAULT_START_THRESHOLD,
                ),
            ): _number_selector(
                minimum=0.1,
                maximum=10000,
                step=0.1,
                unit=UnitOfPower.WATT,
            ),
            vol.Required(
                CONF_START_CONFIRMATION,
                default=defaults.get(
                    CONF_START_CONFIRMATION,
                    DEFAULT_START_CONFIRMATION,
                ),
            ): _number_selector(
                minimum=0,
                maximum=600,
                step=1,
                unit=UnitOfTime.SECONDS,
            ),
            vol.Required(
                CONF_SPIN_REQUIRED_EVENTS,
                default=defaults.get(
                    CONF_SPIN_REQUIRED_EVENTS,
                    DEFAULT_SPIN_REQUIRED_EVENTS,
                ),
            ): _number_selector(
                minimum=1,
                maximum=20,
                step=1,
            ),
            vol.Required(
                CONF_SPIN_WINDOW,
                default=defaults.get(
                    CONF_SPIN_WINDOW,
                    DEFAULT_SPIN_WINDOW,
                ),
            ): _number_selector(
                minimum=1,
                maximum=3600,
                step=1,
                unit=UnitOfTime.SECONDS,
            ),
            vol.Required(
                CONF_SPIN_MIN_CYCLE_TIME,
                default=defaults.get(
                    CONF_SPIN_MIN_CYCLE_TIME,
                    DEFAULT_SPIN_MIN_CYCLE_TIME,
                ),
            ): _number_selector(
                minimum=0,
                maximum=21600,
                step=1,
                unit=UnitOfTime.SECONDS,
            ),
            vol.Required(
                CONF_SPIN_ACTIVITY_MAX_AGE,
                default=defaults.get(
                    CONF_SPIN_ACTIVITY_MAX_AGE,
                    DEFAULT_SPIN_ACTIVITY_MAX_AGE,
                ),
            ): _number_selector(
                minimum=0,
                maximum=3600,
                step=1,
                unit=UnitOfTime.SECONDS,
            ),
            vol.Required(
                CONF_FINISH_CONFIRMATION,
                default=defaults.get(
                    CONF_FINISH_CONFIRMATION,
                    DEFAULT_FINISH_CONFIRMATION,
                ),
            ): _number_selector(
                minimum=1,
                maximum=3600,
                step=1,
                unit=UnitOfTime.SECONDS,
            ),
            vol.Required(
                CONF_RUNNING_FINISH_CONFIRMATION,
                default=defaults.get(
                    CONF_RUNNING_FINISH_CONFIRMATION,
                    DEFAULT_RUNNING_FINISH_CONFIRMATION,
                ),
            ): _number_selector(
                minimum=60,
                maximum=21600,
                step=1,
                unit=UnitOfTime.SECONDS,
            ),
            vol.Required(
                CONF_ARMING_TIMEOUT,
                default=defaults.get(
                    CONF_ARMING_TIMEOUT,
                    DEFAULT_ARMING_TIMEOUT,
                ),
            ): _number_selector(
                minimum=0,
                maximum=86400,
                step=1,
                unit=UnitOfTime.SECONDS,
            ),
            vol.Required(
                CONF_FINISHED_RETENTION,
                default=defaults.get(
                    CONF_FINISHED_RETENTION,
                    DEFAULT_FINISHED_RETENTION,
                ),
            ): _number_selector(
                minimum=0,
                maximum=86400,
                step=1,
                unit=UnitOfTime.SECONDS,
            ),
            vol.Required(
                CONF_POWER_UNAVAILABLE_GRACE,
                default=defaults.get(
                    CONF_POWER_UNAVAILABLE_GRACE,
                    DEFAULT_POWER_UNAVAILABLE_GRACE,
                ),
            ): _number_selector(
                minimum=0,
                maximum=3600,
                step=1,
                unit=UnitOfTime.SECONDS,
            ),
            vol.Required(
                CONF_SNAPSHOT_MAX_AGE,
                default=defaults.get(
                    CONF_SNAPSHOT_MAX_AGE,
                    DEFAULT_SNAPSHOT_MAX_AGE,
                ),
            ): _number_selector(
                minimum=3600,
                maximum=604800,
                step=1,
                unit=UnitOfTime.SECONDS,
            ),
        }
    )


def _normalize_options(
    user_input: Mapping[str, Any],
) -> dict[str, int | float]:
    """Normalize selector values before storing them."""
    normalized: dict[str, int | float] = {
        CONF_ACTIVITY_THRESHOLD: float(
            user_input[CONF_ACTIVITY_THRESHOLD]
        ),
        CONF_START_THRESHOLD: float(
            user_input[CONF_START_THRESHOLD]
        ),
    }

    normalized.update(
        {
            key: int(user_input[key])
            for key in _INTEGER_OPTION_KEYS
        }
    )
    return normalized


class LaundryMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Laundry Monitor."""

    VERSION = CONFIG_ENTRY_VERSION
    MINOR_VERSION = CONFIG_ENTRY_MINOR_VERSION

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> LaundryMonitorOptionsFlow:
        """Return the Laundry Monitor options flow."""
        return LaundryMonitorOptionsFlow()

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


class LaundryMonitorOptionsFlow(OptionsFlowWithReload):
    """Handle detector options for Laundry Monitor."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Manage detector thresholds and confirmation periods."""
        errors: dict[str, str] = {}

        if user_input is not None:
            normalized = _normalize_options(user_input)

            if (
                normalized[CONF_ACTIVITY_THRESHOLD]
                > normalized[CONF_START_THRESHOLD]
            ):
                errors[
                    CONF_ACTIVITY_THRESHOLD
                ] = "activity_threshold_above_start"
            else:
                return self.async_create_entry(
                    title="",
                    data=normalized,
                )

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(
                user_input
                if user_input is not None
                else self.config_entry.options
            ),
            errors=errors,
        )
