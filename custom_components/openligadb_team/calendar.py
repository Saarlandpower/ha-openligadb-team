"""Calendar with the team's fixtures."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import OpenLigaDBCoordinator
from .entity import OpenLigaDBEntity
from .helpers import (
    MATCH_DURATION,
    current_or_next_match,
    match_description,
    match_summary,
    matches_in_range,
    parse_utc,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the calendar from a config entry."""
    coordinator: OpenLigaDBCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MatchCalendar(coordinator)])


def _to_event(match: dict[str, Any]) -> CalendarEvent | None:
    kickoff = parse_utc(match.get("date_utc"))
    if kickoff is None:
        return None
    start = dt_util.as_local(kickoff)
    return CalendarEvent(
        start=start,
        end=start + MATCH_DURATION,
        summary=match_summary(match),
        description=match_description(match) or None,
        location=match.get("location"),
        uid=str(match["match_id"]) if match.get("match_id") is not None else None,
    )


class MatchCalendar(OpenLigaDBEntity, CalendarEntity):
    """Fixtures and results (window: 4 weeks back, 12 weeks ahead)."""

    _key = "calendar"
    _attr_translation_key = "calendar"
    _attr_icon = "mdi:calendar-month"

    @property
    def event(self) -> CalendarEvent | None:
        m = current_or_next_match(self._data.get("matches") or [], dt_util.utcnow())
        return _to_event(m) if m else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        events = [
            _to_event(m)
            for m in matches_in_range(
                self._data.get("matches") or [],
                dt_util.as_utc(start_date),
                dt_util.as_utc(end_date),
            )
        ]
        return [e for e in events if e is not None]
