"""Binary sensors for OpenLigaDB Team Tracker."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import OpenLigaDBCoordinator
from .entity import OpenLigaDBEntity
from .helpers import has_match_on_day, live_match


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors from a config entry."""
    coordinator: OpenLigaDBCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LiveBinarySensor(coordinator), MatchdayBinarySensor(coordinator)])


class LiveBinarySensor(OpenLigaDBEntity, BinarySensorEntity):
    """On while a match of the team is being played."""

    _key = "live"
    _attr_translation_key = "live"
    _attr_icon = "mdi:soccer"

    @property
    def is_on(self) -> bool:
        return bool(self._data.get("live"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        m = live_match(self._data.get("matches") or []) or {}
        return {
            "home": m.get("home"),
            "away": m.get("away"),
            "live_score": m.get("live_score"),
        }


class MatchdayBinarySensor(OpenLigaDBEntity, BinarySensorEntity):
    """On if the team has a kickoff today (local time)."""

    _key = "matchday_today"
    _attr_translation_key = "matchday_today"
    _attr_icon = "mdi:calendar-star"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Flip at midnight without waiting for the next coordinator update.
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._midnight, hour=0, minute=0, second=5
            )
        )

    @callback
    def _midnight(self, _now) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        start = dt_util.start_of_local_day()
        return has_match_on_day(
            self._data.get("matches") or [], start, start + timedelta(days=1)
        )
