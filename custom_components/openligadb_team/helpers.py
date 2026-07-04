"""Pure helpers used by the OpenLigaDB Team Tracker integration."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any


def normalize_team_name(name: str) -> str:
    """Normalize a team name for tolerant cross-competition comparisons.

    OpenLigaDB formats the same club's name slightly differently between
    competitions (e.g. "1. FC Saarbruecken" in the league vs "1.FC
    Saarbruecken" in a cup), so comparisons strip everything but
    letters/digits.
    """
    return re.sub(r"[^a-z0-9]", "", name.lower())


def final_score(match: dict[str, Any]) -> str | None:
    """Extract the final result (resultTypeID 2 = Endergebnis) from a match."""
    for result in match.get("matchResults") or []:
        if result.get("resultTypeID") == 2:
            return f"{result.get('pointsTeam1')}:{result.get('pointsTeam2')}"
    return None


def slim_match(match: dict[str, Any]) -> dict[str, Any]:
    """Reduce an OpenLigaDB match object to dashboard friendly essentials."""
    return {
        "date_utc": match.get("matchDateTimeUTC"),
        "date_local": match.get("matchDateTime"),
        "home": (match.get("team1") or {}).get("teamName"),
        "away": (match.get("team2") or {}).get("teamName"),
        "home_icon": (match.get("team1") or {}).get("teamIconUrl"),
        "away_icon": (match.get("team2") or {}).get("teamIconUrl"),
        "finished": match.get("matchIsFinished", False),
        "score": final_score(match),
        "league": match.get("leagueName"),
        "matchday": (match.get("group") or {}).get("groupName"),
        "location": (match.get("location") or {}).get("locationStadium")
        if match.get("location")
        else None,
    }


def parse_utc(value: str | None) -> datetime | None:
    """Parse an ISO timestamp into an aware UTC datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def pick_next_and_last_match(
    matches: list[dict[str, Any]], now: datetime | None = None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Pick the next relevant match and the last finished match."""
    now = now or datetime.now(timezone.utc)
    next_match = next(
        (
            match
            for match in matches
            if not match["finished"]
            and (parse_utc(match["date_utc"]) or now) >= now - timedelta(hours=3)
        ),
        None,
    )
    last_match = next((match for match in reversed(matches) if match["finished"]), None)
    return next_match, last_match
