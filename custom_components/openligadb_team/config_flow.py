"""Config flow for OpenLigaDB Team Tracker."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import OpenLigaDBApi, OpenLigaDBError
from .const import (
    CONF_LEAGUE_SHORTCUT,
    CONF_TEAM_ID,
    CONF_TEAM_NAME,
    DEFAULT_LEAGUE,
    DOMAIN,
    current_season,
)

_LOGGER = logging.getLogger(__name__)


class OpenLigaDBConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenLigaDB Team Tracker."""

    VERSION = 1

    def __init__(self) -> None:
        self._league_shortcut: str | None = None
        self._teams: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First step: ask for the league shortcut."""
        errors: dict[str, str] = {}

        if user_input is not None:
            shortcut = user_input[CONF_LEAGUE_SHORTCUT].strip().lower()
            api = OpenLigaDBApi(async_get_clientsession(self.hass))
            season = current_season()
            try:
                teams = await api.get_available_teams(shortcut, season)
                if not teams:
                    # Off-season / next season not in OpenLigaDB yet:
                    # offer last season's teams instead.
                    teams = await api.get_available_teams(shortcut, season - 1)
            except OpenLigaDBError:
                errors["base"] = "cannot_connect"
                teams = []

            if not errors and not teams:
                errors["base"] = "no_teams"

            if not errors:
                self._league_shortcut = shortcut
                self._teams = teams
                return await self.async_step_team()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LEAGUE_SHORTCUT, default=DEFAULT_LEAGUE
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_team(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Second step: pick the team from a dropdown."""
        if user_input is not None:
            team_id = int(user_input[CONF_TEAM_ID])
            team_name = next(
                (
                    t.get("teamName")
                    for t in self._teams
                    if int(t.get("teamId", -1)) == team_id
                ),
                str(team_id),
            )
            await self.async_set_unique_id(
                f"{self._league_shortcut}_{team_id}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"{team_name} ({self._league_shortcut})",
                data={
                    CONF_LEAGUE_SHORTCUT: self._league_shortcut,
                    CONF_TEAM_ID: team_id,
                    CONF_TEAM_NAME: team_name,
                },
            )

        options = [
            SelectOptionDict(
                value=str(t.get("teamId")), label=t.get("teamName", "?")
            )
            for t in sorted(
                self._teams, key=lambda t: t.get("teamName", "")
            )
        ]
        return self.async_show_form(
            step_id="team",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TEAM_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=options, mode=SelectSelectorMode.DROPDOWN
                        )
                    ),
                }
            ),
        )
