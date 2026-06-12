"""Data update coordinator for OpenLigaDB Team Tracker."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
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

_LOGGER = logging.getLogger(__name__)


def _final_score(match: dict[str, Any]) -> str | None:
    """Extract the final result (resultTypeID 2 = Endergebnis) from a match."""
    for result in match.get("matchResults") or []:
        if result.get("resultTypeID") == 2:
            return f"{result.get('pointsTeam1')}:{result.get('pointsTeam2')}"
    return None


def _slim_match(match: dict[str, Any]) -> dict[str, Any]:
    """Reduce an OpenLigaDB match object to dashboard friendly essentials."""
    return {
        "date_utc": match.get("matchDateTimeUTC"),
        "date_local": match.get("matchDateTime"),
        "home": (match.get("team1") or {}).get("teamName"),
        "away": (match.get("team2") or {}).get("teamName"),
        "home_icon": (match.get("team1") or {}).get("teamIconUrl"),
        "away_icon": (match.get("team2") or {}).get("teamIconUrl"),
        "finished": match.get("matchIsFinished", False),
        "score": _final_score(match),
        "league": match.get("leagueName"),
        "matchday": (match.get("group") or {}).get("groupName"),
        "location": (match.get("location") or {}).get("locationStadium")
        if match.get("location")
        else None,
    }


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


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

    async def _async_update_data(self) -> dict[str, Any]:
        season = current_season()
        try:
            table = await self.api.get_table(self.league_shortcut, season)
            # Off-season: fall back to the previous season's final table
            if not table:
                table = await self.api.get_table(self.league_shortcut, season - 1)
            matches = await self.api.get_matches_by_team(
                self.team_id, WEEKS_PAST, WEEKS_FUTURE
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
            (row for row in slim_table if row["team_id"] == self.team_id), None
        )

        slim_matches = sorted(
            (_slim_match(m) for m in matches),
            key=lambda m: m["date_utc"] or "",
        )

        now = datetime.now(timezone.utc)
        next_match = next(
            (
                m
                for m in slim_matches
                if not m["finished"]
                and (_parse_utc(m["date_utc"]) or now) >= now - timedelta(hours=3)
            ),
            None,
        )
        last_match = next(
            (m for m in reversed(slim_matches) if m["finished"]),
            None,
        )

        return {
            "season": season,
            "table": slim_table,
            "team_row": own_row,
            "matches": slim_matches,
            "next_match": next_match,
            "last_match": last_match,
        }
