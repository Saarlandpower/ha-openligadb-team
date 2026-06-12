"""Minimal async client for the OpenLigaDB REST API."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import BASE_URL


class OpenLigaDBError(Exception):
    """Raised when the OpenLigaDB API cannot be reached or returns garbage."""


class OpenLigaDBApi:
    """Tiny wrapper around the public OpenLigaDB endpoints used here."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _get(self, path: str) -> Any:
        url = f"{BASE_URL}/{path}"
        try:
            async with self._session.get(
                url, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise OpenLigaDBError(f"Error fetching {url}: {err}") from err

    async def get_available_teams(
        self, league_shortcut: str, season: int
    ) -> list[dict[str, Any]]:
        return await self._get(f"getavailableteams/{league_shortcut}/{season}")

    async def get_table(
        self, league_shortcut: str, season: int
    ) -> list[dict[str, Any]]:
        return await self._get(f"getbltable/{league_shortcut}/{season}")

    async def get_matches_by_team(
        self, team_id: int, weeks_past: int, weeks_future: int
    ) -> list[dict[str, Any]]:
        return await self._get(
            f"getmatchesbyteamid/{team_id}/{weeks_past}/{weeks_future}"
        )
