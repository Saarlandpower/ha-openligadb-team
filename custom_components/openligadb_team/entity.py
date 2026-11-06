"""Shared base entity for OpenLigaDB Team Tracker."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OpenLigaDBCoordinator


class OpenLigaDBEntity(CoordinatorEntity[OpenLigaDBCoordinator]):
    """One device per tracked team; every entity hangs off it."""

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

    @property
    def entity_picture(self) -> str | None:
        """Expose the team logo as the entity picture when available."""
        return self._data.get("team_logo")
