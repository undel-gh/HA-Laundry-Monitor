"""Base entity for Laundry Monitor."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .runtime import LaundryMonitorRuntime


class LaundryMonitorEntity(Entity):
    """Base class for Laundry Monitor entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        runtime: LaundryMonitorRuntime,
        key: str,
    ) -> None:
        """Initialize a Laundry Monitor entity."""
        self.runtime = runtime
        self._attr_unique_id = f"{runtime.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.entry.entry_id)},
            name=runtime.name,
            manufacturer="Laundry Monitor",
            model="Washing Machine Monitor",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to runtime updates."""
        await super().async_added_to_hass()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self.runtime.signal,
                self._handle_runtime_update,
            )
        )

    @callback
    def _handle_runtime_update(self) -> None:
        """Write the latest runtime value to Home Assistant."""
        self.async_write_ha_state()
