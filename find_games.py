"""
find_games.py
Which of this week's real NFL games are worth watching given who is on your
roster, and one data-backed thing to watch in each.

Every angle here is computed from nflverse schedule rows — head-to-head results
in the series, the listed starting QB's record against that opponent, the
closing line, the kickoff slot. Nothing is recalled from memory. There is no
narrative or storyline feed in this pipeline, so a game whose history is thin
gets listed with no hook rather than an invented one: a fabricated "he's 1-4
against them at home" is worse than silence, because it reads as researched.

Games are ranked by how much of your lineup is actually on the field in them.

Usage: python find_games.py
"""

import os

from analyze import TEAM_ALIASES
from pull_roster import build_roster_data, load_config
from pull_stats import (
    current_nfl_week,
    pull_schedule,
    pull_schedule_history,
    week_mismatch_note,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# How far back to compute a head-to-head series. Six keeps it inside the
# current era of team names/venues, so no relocation remapping is needed.
HISTORY_SEASONS = 6

# A one- or two-game series is noise, not a trend worth reporting.
MIN_SERIES_GAMES = 3
MIN_QB_SERIES_GAMES = 2


def _nfl_team(sleeper_team):
    """Sleeper's team code in nflverse's spelling (LAR -> LA, etc.)."""
    return TEAM_ALIASES.get(sleeper_team, sleeper_team)


def roster_by_team(players):
    """nflverse team code -> your players on that team."""
    teams = {}
    for p in players:
        team = p.get("team")
        if not team or team == "FA":
            continue
        teams.setdefault(_nfl_team(team), []).append(p)
    return teams


def _margin_for(game, team):
    """Point margin from `team`'s perspective. result is home_score - away_score."""
    result = game.get("result") or 0
    return result if game["home_team"] == team else -result


def series_meetings(history, team_a, team_b, season, week):
    """
    Completed meetings between two teams strictly before this game, newest
    first. The cutoff matters: the current season's file already carries
    results for weeks already played, and if config.json's current_week lags
    behind the real week, later games would otherwise leak in as "history".
    """
    meetings = [
        g for g in history
        if {g["home_team"], g["away_team"]} == {team_a, team_b}
        and (g["season"], g["week"]) < (season, week)
    ]
    meetings.sort(key=lambda g: (g["season"], g["week"]), reverse=True)
    return meetings


def series_record(meetings, team):
    """(wins, losses, ties) for `team` across these meetings."""
    wins = losses = ties = 0
    for g in meetings:
        margin = _margin_for(g, team)
        if margin > 0:
            wins += 1
        elif margin < 0:
            losses += 1
        else:
            ties += 1
    return wins, losses, ties


def qb_series_record(meetings, qb_name, opponent):
    """
    (wins, losses, ties, points_per_game) for a QB in games where nflverse
    listed him as the starter against `opponent`. Returns None if he never
    started in the series — a QB new to his team, usually.
    """
    if not qb_name:
        return None

    wins = losses = ties = 0
    points = []
    for g in meetings:
        if g.get("home_qb_name") == qb_name:
            team, scored = g["home_team"], g.get("home_score")
        elif g.get("away_qb_name") == qb_name:
            team, scored = g["away_team"], g.get("away_score")
        else:
            continue
        if team == opponent:
            continue

        margin = _margin_for(g, team)
        if margin > 0:
            wins += 1
        elif margin < 0:
            losses += 1
        else:
            ties += 1
        if scored is not None:
            points.append(scored)

    played = wins + losses + ties
    if played < MIN_QB_SERIES_GAMES:
        return None

    ppg = round(sum(points) / len(points), 1) if points else None
    return wins, losses, ties, ppg


def build_game(game, history, by_team):
    """One week's game, annotated with your stake in it and its series history."""
    home, away = game["home_team"], game["away_team"]
    mine = by_team.get(home, []) + by_team.get(away, [])
    meetings = series_meetings(history, home, away, game["season"], game["week"])

    return {
        "home": home,
        "away": away,
        "weekday": game.get("weekday"),
        "gametime": game.get("gametime"),
        "stadium": game.get("stadium"),
        "roof": game.get("roof"),
        # International and other neutral-site games still list a home team, so
        # the series' home/away split carries no home-field meaning for them.
        "neutral": game.get("location") == "Neutral",
        "div_game": bool(game.get("div_game")),
        "spread_line": game.get("spread_line"),
        "total_line": game.get("total_line"),
        "home_qb": game.get("home_qb_name"),
        "away_qb": game.get("away_qb_name"),
        # A finished game is a recap, not something to watch. Callers separate
        # the two rather than presenting a decided game as upcoming.
        "final": game.get("result") is not None,
        "home_score": game.get("home_score"),
        "away_score": game.get("away_score"),
        "my_players": mine,
        "my_starters": [p for p in mine if p.get("is_starter")],
        "meetings": meetings,
        # Series record for the team hosting this week, plus that team's record
        # in this series at home — the venue split the example asks for.
        "home_record": series_record(meetings, home),
        "home_at_home": series_record(
            [g for g in meetings if g["home_team"] == home], home
        ),
        "home_qb_record": qb_series_record(meetings, game.get("home_qb_name"), away),
        "away_qb_record": qb_series_record(meetings, game.get("away_qb_name"), home),
    }


def _fmt_record(record):
    wins, losses, ties = record
    return f"{wins}-{losses}" + (f"-{ties}" if ties else "")


def _fmt_line(g):
    """Closing line in words. Positive spread_line means the home team is favored."""
    parts = []
    spread = g["spread_line"]
    if spread:
        favored, dog = (g["home"], g["away"]) if spread > 0 else (g["away"], g["home"])
        parts.append(f"{favored} favored by {abs(spread):g} over {dog}")
    elif spread == 0:
        parts.append("pick'em")
    if g["total_line"]:
        parts.append(f"total {g['total_line']:g}")
    return ", ".join(parts)


def format_game(g, season):
    """One game as a heading plus fact bullets, for the analysis step to narrate."""
    kickoff = " ".join(x for x in (g["weekday"], g["gametime"]) if x)
    md = f"\n### {g['away']} @ {g['home']}"
    if kickoff:
        md += f" — {kickoff}"
    if g["final"]:
        md += f" — **FINAL** {g['away']} {g['away_score']}, {g['home']} {g['home_score']}"
    md += "\n"

    if g["my_players"]:
        names = ", ".join(
            f"**{p['name']}** ({p['position']}, {p['team']}"
            + (", starter)" if p.get("is_starter") else ", bench)")
            for p in g["my_players"]
        )
        md += f"\nYour players: {names}\n"

    facts = []
    venue = g["stadium"]
    if venue:
        detail = " (dome)" if g["roof"] in ("dome", "closed") else ""
        if g["neutral"]:
            detail += f" — neutral site, {g['home']} is home in name only"
        facts.append(f"{venue}{detail}")
    line = _fmt_line(g)
    if line:
        facts.append(line)
    if g["div_game"]:
        facts.append("division game")

    played = len(g["meetings"])
    if played >= MIN_SERIES_GAMES:
        since = season - HISTORY_SEASONS
        series = f"series since {since}: {g['home']} {_fmt_record(g['home_record'])}"
        home_meetings = sum(1 for m in g["meetings"] if m["home_team"] == g["home"])
        if home_meetings and not g["neutral"]:
            series += f", {_fmt_record(g['home_at_home'])} at home"
        facts.append(series)
        last = g["meetings"][0]
        facts.append(
            f"last meeting {last['season']} wk{last['week']}: "
            f"{last['away_team']} {last['away_score']} at {last['home_team']} {last['home_score']}"
        )
    elif played:
        plural = "meeting" if played == 1 else "meetings"
        facts.append(f"only {played} prior {plural} since {season - HISTORY_SEASONS}")
    else:
        facts.append(f"no meetings since {season - HISTORY_SEASONS}")

    for qb, opponent, record in (
        (g["home_qb"], g["away"], g["home_qb_record"]),
        (g["away_qb"], g["home"], g["away_qb_record"]),
    ):
        if record:
            wins, losses, ties, ppg = record
            detail = f"{qb} as starter vs {opponent}: {_fmt_record((wins, losses, ties))}"
            if ppg:
                detail += f", {ppg} pts/gm for his team"
            facts.append(detail)

    for fact in facts:
        md += f"- {fact}\n"
    return md


def generate_markdown(games, week, season, my_team_codes, real_week=None):
    md = f"# Games to Watch — Week {week} ({season})\n"

    stale = week_mismatch_note(week, real_week)
    if stale:
        md += f"\n> **⚠️ Wrong week:** {stale}\n"

    md += (
        f"\nRanked by how much of your lineup is on the field. Series history "
        f"covers {season - HISTORY_SEASONS}-{season} from nflverse results; "
        f"games with no hook below simply have no series data behind them.\n"
    )

    if not games:
        md += (
            f"\nNone of your players' teams ({', '.join(sorted(my_team_codes)) or 'none rostered'}) "
            f"have a Week {week} game on the schedule — a bye week for all of them, or the "
            f"schedule pull came back empty.\n"
        )
        return md

    upcoming = [g for g in games if not g["final"]]
    played = [g for g in games if g["final"]]

    if upcoming:
        md += "\n## Still to play\n"
        for g in upcoming:
            md += format_game(g, season)

    if played:
        heading = "Already final" if upcoming else "All final — this week is over"
        md += f"\n## {heading}\n"
        if not upcoming:
            md += (
                f"\nEvery game with one of your players in it has been decided, so"
                f" nothing below is actionable for week {week}. Read it as the setup"
                f" for week {week + 1}.\n"
            )
        for g in played:
            md += format_game(g, season)

    return md


def build_games_report(config):
    season = config["season"]
    week = config["current_week"]

    print(f"Finding Week {week} games to watch...\n")

    roster_data = build_roster_data(config)
    if not roster_data:
        print("Failed to pull roster. Check config.json.")
        return None

    by_team = roster_by_team(roster_data["players"])

    print()
    schedule = pull_schedule(season)
    history = pull_schedule_history(season, HISTORY_SEASONS)

    week_games = [
        g for g in schedule
        if g.get("week") == week
        and (g.get("home_team") in by_team or g.get("away_team") in by_team)
    ]

    real_week = current_nfl_week(schedule)
    stale = week_mismatch_note(week, real_week)
    if stale:
        print(f"\n  WARNING: {stale}")

    games = [build_game(g, history, by_team) for g in week_games]
    # Most of your lineup first; a game with two starters outranks one with five
    # bench players you are not actually counting on this week.
    games.sort(
        key=lambda g: (len(g["my_starters"]), len(g["my_players"])),
        reverse=True,
    )

    md = generate_markdown(games, week, season, set(by_team), real_week)

    filename = f"week_{week:02d}_games.md"
    out_path = os.path.join(OUTPUT_DIR, filename)
    with open(out_path, "w") as f:
        f.write(md)

    print(md)
    print(f"Saved to output/{filename}")
    return out_path


if __name__ == "__main__":
    config = load_config()

    if "YOUR_" in config["sleeper_username"]:
        print("Update config.json with your Sleeper username and league ID first.")
    else:
        build_games_report(config)
