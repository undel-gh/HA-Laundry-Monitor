"""Repairs and issue-registry support for Laundry Monitor."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)

from .const import (
    CONF_DOOR_SENSOR,
    CONF_POWER_SENSOR,
    CONF_VIBRATION_SENSOR,
    DOMAIN,
)

REQUIRED_SOURCE_KEYS: tuple[str, ...] = (
    CONF_POWER_SENSOR,
    CONF_DOOR_SENSOR,
    CONF_VIBRATION_SENSOR,
)

ISSUE_TRANSLATION_KEY = "required_source_unavailable"


def required_source_issue_id(
    entry_id: str,
    source_key: str,
) -> str:
    """Return the stable issue ID for a required source."""
    return f"{entry_id}_{source_key}_unavailable"


class LaundryMonitorRepairs:
    """Maintain Repairs issues for required source availability."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the Repairs manager."""
        self._hass = hass
        self._entry = entry
        self._remove_listener: Callable[[], None] | None = None

    @property
    def _required_entities(self) -> tuple[str, ...]:
        """Return configured required source entity IDs."""
        return tuple(
            entity_id
            for source_key in REQUIRED_SOURCE_KEYS
            if isinstance(
                (entity_id := self._entry.data.get(source_key)),
                str,
            )
            and entity_id
        )

    @callback
    def async_start(self) -> None:
        """Create current issues and subscribe to source changes."""
        self._async_update_all_issues()

        if self._required_entities:
            self._remove_listener = async_track_state_change_event(
                self._hass,
                self._required_entities,
                self._async_source_state_changed,
            )

    @callback
    def async_stop(self) -> None:
        """Remove subscriptions and issues for an unloaded entry."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None

        for source_key in REQUIRED_SOURCE_KEYS:
            async_delete_issue(
                self._hass,
                DOMAIN,
                required_source_issue_id(
                    self._entry.entry_id,
                    source_key,
                ),
            )

    @callback
    def _async_source_state_changed(
        self,
        event: Event[EventStateChangedData],
    ) -> None:
        """Update the issue belonging to a changed source."""
        entity_id = event.data["entity_id"]

        for source_key in REQUIRED_SOURCE_KEYS:
            if self._entry.data.get(source_key) == entity_id:
                self._async_update_issue(source_key)
                return

    @callback
    def _async_update_all_issues(self) -> None:
        """Update Repairs issues for all required sources."""
        for source_key in REQUIRED_SOURCE_KEYS:
            self._async_update_issue(source_key)

    @callback
    def _async_update_issue(self, source_key: str) -> None:
        """Create or delete one required-source issue."""
        entity_id = self._entry.data.get(source_key)
        issue_id = required_source_issue_id(
            self._entry.entry_id,
            source_key,
        )

        state = (
            self._hass.states.get(entity_id)
            if isinstance(entity_id, str) and entity_id
            else None
        )
        available = (
            state is not None
            and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
        )

        if available:
            async_delete_issue(
                self._hass,
                DOMAIN,
                issue_id,
            )
            return

        display_entity_id = (
            entity_id
            if isinstance(entity_id, str) and entity_id
            else source_key
        )

        async_create_issue(
            self._hass,
            DOMAIN,
            issue_id,
            data={
                "entry_id": self._entry.entry_id,
                "entity_id": display_entity_id,
                "source_key": source_key,
            },
            is_fixable=False,
            is_persistent=False,
            severity=IssueSeverity.WARNING,
            translation_key=ISSUE_TRANSLATION_KEY,
            translation_placeholders={
                "name": self._entry.title,
                "entity_id": display_entity_id,
            },
        )
