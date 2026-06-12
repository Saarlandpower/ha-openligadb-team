"""Constants for the OpenLigaDB Team Tracker integration."""
from datetime import date

DOMAIN = "openligadb_team"

BASE_URL = "https://api.openligadb.de"

CONF_LEAGUE_SHORTCUT = "league_shortcut"
CONF_TEAM_ID = "team_id"
CONF_TEAM_NAME = "team_name"

DEFAULT_LEAGUE = "bl3"
DEFAULT_SCAN_INTERVAL_MINUTES = 15

# Matches window for getmatchesbyteamid (weeks)
WEEKS_PAST = 3
WEEKS_FUTURE = 5


def current_season(today: date | None = None) -> int:
    """Return the OpenLigaDB season year for the given date.

    German football seasons run from roughly July to June. OpenLigaDB
    identifies a season by its starting year, e.g. 2026 == season 2026/27.
    """
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1
