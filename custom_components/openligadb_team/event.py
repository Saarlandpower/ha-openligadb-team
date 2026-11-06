"""Event entity: kickoff, goals and final whistle as a pickable trigger."""
from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import OpenLigaDBCoordinator
from .entity import OpenLigaDBEntity

EVENT_TYPES = ["match_started", "goal", "match_ended"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the event entity from a config entry."""
    coordinator: OpenLigaDBCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MatchEventEntity(coordinator)])


class MatchEventEntity(OpenLigaDBEntity, EventEntity):
    """Mirrors the openligadb_team_* bus events as an entity."""

    _key = "match_event"
    _attr_translation_key = "match_event"
    _attr_event_types = EVENT_TYPES

    @property
    def entity_picture(self) -> str | None:
        # Event entities show their event-type icon; no team logo here.
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        # Write the state after every single event: if kickoff and an early
        # goal arrive in the same poll, each one must reach the state machine,
        # otherwise automations would only ever see the last one.
        for event_type, payload in self.coordinator.pending_events:
            if event_type in EVENT_TYPES:
                self._trigger_event(event_type, payload)
                self.async_write_ha_state()
        super()._handle_coordinator_update()
