"""The Laundry Monitor integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .runtime import LaundryMonitorRuntime
from .storage import LaundryStateStore

type LaundryMonitorConfigEntry = ConfigEntry[LaundryMonitorRuntime]

_PLATFORM_ENUMS = tuple(Platform(platform) for platform in PLATFORMS)
DATA_STATE_STORE = f"{DOMAIN}_state_store"


def _get_state_store(hass: HomeAssistant) -> LaundryStateStore:
    """Return the shared Laundry Monitor state store."""
    store = hass.data.get(DATA_STATE_STORE)

    if store is None:
        store = LaundryStateStore(hass)
        hass.data[DATA_STATE_STORE] = store
        runtime = LaundryMonitorRuntime(
            hass=hass,
            entry=entry,
            state_store=_get_state_store(hass),
        )
    return store

async def async_setup_entry(
    hass: HomeAssistant,
    entry: LaundryMonitorConfigEntry,
) -> bool:
    """Set up Laundry Monitor from a config entry."""
    runtime = LaundryMonitorRuntime(hass=hass, entry=entry)
    entry.runtime_data = runtime

    await runtime.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORM_ENUMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: LaundryMonitorConfigEntry,
) -> bool:
    """Unload a Laundry Monitor config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        _PLATFORM_ENUMS,
    )

    if unload_ok:
        await entry.runtime_data.async_stop()

    return unload_ok
    
async def async_remove_entry(hass, entry) -> None:
    store = LaundryStateStore(hass)
    await store.async_remove(entry.entry_id)

