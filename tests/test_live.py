"""Tests for live mode: polling cadence and event detection."""
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "openligadb_team"
    / "helpers.py"
)
SPEC = spec_from_file_location("openligadb_team_helpers_live", MODULE_PATH)
assert SPEC and SPEC.loader
H = module_from_spec(SPEC)
SPEC.loader.exec_module(H)

KICKOFF = datetime(2026, 11, 7, 13, 0, tzinfo=timezone.utc)
TEAM_ID = 40
TEAM = "FC Bayern München"


def raw_match(goals=(), finished=False, match_id=1):
    return {
        "matchID": match_id,
        "matchDateTimeUTC": KICKOFF.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "matchDateTime": "2026-11-07T14:00:00",
        "team1": {"teamId": TEAM_ID, "teamName": TEAM},
        "team2": {"teamId": 7, "teamName": "Borussia Dortmund"},
        "matchIsFinished": finished,
        "matchResults": (
            [{"resultTypeID": 2, "pointsTeam1": goals[-1][0] if goals else 0,
              "pointsTeam2": goals[-1][1] if goals else 0}]
            if finished
            else []
        ),
        "goals": [
            {"goalID": 100 + i, "scoreTeam1": h, "scoreTeam2": a,
             "matchMinute": 10 * (i + 1), "goalGetterName": f"Spieler {i}",
             "isPenalty": False, "isOwnGoal": False, "isOvertime": False}
            for i, (h, a) in enumerate(goals)
        ],
        "leagueName": "1. Fußball-Bundesliga",
        "group": {"groupName": "10. Spieltag"},
    }


def snap(now, **kw):
    return H.build_snapshot([raw_match(**kw)], now)


def slim(minutes_from_kickoff_to_now, finished=False):
    return {"date_utc": KICKOFF.isoformat(), "finished": finished}, KICKOFF + timedelta(
        minutes=minutes_from_kickoff_to_now
    )


# --- polling cadence --------------------------------------------------------

def test_interval_is_one_minute_while_live() -> None:
    m, now = slim(30)
    assert H.compute_update_interval([m], now) == H.LIVE_INTERVAL


def test_interval_wakes_up_at_kickoff() -> None:
    m, now = slim(-7)
    assert H.compute_update_interval([m], now) == timedelta(minutes=7)


def test_interval_never_below_one_minute_before_kickoff() -> None:
    m, now = slim(0)
    now -= timedelta(seconds=20)
    assert H.compute_update_interval([m], now) == H.LIVE_INTERVAL


def test_interval_matchday_before_and_after_match() -> None:
    m, now = slim(-6 * 60)
    assert H.compute_update_interval([m], now) == H.MATCHDAY_INTERVAL
    m, now = slim(4 * 60, finished=True)
    assert H.compute_update_interval([m], now) == H.MATCHDAY_INTERVAL


def test_interval_idle_without_nearby_match() -> None:
    m, now = slim(-3 * 24 * 60)
    assert H.compute_update_interval([m], now) == H.IDLE_INTERVAL
    assert H.compute_update_interval([], now) == H.IDLE_INTERVAL


def test_live_window_ends_if_finished_flag_never_set() -> None:
    m, now = slim(4 * 60)
    assert not H.is_live(m, now)


# --- goals ------------------------------------------------------------------

def test_slim_goals_detects_side_including_own_goals() -> None:
    goals = H.slim_goals(raw_match(goals=[(0, 1), (1, 1), (2, 1)]))
    assert [g["side"] for g in goals] == ["away", "home", "home"]


def test_slim_goals_sorts_by_running_score() -> None:
    m = raw_match(goals=[(1, 0), (2, 0)])
    m["goals"].reverse()
    assert [g["score_home"] for g in H.slim_goals(m)] == [1, 2]


# --- events -----------------------------------------------------------------

def events(old, new):
    return H.diff_match_events(old, new, TEAM_ID, TEAM)


def test_no_events_on_first_snapshot() -> None:
    assert events(None, snap(KICKOFF + timedelta(minutes=50), goals=[(1, 0)])) == []


def test_kickoff_event() -> None:
    old = snap(KICKOFF - timedelta(minutes=1))
    new = snap(KICKOFF + timedelta(minutes=1))
    (etype, data), = events(old, new)
    assert etype == "match_started"
    assert data["team_side"] == "home"
    assert data["score"] == "0:0"


def test_goal_event_for_and_against_team() -> None:
    t = KICKOFF + timedelta(minutes=30)
    old = snap(t, goals=[(1, 0)])
    new = snap(t + timedelta(minutes=1), goals=[(1, 0), (1, 1), (2, 1)])
    result = events(old, new)
    assert [e for e, _ in result] == ["goal", "goal"]
    first, second = result[0][1], result[1][1]
    assert first["scoring_team"] == "Borussia Dortmund"
    assert first["for_team"] is False
    assert first["score"] == "1:1"
    assert second["for_team"] is True
    assert second["score"] == "2:1"
    assert second["scorer"] == "Spieler 2"


def test_kickoff_and_early_goal_in_same_poll() -> None:
    old = snap(KICKOFF - timedelta(minutes=1))
    new = snap(KICKOFF + timedelta(minutes=2), goals=[(0, 1)])
    assert [e for e, _ in events(old, new)] == ["match_started", "goal"]


def test_final_whistle_reports_result() -> None:
    t = KICKOFF + timedelta(minutes=100)
    old = snap(t, goals=[(2, 1)])
    new = snap(t + timedelta(minutes=1), goals=[(2, 1)], finished=True)
    (etype, data), = events(old, new)
    assert etype == "match_ended"
    assert data["result"] == "won"
    assert data["score"] == "2:1"


def test_missed_whole_match_only_reports_final_whistle() -> None:
    old = snap(KICKOFF - timedelta(minutes=5))
    new = snap(KICKOFF + timedelta(hours=2), goals=[(0, 1), (0, 2)], finished=True)
    (etype, data), = events(old, new)
    assert etype == "match_ended"
    assert data["result"] == "lost"


def test_no_duplicate_events_without_changes() -> None:
    t = KICKOFF + timedelta(minutes=40)
    s = snap(t, goals=[(1, 0)])
    assert events(s, snap(t + timedelta(minutes=1), goals=[(1, 0)])) == []


def test_annotate_live_adds_live_score() -> None:
    now = KICKOFF + timedelta(minutes=60)
    s = H.build_snapshot([raw_match(goals=[(1, 0), (1, 1)])], now)
    m = H.slim_match(raw_match(goals=[(1, 0), (1, 1)]))
    (out,) = H.annotate_live([m], s, now)
    assert out["live"] is True
    assert out["live_score"] == "1:1"


# --- calendar / matchday ------------------------------------------------------

def cal_match(minutes_from_now_kickoff, now, **kw):
    return {"date_utc": (now + timedelta(minutes=minutes_from_now_kickoff)).isoformat(),
            "home": "A", "away": "B", "finished": False, "score": None,
            "league": "3. Liga", "matchday": "12. Spieltag", **kw}


def test_match_summary_adds_result_when_finished() -> None:
    now = KICKOFF
    assert H.match_summary(cal_match(0, now)) == "A – B"
    assert H.match_summary(cal_match(0, now, finished=True, score="2:1")) == "A – B (2:1)"
    assert H.match_description(cal_match(0, now)) == "3. Liga · 12. Spieltag"


def test_matches_in_range_includes_overlapping_running_match() -> None:
    now = KICKOFF
    running = cal_match(-60, now)
    later = cal_match(24 * 60, now)
    assert H.matches_in_range([running, later], now, now + timedelta(hours=1)) == [running]


def test_current_or_next_prefers_running_match() -> None:
    now = KICKOFF
    old = cal_match(-5 * 60, now)
    running = cal_match(-30, now)
    nxt = cal_match(3 * 24 * 60, now)
    assert H.current_or_next_match([old, running, nxt], now) is running
    assert H.current_or_next_match([old, nxt], now) is nxt
    assert H.current_or_next_match([old], now) is None


def test_has_match_on_day() -> None:
    day = datetime(2026, 11, 7, tzinfo=timezone.utc)
    assert H.has_match_on_day([cal_match(0, KICKOFF)], day, day + timedelta(days=1))
    assert not H.has_match_on_day([cal_match(24 * 60, KICKOFF)], day, day + timedelta(days=1))


def test_live_match_picks_flagged_match() -> None:
    a, b = {"live": False}, {"live": True}
    assert H.live_match([a, b]) is b
    assert H.live_match([a]) is None
