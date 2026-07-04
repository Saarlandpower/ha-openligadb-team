"""Tests for pure match helper functions."""
from datetime import datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "openligadb_team"
    / "helpers.py"
)
SPEC = spec_from_file_location("openligadb_team_helpers", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
pick_next_and_last_match = MODULE.pick_next_and_last_match
slim_match = MODULE.slim_match
normalize_team_name = MODULE.normalize_team_name


def test_slim_match_extracts_relevant_fields() -> None:
    """The reduced match payload should keep the dashboard-relevant values."""
    match = {
        "matchDateTimeUTC": "2026-06-12T18:00:00Z",
        "matchDateTime": "2026-06-12T20:00:00",
        "team1": {"teamName": "A", "teamIconUrl": "home.png"},
        "team2": {"teamName": "B", "teamIconUrl": "away.png"},
        "matchIsFinished": True,
        "matchResults": [
            {"resultTypeID": 1, "pointsTeam1": 0, "pointsTeam2": 0},
            {"resultTypeID": 2, "pointsTeam1": 2, "pointsTeam2": 1},
        ],
        "leagueName": "3. Liga",
        "group": {"groupName": "34. Spieltag"},
        "location": {"locationStadium": "Ludwigspark"},
    }

    assert slim_match(match) == {
        "date_utc": "2026-06-12T18:00:00Z",
        "date_local": "2026-06-12T20:00:00",
        "home": "A",
        "away": "B",
        "home_icon": "home.png",
        "away_icon": "away.png",
        "finished": True,
        "score": "2:1",
        "league": "3. Liga",
        "matchday": "34. Spieltag",
        "location": "Ludwigspark",
    }


def test_pick_next_and_last_match_ignores_stale_unfinished_matches() -> None:
    """An outdated unfinished match should not block the real upcoming fixture."""
    now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
    matches = [
        {
            "date_utc": "2026-06-12T06:00:00Z",
            "finished": False,
            "home": "Old",
            "away": "Fixture",
        },
        {
            "date_utc": "2026-06-12T19:00:00Z",
            "finished": False,
            "home": "Next",
            "away": "Fixture",
        },
        {
            "date_utc": "2026-06-10T17:00:00Z",
            "finished": True,
            "home": "Last",
            "away": "Finished",
        },
    ]

    next_match, last_match = pick_next_and_last_match(matches, now=now)

    assert next_match == matches[1]
    assert last_match == matches[2]


def test_normalize_team_name_matches_across_competition_formatting() -> None:
    """League and cup spellings of the same club should normalize equal."""
    assert normalize_team_name("1. FC Saarbrücken") == normalize_team_name(
        "1.FC Saarbrücken"
    )


def test_normalize_team_name_is_case_insensitive() -> None:
    """Comparisons should not be sensitive to case."""
    assert normalize_team_name("Hertha BSC") == normalize_team_name("HERTHA bsc")
