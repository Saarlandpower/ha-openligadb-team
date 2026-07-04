"""Data update coordinator for OpenLigaDB Team Tracker."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OpenLigaDBApi, OpenLigaDBError
from .const import (
    CONF_LEAGUE_SHORTCUT,
    CONF_TEAM_ID,
    CONF_TEAM_NAME,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    WEEKS_FUTURE,
    WEEKS_PAST,
    current_season,
)
from .helpers import normalize_team_name, pick_next_and_last_match, slim_match

_LOGGER = logging.getLogger(__name__)


class OpenLigaDBCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch table and team matches from OpenLigaDB."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES),
        )
        self.entry = entry
        self.api = OpenLigaDBApi(async_get_clientsession(hass))
        self.league_shortcut: str = entry.data[CONF_LEAGUE_SHORTCUT]
        self.team_id: int = int(entry.data[CONF_TEAM_ID])
        self.team_name: str = entry.data[CONF_TEAM_NAME]

    async def _async_resolve_team_id(self, season: int) -> int:
        """Re-resolve the team id for this season by name.

        OpenLigaDB occasionally assigns a new internal team id for a
        competition when a new season starts (observed for cup competitions
        such as the DFB-Pokal, where the id is not shared with the league).
        Resolving by name on every refresh keeps matches flowing without the
        user having to reconfigure the integration whenever OpenLigaDB does
        this. Falls back to the originally configured id if the team can't
        be found (e.g. season not yet published).
        """
        try:
            teams = await self.api.get_available_teams(self.league_shortcut, season)
        except OpenLigaDBError:
            return self.team_id

        wanted = normalize_team_name(self.team_name)
        for team in teams:
            if normalize_team_name(team.get("teamName", "")) == wanted:
                return int(team["teamId"])
        return self.team_id

    async def _async_update_data(self) -> dict[str, Any]:
        season = current_season()
        data_season = season
        try:
            table = await self.api.get_table(self.league_shortcut, season)
            # Off-season: fall back to the previous season's final table
            if not table:
                data_season = season - 1
                table = await self.api.get_table(self.league_shortcut, season - 1)

            # Resolve against the actual current season, not data_season: cup
            # competitions never have a table, so data_season would otherwise
            # always drift back a year and re-resolve to a stale team id.
            team_id = await self._async_resolve_team_id(season)
            matches = await self.api.get_matches_by_team(
                team_id, WEEKS_PAST, WEEKS_FUTURE
            )
        except OpenLigaDBError as err:
            raise UpdateFailed(str(err)) from err

        slim_table = [
            {
                "position": idx,
                "team": row.get("teamName"),
                "team_id": row.get("teamInfoId"),
                "icon": row.get("teamIconUrl"),
                "matches": row.get("matches"),
                "won": row.get("won"),
                "draw": row.get("draw"),
                "lost": row.get("lost"),
                "goals": row.get("goals"),
                "opponent_goals": row.get("opponentGoals"),
                "goal_diff": row.get("goalDiff"),
                "points": row.get("points"),
            }
            for idx, row in enumerate(table, start=1)
        ]

        own_row = next(
            (row for row in slim_table if row["team_id"] == team_id), None
        )

        slim_matches = sorted(
            (slim_match(m) for m in matches),
            key=lambda m: m["date_utc"] or "",
        )
        next_match, last_match = pick_next_and_last_match(slim_matches)

        return {
            "season": data_season,
            "table": slim_table,
            "team_row": own_row,
            "matches": slim_matches,
            "next_match": next_match,
            "last_match": last_match,
        }
