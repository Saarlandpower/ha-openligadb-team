"""Data update coordinator for OpenLigaDB Team Tracker."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

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
from .helpers import (
    annotate_live,
    build_snapshot,
    compute_update_interval,
    diff_match_events,
    drop_placeholder_fixtures,
    find_team_logo_in_matches,
    is_live,
    is_womens_competition,
    normalize_team_name,
    pick_next_and_last_match,
    slim_match,
)

_LOGGER = logging.getLogger(__name__)

# While a match is live only that match is fetched every minute; the table
# and the full fixture list are refreshed at most this often.
FULL_REFRESH_WHILE_LIVE = timedelta(minutes=15)


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

        # Raw API state kept between polls so live updates can patch single
        # matches instead of refetching everything every minute.
        self._table: list[dict[str, Any]] = []
        self._raw_matches: list[dict[str, Any]] | None = None
        self._resolved_team_id: int = self.team_id
        self._data_season: int = current_season()
        self._last_full_refresh: datetime | None = None
        self._snapshot: dict[Any, dict[str, Any]] | None = None

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
        now = dt_util.utcnow()
        live_ids = [
            match_id
            for match_id, match in (self._snapshot or {}).items()
            if is_live(match, now)
        ]
        full_due = (
            self._raw_matches is None
            or not live_ids
            or self._last_full_refresh is None
            or now - self._last_full_refresh >= FULL_REFRESH_WHILE_LIVE
        )

        try:
            if full_due:
                await self._async_full_refresh()
                self._last_full_refresh = now
            else:
                await self._async_refresh_live_matches(live_ids)
        except OpenLigaDBError as err:
            raise UpdateFailed(str(err)) from err

        snapshot = build_snapshot(self._raw_matches or [], now)
        for event_type, payload in diff_match_events(
            self._snapshot, snapshot, self._resolved_team_id, self.team_name
        ):
            _LOGGER.debug("Firing %s_%s: %s", DOMAIN, event_type, payload)
            self.hass.bus.async_fire(
                f"{DOMAIN}_{event_type}",
                {
                    "entry_id": self.entry.entry_id,
                    "team": self.team_name,
                    "league_shortcut": self.league_shortcut,
                    **payload,
                },
            )
        self._snapshot = snapshot

        data = self._build_data(snapshot, now)

        interval = compute_update_interval(data["matches"], now)
        if interval != self.update_interval:
            _LOGGER.debug("%s: next update in %s", self.team_name, interval)
        self.update_interval = interval
        return data

    async def _async_full_refresh(self) -> None:
        """Fetch table and all team matches (the regular refresh)."""
        season = current_season()
        data_season = season
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

        # OpenLigaDB shares one teamId across a club's men's and women's
        # squads, so getmatchesbyteamid mixes competitions of both genders.
        # Keep only matches whose competition matches the category of the
        # configured league (a men's bl1 sensor drops the women's Regionalliga
        # fixtures, and vice versa) so next/last/matches stay on one squad.
        configured_is_women = is_womens_competition(self.league_shortcut)
        matches = [
            m
            for m in matches
            if is_womens_competition(m.get("leagueShortcut"), m.get("leagueName"))
            == configured_is_women
        ]

        # Drop OpenLigaDB placeholder draw dumps (see helper docstring).
        matches = drop_placeholder_fixtures(matches)

        self._table = table
        self._raw_matches = matches
        self._resolved_team_id = team_id
        self._data_season = data_season

    async def _async_refresh_live_matches(self, match_ids: list[Any]) -> None:
        """Patch only the live matches with fresh data (one small request each)."""
        by_id = {m.get("matchID"): i for i, m in enumerate(self._raw_matches or [])}
        for match_id in match_ids:
            fresh = await self.api.get_match(match_id)
            if isinstance(fresh, dict) and match_id in by_id:
                self._raw_matches[by_id[match_id]] = fresh

    def _build_data(
        self, snapshot: dict[Any, dict[str, Any]], now: datetime
    ) -> dict[str, Any]:
        """Turn the cached raw API data into what the sensors expose."""
        team_id = self._resolved_team_id
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
            for idx, row in enumerate(self._table, start=1)
        ]

        own_row = next(
            (row for row in slim_table if row["team_id"] == team_id), None
        )

        slim_matches = annotate_live(
            sorted(
                (slim_match(m) for m in self._raw_matches or []),
                key=lambda m: m["date_utc"] or "",
            ),
            snapshot,
            now,
        )
        next_match, last_match = pick_next_and_last_match(slim_matches, now)
        team_logo = (own_row or {}).get("icon") or find_team_logo_in_matches(
            slim_matches, self.team_name
        )

        return {
            "season": self._data_season,
            "table": slim_table,
            "team_row": own_row,
            "team_logo": team_logo,
            "matches": slim_matches,
            "next_match": next_match,
            "last_match": last_match,
            "live": any(m["live"] for m in slim_matches),
        }
