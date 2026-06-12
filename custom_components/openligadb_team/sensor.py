"""Sensor platform for OpenLigaDB Team Tracker."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OpenLigaDBCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator: OpenLigaDBCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            TablePositionSensor(coordinator),
            PointsSensor(coordinator),
            NextMatchSensor(coordinator),
            LastMatchSensor(coordinator),
            MatchesSensor(coordinator),
            TableSensor(coordinator),
        ]
    )


class OpenLigaDBBaseSensor(CoordinatorEntity[OpenLigaDBCoordinator], SensorEntity):
    """Common base for all OpenLigaDB sensors."""

    _attr_has_entity_name = True
    _key: str = "base"

    def __init__(self, coordinator: OpenLigaDBCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.entry
        self._attr_unique_id = f"{entry.entry_id}_{self._key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.team_name,
            manufacturer="OpenLigaDB",
            model=coordinator.league_shortcut.upper(),
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.openligadb.de",
        )

    @property
    def _data(self) -> dict[str, Any]:
        return self.coordinator.data or {}


class TablePositionSensor(OpenLigaDBBaseSensor):
    """Current table position."""

    _key = "position"
    _attr_translation_key = "position"
    _attr_icon = "mdi:podium"

    @property
    def native_value(self) -> int | None:
        row = self._data.get("team_row")
        return row.get("position") if row else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        row = self._data.get("team_row") or {}
        return {
            "season": self._data.get("season"),
            "matches": row.get("matches"),
            "won": row.get("won"),
            "draw": row.get("draw"),
            "lost": row.get("lost"),
            "goals": row.get("goals"),
            "opponent_goals": row.get("opponent_goals"),
            "goal_diff": row.get("goal_diff"),
        }


class PointsSensor(OpenLigaDBBaseSensor):
    """Current points."""

    _key = "points"
    _attr_translation_key = "points"
    _attr_icon = "mdi:counter"
    _attr_native_unit_of_measurement = "Punkte"

    @property
    def native_value(self) -> int | None:
        row = self._data.get("team_row")
        return row.get("points") if row else None


class NextMatchSensor(OpenLigaDBBaseSensor):
    """Next scheduled match."""

    _key = "next_match"
    _attr_translation_key = "next_match"
    _attr_icon = "mdi:soccer-field"

    @property
    def native_value(self) -> str | None:
        m = self._data.get("next_match")
        if not m:
            return None
        return f"{m['home']} – {m['away']}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._data.get("next_match") or {}


class LastMatchSensor(OpenLigaDBBaseSensor):
    """Last finished match."""

    _key = "last_match"
    _attr_translation_key = "last_match"
    _attr_icon = "mdi:scoreboard"

    @property
    def native_value(self) -> str | None:
        m = self._data.get("last_match")
        if not m:
            return None
        return f"{m['home']} {m['score']} {m['away']}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._data.get("last_match") or {}


class MatchesSensor(OpenLigaDBBaseSensor):
    """All matches in the configured window (incl. cup games)."""

    _key = "matches"
    _attr_translation_key = "matches"
    _attr_icon = "mdi:calendar-month"

    @property
    def native_value(self) -> int:
        return len(self._data.get("matches") or [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"matches": self._data.get("matches") or []}


class TableSensor(OpenLigaDBBaseSensor):
    """Full league table."""

    _key = "table"
    _attr_translation_key = "table"
    _attr_icon = "mdi:table"

    @property
    def native_value(self) -> int:
        return len(self._data.get("table") or [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "season": self._data.get("season"),
            "table": self._data.get("table") or [],
        }
