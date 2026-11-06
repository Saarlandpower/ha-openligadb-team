"""Set up the integration in a real Home Assistant and play a match through."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

import custom_components.openligadb_team.coordinator  # noqa: F401  (patch target)

DOMAIN = "openligadb_team"
KICKOFF = datetime(2026, 11, 7, 13, 0, tzinfo=timezone.utc)
API = "custom_components.openligadb_team.api.OpenLigaDBApi"

TABLE = [
    {"teamInfoId": 40, "teamName": "FC Bayern München", "teamIconUrl": "https://x/fcb.png",
     "matches": 9, "won": 8, "draw": 1, "lost": 0, "goals": 30, "opponentGoals": 5,
     "goalDiff": 25, "points": 25},
    {"teamInfoId": 7, "teamName": "Borussia Dortmund", "teamIconUrl": "https://x/bvb.png",
     "matches": 9, "won": 6, "draw": 1, "lost": 2, "goals": 20, "opponentGoals": 10,
     "goalDiff": 10, "points": 19},
]


def make_match(goals=(), finished=False):
    return {
        "matchID": 4711,
        "matchDateTimeUTC": KICKOFF.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "matchDateTime": "2026-11-07T14:00:00",
        "leagueShortcut": "bl1",
        "leagueName": "1. Fußball-Bundesliga 2026/2027",
        "group": {"groupName": "10. Spieltag"},
        "team1": {"teamId": 40, "teamName": "FC Bayern München", "teamIconUrl": "https://x/fcb.png"},
        "team2": {"teamId": 7, "teamName": "Borussia Dortmund", "teamIconUrl": "https://x/bvb.png"},
        "matchIsFinished": finished,
        "matchResults": (
            [{"resultTypeID": 2, "pointsTeam1": goals[-1][0], "pointsTeam2": goals[-1][1]}]
            if finished and goals else []
        ),
        "goals": [
            {"goalID": 900 + i, "scoreTeam1": h, "scoreTeam2": a, "matchMinute": m,
             "goalGetterName": n, "isPenalty": False, "isOwnGoal": False, "isOvertime": False}
            for i, (h, a, m, n) in enumerate(goals)
        ],
        "location": {"locationStadium": "Allianz Arena"},
    }


class FakeApi:
    """Stands in for OpenLigaDBApi; the test moves the match forward."""

    state = {"goals": [], "finished": False}

    def __init__(self, *_a, **_kw):
        pass

    async def get_available_teams(self, *_a):
        return [{"teamId": 40, "teamName": "FC Bayern München"}]

    async def get_table(self, *_a):
        return copy.deepcopy(TABLE)

    async def get_matches_by_team(self, *_a):
        return [make_match(FakeApi.state["goals"], FakeApi.state["finished"])]

    async def get_match(self, _match_id):
        return make_match(FakeApi.state["goals"], FakeApi.state["finished"])


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, to: datetime) -> None:
    freezer.move_to(to)
    async_fire_time_changed(hass, to)
    await hass.async_block_till_done()


async def test_full_match(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await hass.config.async_set_time_zone("Europe/Berlin")
    FakeApi.state = {"goals": [], "finished": False}
    freezer.move_to(KICKOFF - timedelta(hours=2))

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"league_shortcut": "bl1", "team_id": 40, "team_name": "FC Bayern München"},
        unique_id="bl1_40",
    )
    entry.add_to_hass(hass)
    with patch("custom_components.openligadb_team.coordinator.OpenLigaDBApi", FakeApi):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        reg = er.async_get(hass)
        ids = {e.unique_id.split("_", 1)[1]: e.entity_id
               for e in er.async_entries_for_config_entry(reg, entry.entry_id)}
        print(ids)
        for key in ("position", "points", "next_match", "last_match", "matches", "table",
                    "live_score", "live", "matchday_today", "calendar", "match_event"):
            assert key in ids, key

        # before kickoff
        assert hass.states.get(ids["position"]).state == "1"
        assert hass.states.get(ids["matchday_today"]).state == "on"
        assert hass.states.get(ids["live"]).state == "off"
        assert hass.states.get(ids["live_score"]).state == "unknown"
        cal = hass.states.get(ids["calendar"])
        assert cal.state == "off"
        assert cal.attributes["message"] == "FC Bayern München – Borussia Dortmund"
        assert cal.attributes["location"] == "Allianz Arena"

        goal_bus = async_capture_events(hass, "openligadb_team_goal")
        changes: list[str] = []
        hass.bus.async_listen(
            "state_changed",
            lambda e: changes.append(e.data["new_state"].attributes.get("event_type"))
            if e.data["entity_id"] == ids["match_event"] and e.data.get("new_state") else None,
        )

        # kickoff + early goal in the same poll: both must reach the entity
        FakeApi.state["goals"] = [(1, 0, 1, "H. Kane")]
        await _tick(hass, freezer, KICKOFF + timedelta(minutes=2))
        await _tick(hass, freezer, KICKOFF + timedelta(minutes=17))  # coordinator was on 15/60 min
        print("changes", changes)
        assert "match_started" in changes and "goal" in changes
        assert changes.index("match_started") < changes.index("goal")
        assert hass.states.get(ids["live"]).state == "on"
        assert hass.states.get(ids["live_score"]).state == "1:0"
        assert hass.states.get(ids["live_score"]).attributes["last_goal"]["scorer"] == "H. Kane"
        assert hass.states.get(ids["calendar"]).state == "on"
        ev = hass.states.get(ids["match_event"])
        assert ev.attributes["event_type"] == "goal"
        assert ev.attributes["for_team"] is True

        # live mode now polls every minute
        FakeApi.state["goals"].append((1, 1, 50, "S. Guirassy"))
        await _tick(hass, freezer, KICKOFF + timedelta(minutes=18, seconds=30))
        assert hass.states.get(ids["live_score"]).state == "1:1"
        ev = hass.states.get(ids["match_event"])
        assert ev.attributes["for_team"] is False
        assert ev.attributes["scoring_team"] == "Borussia Dortmund"
        assert len(goal_bus) == 2

        # final whistle
        FakeApi.state["goals"].append((2, 1, 89, "J. Musiala"))
        FakeApi.state["finished"] = True
        await _tick(hass, freezer, KICKOFF + timedelta(minutes=19, seconds=40))
        ev = hass.states.get(ids["match_event"])
        assert ev.attributes["event_type"] == "match_ended"
        assert ev.attributes["result"] == "won"
        assert hass.states.get(ids["live"]).state == "off"
        assert hass.states.get(ids["live_score"]).state == "unknown"
        assert hass.states.get(ids["last_match"]).state == "FC Bayern München 2:1 Borussia Dortmund"

        # calendar range query
        events = await hass.services.async_call(
            "calendar", "get_events",
            {"entity_id": ids["calendar"],
             "start_date_time": (KICKOFF - timedelta(days=1)).isoformat(),
             "end_date_time": (KICKOFF + timedelta(days=1)).isoformat()},
            blocking=True, return_response=True,
        )
        (cal_ev,) = events[ids["calendar"]]["events"]
        assert cal_ev["summary"] == "FC Bayern München – Borussia Dortmund (2:1)"
        assert cal_ev["start"].startswith("2026-11-07T14:00:00+01:00")

        # translated names (en)
        assert hass.states.get(ids["match_event"]).name.endswith("Match event")

        assert await hass.config_entries.async_unload(entry.entry_id)
