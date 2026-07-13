"""Button entities for Laundry Monitor."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LaundryMonitorConfigEntry
from .entity import LaundryMonitorEntity
from .runtime import LaundryMonitorRuntime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LaundryMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Laundry Monitor button entities."""
    if not entry.runtime_data.tracking_enabled:
        return

    async_add_entities([LaundryMonitorMarkUnloadedButton(entry.runtime_data)])


class LaundryMonitorMarkUnloadedButton(
    LaundryMonitorEntity,
    ButtonEntity,
):
    """Button used to explicitly mark the machine as unloaded."""

    _attr_translation_key = "mark_unloaded"

    def __init__(self, runtime: LaundryMonitorRuntime) -> None:
        """Initialize the button."""
        super().__init__(runtime, "mark_unloaded")

    async def async_press(self) -> None:
        """Handle the button press."""
        self.runtime.async_mark_unloaded()
