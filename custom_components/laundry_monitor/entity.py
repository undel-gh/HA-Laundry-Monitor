"""Base entity for Laundry Monitor."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .runtime import LaundryMonitorRuntime


# A dispatcher notification is not necessarily a Home Assistant state change.


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
        self._last_published_signature: object = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.entry.entry_id)},
            name=runtime.name,
            manufacturer="Laundry Monitor",
            model="Washing Machine Monitor",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to runtime updates."""
        await super().async_added_to_hass()
        # Home Assistant publishes the initial state during entity setup.
        self._last_published_signature = self._runtime_state_signature()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self.runtime.signal,
                self._handle_runtime_update,
            )
        )

    def _runtime_state_signature(self) -> object:
        """Return the state relevant to this entity's HA publication."""
        return (self.available, self.state)

    @callback
    def _handle_runtime_update(self) -> None:
        """Publish only when this entity's observable state changes."""
        signature = self._runtime_state_signature()
        if signature == self._last_published_signature:
            return
        self._last_published_signature = signature
        self.async_write_ha_state()
