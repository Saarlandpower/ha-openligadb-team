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


# Markers that identify a women's competition in OpenLigaDB league metadata.
# OpenLigaDB shares a single teamId across a club's squads: Borussia Dortmund
# is teamId 7 for both the men's Bundesliga side and the women's Regionalliga
# side, so getmatchesbyteamid/7 returns both. We keep only matches whose
# competition matches the gender/category of the configured league, otherwise
# a women's Regionalliga fixture (played most weekends) becomes the "next
# match" of a bl1 sensor. Clubs whose women's team has its own OpenLigaDB id
# (e.g. Eintracht Frankfurt, SC Freiburg) never hit this, which is why the
# problem only surfaced for the BVB.
_WOMEN_MARKERS = ("frauen", "women", "damen", "féminin", "feminin")


def is_womens_competition(
    league_shortcut: str | None, league_name: str | None = None
) -> bool:
    """Heuristic: does this OpenLigaDB league belong to women's football?"""
    blob = f"{league_shortcut or ''} {league_name or ''}".lower()
    return any(marker in blob for marker in _WOMEN_MARKERS)


def drop_placeholder_fixtures(
    matches: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Remove OpenLigaDB placeholder draw dumps from a match list.

    OpenLigaDB sometimes publishes a competition's draw as a placeholder: every
    fixture of a team is stamped with one identical kickoff time (e.g. the
    2026/27 Champions League league phase lists all eight opponents at the same
    date/time in a parallel ``ucl2026`` competition, next to the correctly
    scheduled ``ucl``). A team cannot play two matches simultaneously, so any
    cluster of 2+ matches sharing the exact kickoff time within the same league
    is bogus and dropped; the correctly scheduled fixture survives in the
    properly dated competition.
    """
    counts: dict[tuple[Any, Any], int] = {}
    for m in matches:
        ts = m.get("matchDateTimeUTC")
        if ts:
            key = (m.get("leagueId"), ts)
            counts[key] = counts.get(key, 0) + 1
    return [
        m
        for m in matches
        if not (
            m.get("matchDateTimeUTC")
            and counts.get((m.get("leagueId"), m.get("matchDateTimeUTC")), 0) > 1
        )
    ]


def find_team_logo_in_matches(
    matches: list[dict[str, Any]], team_name: str
) -> str | None:
    """Find the configured team's logo in a match list.

    Cup competitions can have no table data at all, so the integration cannot
    always rely on the table row to expose the team's icon. In that case we
    inspect the fetched fixtures/results and pick the first matching home/away
    logo for the configured club name.
    """
    wanted = normalize_team_name(team_name)
    for match in matches:
        if normalize_team_name(match.get("home") or "") == wanted:
            return match.get("home_icon")
        if normalize_team_name(match.get("away") or "") == wanted:
            return match.get("away_icon")
    return None


def final_score(match: dict[str, Any]) -> str | None:
    """Extract the final result (resultTypeID 2 = Endergebnis) from a match."""
    for result in match.get("matchResults") or []:
        if result.get("resultTypeID") == 2:
            return f"{result.get('pointsTeam1')}:{result.get('pointsTeam2')}"
    return None


def slim_match(match: dict[str, Any]) -> dict[str, Any]:
    """Reduce an OpenLigaDB match object to dashboard friendly essentials."""
    return {
        "match_id": match.get("matchID"),
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


# --- Live mode ---------------------------------------------------------------

# Polling cadence. Kept here (not in const.py) so the pure helpers stay
# importable without the package and remain unit-testable on their own.
LIVE_INTERVAL = timedelta(minutes=1)
MATCHDAY_INTERVAL = timedelta(minutes=15)
IDLE_INTERVAL = timedelta(minutes=60)

# A match counts as live from kickoff until OpenLigaDB flags it finished, but
# at most this long: extra time, penalties and a late "finished" flag fit in,
# and a match whose flag is never set stops being polled every minute.
LIVE_WINDOW = timedelta(hours=3, minutes=30)

# How close a kickoff (or how recent a match) has to be for the 15-minute
# matchday cadence instead of the hourly idle one.
MATCHDAY_LOOKAHEAD = timedelta(hours=12)
MATCHDAY_LOOKBEHIND = timedelta(hours=6)


def is_live(match: dict[str, Any], now: datetime) -> bool:
    """Is the match running right now (kicked off, not yet finished)?"""
    if match.get("finished"):
        return False
    kickoff = parse_utc(match.get("date_utc"))
    return kickoff is not None and kickoff <= now < kickoff + LIVE_WINDOW


def compute_update_interval(
    matches: list[dict[str, Any]], now: datetime
) -> timedelta:
    """Pick the next polling interval from the team's fixtures.

    - a match is live: every minute
    - kickoff is closer than the matchday interval: wake up right at kickoff
    - a match within the next 12 h or in the last 6 h: every 15 minutes
      (the table keeps changing while the rest of the matchday is played)
    - otherwise: hourly
    """
    if any(is_live(m, now) for m in matches):
        return LIVE_INTERVAL

    busy = False
    for m in matches:
        kickoff = parse_utc(m.get("date_utc"))
        if kickoff is None:
            continue
        delta = kickoff - now
        if timedelta(0) < delta <= MATCHDAY_INTERVAL and not m.get("finished"):
            return max(delta, LIVE_INTERVAL)
        if -MATCHDAY_LOOKBEHIND <= delta <= MATCHDAY_LOOKAHEAD:
            busy = True
    return MATCHDAY_INTERVAL if busy else IDLE_INTERVAL


def slim_goals(match: dict[str, Any]) -> list[dict[str, Any]]:
    """Goals in order, each with the side that benefitted from it.

    The side is derived from which running score went up, which stays correct
    for own goals too (OpenLigaDB's scoringTeamId is not documented for them).
    """
    raw = sorted(
        match.get("goals") or [],
        key=lambda g: (
            (g.get("scoreTeam1") or 0) + (g.get("scoreTeam2") or 0),
            g.get("matchMinute") or 0,
            g.get("goalID") or 0,
        ),
    )
    goals: list[dict[str, Any]] = []
    prev_home, prev_away = 0, 0
    for g in raw:
        home = g.get("scoreTeam1") or 0
        away = g.get("scoreTeam2") or 0
        if home > prev_home:
            side = "home"
        elif away > prev_away:
            side = "away"
        else:
            side = None
        goals.append(
            {
                "goal_id": g.get("goalID"),
                "minute": g.get("matchMinute"),
                "scorer": g.get("goalGetterName"),
                "score_home": home,
                "score_away": away,
                "side": side,
                "penalty": bool(g.get("isPenalty")),
                "own_goal": bool(g.get("isOwnGoal")),
                "overtime": bool(g.get("isOvertime")),
            }
        )
        prev_home, prev_away = home, away
    return goals


def build_snapshot(
    matches: list[dict[str, Any]], now: datetime
) -> dict[Any, dict[str, Any]]:
    """Per-match state used to detect kickoffs, goals and final whistles."""
    snapshot: dict[Any, dict[str, Any]] = {}
    for m in matches:
        match_id = m.get("matchID")
        if match_id is None:
            continue
        slim = slim_match(m)
        kickoff = parse_utc(slim["date_utc"])
        goals = slim_goals(m)
        if goals:
            score_home, score_away = goals[-1]["score_home"], goals[-1]["score_away"]
        else:
            score_home, score_away = 0, 0
        final = slim["score"]
        if slim["finished"] and final:
            score_home, score_away = (int(x) for x in final.split(":"))
        snapshot[match_id] = {
            **slim,
            "home_id": (m.get("team1") or {}).get("teamId"),
            "away_id": (m.get("team2") or {}).get("teamId"),
            "started": kickoff is not None and kickoff <= now,
            "goals": goals,
            "score_home": score_home,
            "score_away": score_away,
        }
    return snapshot


def team_side(match: dict[str, Any], team_id: int, team_name: str) -> str | None:
    """Is the tracked team playing at home or away in this match?"""
    wanted = normalize_team_name(team_name)
    if match.get("home_id") == team_id or normalize_team_name(match.get("home") or "") == wanted:
        return "home"
    if match.get("away_id") == team_id or normalize_team_name(match.get("away") or "") == wanted:
        return "away"
    return None


def diff_match_events(
    old: dict[Any, dict[str, Any]] | None,
    new: dict[Any, dict[str, Any]],
    team_id: int,
    team_name: str,
) -> list[tuple[str, dict[str, Any]]]:
    """Compare two snapshots and return (event_type, data) pairs.

    Nothing fires on the very first snapshot or for a match seen for the first
    time, so a Home Assistant restart in the middle of a match does not replay
    its kickoff and goals. If a whole match slipped through between two polls
    (scheduled before, finished now), only the final whistle is reported.
    """
    if old is None:
        return []

    events: list[tuple[str, dict[str, Any]]] = []
    for match_id, cur in new.items():
        prev = old.get(match_id)
        if prev is None:
            continue

        side = team_side(cur, team_id, team_name)
        base = {
            "match_id": match_id,
            "competition": cur.get("league"),
            "matchday": cur.get("matchday"),
            "home": cur.get("home"),
            "away": cur.get("away"),
            "team_side": side,
            "score": f"{cur['score_home']}:{cur['score_away']}",
            "score_home": cur["score_home"],
            "score_away": cur["score_away"],
        }
        missed_whole_match = not prev["started"] and cur["finished"]

        if not prev["started"] and cur["started"] and not cur["finished"]:
            events.append(("match_started", dict(base)))

        if not missed_whole_match:
            seen = {g["goal_id"] for g in prev["goals"]}
            for goal in cur["goals"]:
                if goal["goal_id"] in seen:
                    continue
                for_team = None if side is None or goal["side"] is None else goal["side"] == side
                events.append(
                    (
                        "goal",
                        {
                            **base,
                            "score": f"{goal['score_home']}:{goal['score_away']}",
                            "score_home": goal["score_home"],
                            "score_away": goal["score_away"],
                            "minute": goal["minute"],
                            "scorer": goal["scorer"],
                            "scoring_side": goal["side"],
                            "scoring_team": cur.get(goal["side"]) if goal["side"] else None,
                            "for_team": for_team,
                            "penalty": goal["penalty"],
                            "own_goal": goal["own_goal"],
                            "overtime": goal["overtime"],
                        },
                    )
                )

        if not prev["finished"] and cur["finished"]:
            result = None
            if side is not None:
                own = cur["score_home"] if side == "home" else cur["score_away"]
                other = cur["score_away"] if side == "home" else cur["score_home"]
                result = "won" if own > other else "lost" if own < other else "draw"
            events.append(("match_ended", {**base, "result": result}))

    return events


def annotate_live(
    matches: list[dict[str, Any]],
    snapshot: dict[Any, dict[str, Any]],
    now: datetime,
) -> list[dict[str, Any]]:
    """Add ``live`` and ``live_score`` to slim matches for the sensors."""
    out = []
    for m in matches:
        live = is_live(m, now)
        snap = snapshot.get(m.get("match_id")) or {}
        out.append(
            {
                **m,
                "live": live,
                "live_score": f"{snap.get('score_home', 0)}:{snap.get('score_away', 0)}"
                if live
                else None,
            }
        )
    return out


# --- Calendar / matchday helpers ----------------------------------------------

# Calendar entries span a regular match incl. half-time and stoppage time.
MATCH_DURATION = timedelta(hours=2)


def match_summary(match: dict[str, Any]) -> str:
    """Calendar title, with the result once the match is finished."""
    title = f"{match.get('home')} – {match.get('away')}"
    if match.get("finished") and match.get("score"):
        title += f" ({match['score']})"
    return title


def match_description(match: dict[str, Any]) -> str:
    """Calendar description: competition and matchday."""
    return " · ".join(
        part for part in (match.get("league"), match.get("matchday")) if part
    )


def matches_in_range(
    matches: list[dict[str, Any]], start: datetime, end: datetime
) -> list[dict[str, Any]]:
    """Matches whose calendar slot overlaps [start, end)."""
    found = []
    for m in matches:
        kickoff = parse_utc(m.get("date_utc"))
        if kickoff is None:
            continue
        if kickoff < end and kickoff + MATCH_DURATION > start:
            found.append(m)
    return found


def current_or_next_match(
    matches: list[dict[str, Any]], now: datetime
) -> dict[str, Any] | None:
    """The match running now, otherwise the next one (for the calendar state)."""
    upcoming = [
        (kickoff, m)
        for m in matches
        if (kickoff := parse_utc(m.get("date_utc"))) is not None
        and kickoff + MATCH_DURATION > now
    ]
    return min(upcoming, key=lambda x: x[0])[1] if upcoming else None


def has_match_on_day(
    matches: list[dict[str, Any]], day_start: datetime, day_end: datetime
) -> bool:
    """Is there a kickoff between day_start and day_end (local day bounds)?"""
    for m in matches:
        kickoff = parse_utc(m.get("date_utc"))
        if kickoff is not None and day_start <= kickoff < day_end:
            return True
    return False


def live_match(matches: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The match currently flagged live by annotate_live, if any."""
    return next((m for m in matches if m.get("live")), None)
