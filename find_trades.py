"""
find_trades.py
Scans every roster in your league for the things the weekly report can't
see on its own (it only ever resolves your own team):

  - Where you are weak: your thinnest positions, and the worst body you would
    have to start or fall back on at each.
  - Free agents worth adding: every player on no roster in the league, ranked
    against your own weakest body at that position, so a suggestion is only
    made when it is an actual upgrade. Availability here is computed, not
    guessed — the league's rostered player_ids are diffed against Sleeper's
    full player DB, so a named free agent really is unrostered.
  - A specific trade to propose: pick a team with a complementary
    surplus/need imbalance against you, then pick an actual bench player on
    each side (ranked by current PPG) to build a concrete offer around.
  - Where you have an advantage against your current-week opponent: bench
    positions they have no depth behind, and any of their starters
    carrying a live Sleeper injury tag.

Roster-composition + PPG heuristic — there's no trade-value or projections
feed in this pipeline, so "best" means "best current production among the
players actually available," not a real trade calculator or a rest-of-season
projection. Treat suggestions as a starting point, not gospel. Deliberately
does not dump a full breakdown of every team.

Usage: python find_trades.py
"""

import os

from pull_roster import get_league_rosters, get_player_db, load_config
from pull_stats import (
    current_nfl_week,
    pull_player_stats,
    pull_schedule,
    summarize_player,
    week_mismatch_note,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]
SURPLUS_GAP = 2  # min difference in rostered count to call it a real imbalance

# How many of each position the league's slots force you to field (QB, RB, RB,
# WR, WR, TE, FLEX, FLEX, K, DEF). At or below this count you have no bench
# behind the position — an injury there has no in-house answer.
STARTERS_NEEDED = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}

# Free agents suggested per position. The report is meant to be pasted into a
# chat context, so this stays short on purpose.
MAX_SUGGESTIONS_PER_POSITION = 3


def position_counts(players):
    counts = {pos: 0 for pos in POSITIONS}
    for p in players:
        if p["position"] in counts:
            counts[p["position"]] += 1
    return counts


def player_production(name, all_stats):
    """
    (ppg, games) for a player, or (0.0, 0) with no stat sample. games matters:
    a high PPG over one game is not the same claim as one over every game, and
    without it a single-week sample reads as a trend.
    """
    summary = summarize_player(all_stats, name) if all_stats is not None else None
    if not summary:
        return 0.0, 0
    ppg = (
        summary.get("fantasy_points_ppr_per_game")
        or summary.get("fantasy_points_per_game")
        or 0.0
    )
    return ppg, summary.get("games") or 0


def get_ppg(name, all_stats):
    """Current-season PPG for a player, or 0.0 if there's no stat sample yet."""
    return player_production(name, all_stats)[0]


def summarize_my_positions(my_team, all_stats):
    """
    Per position: who you have, the worst of them by PPG, and whether you have
    any bench behind the slots you must fill. The worst body is the bar a free
    agent has to clear to be worth adding at all.
    """
    counts = position_counts(my_team["players"])
    summary = {}

    for pos in POSITIONS:
        mine = []
        for p in my_team["players"]:
            if p["position"] != pos:
                continue
            ppg, games = player_production(p["name"], all_stats)
            mine.append({"name": p["name"], "ppg": ppg, "games": games, "is_starter": p["is_starter"]})
        if not mine:
            summary[pos] = {"count": 0, "players": [], "worst": None, "no_bench": True}
            continue

        mine.sort(key=lambda p: p["ppg"])
        summary[pos] = {
            "count": counts[pos],
            "players": mine,
            "worst": mine[0],
            "no_bench": counts[pos] <= STARTERS_NEEDED.get(pos, 1),
        }

    return summary


def rostered_player_ids(league):
    """Every player_id held by any team in the league — the inverse of the FA pool."""
    return {
        p["player_id"]
        for team in league["teams"]
        for p in team["players"]
    }


def find_free_agents(league, player_db, all_stats, my_positions):
    """
    Unrostered players worth adding, grouped by position.

    Availability is a real diff (player DB minus every rostered id), not a
    guess. Quality is current production only — there are no projections in
    this pipeline, so a player with no stat sample is left out rather than
    recommended on reputation. The one exception is team defenses, which carry
    no nflverse player stats at all; those are returned separately as a bare
    availability list, since "which DEFs are streamable" is still useful.
    """
    rostered = rostered_player_ids(league)

    candidates = {pos: [] for pos in POSITIONS}
    available_defenses = []

    for pid, p in player_db.items():
        if pid in rostered:
            continue
        pos = p.get("position")
        if pos not in POSITIONS:
            continue
        if not p.get("active") or not p.get("team"):
            continue

        # Team defenses are pseudo-players keyed by team code: no full_name and
        # status is always null, so they must skip the status check below.
        if pos == "DEF":
            available_defenses.append(p.get("team"))
            continue

        # The DB is full of inactive and practice-squad entries that cannot be
        # started; only real actives are addable.
        if p.get("status") != "Active":
            continue

        name = p.get("full_name")
        if not name:
            continue

        ppg, games = player_production(name, all_stats)
        if not ppg:
            continue  # no stat sample: nothing here but a name

        candidates[pos].append({
            "name": name,
            "position": pos,
            "team": p.get("team"),
            "ppg": ppg,
            "games": games,
            "injury_status": p.get("injury_status"),
            # 1 means he is his NFL team's starter at the position — the
            # difference between a real add and a backup with one good week.
            "depth_chart_order": p.get("depth_chart_order"),
        })

    # Only suggest a player who beats the worst body you already have there.
    upgrades = {}
    for pos, pool in candidates.items():
        bar = my_positions.get(pos, {}).get("worst")
        bar_ppg = bar["ppg"] if bar else 0.0
        better = [c for c in pool if c["ppg"] > bar_ppg]
        better.sort(key=lambda c: c["ppg"], reverse=True)
        if better:
            upgrades[pos] = {
                "bar": bar,
                "bar_ppg": bar_ppg,
                "options": better[:MAX_SUGGESTIONS_PER_POSITION],
                "total_better": len(better),
            }

    return upgrades, sorted(available_defenses)


def find_trade_candidates(my_team, other_teams, all_stats):
    """
    For each other team, find the position they most out-roster you at and
    the position you most out-roster them at. If both sides have bench
    players sitting in those spots, suggest the pair whose current PPG is
    closest to each other — a best-vs-best pairing (your top bench piece
    for their top bench piece) tends to be lopsided and unlikely to be
    accepted, since PPG at different positions isn't directly comparable
    and a big gap reads as a lowball either direction.
    """
    my_counts = position_counts(my_team["players"])
    candidates = []

    for team in other_teams:
        their_counts = position_counts(team["players"])
        their_surplus = {
            pos: their_counts[pos] - my_counts[pos] for pos in POSITIONS
            if their_counts[pos] - my_counts[pos] >= SURPLUS_GAP
        }
        my_surplus = {
            pos: my_counts[pos] - their_counts[pos] for pos in POSITIONS
            if my_counts[pos] - their_counts[pos] >= SURPLUS_GAP
        }

        if not their_surplus or not my_surplus:
            continue

        pos_get = max(their_surplus, key=their_surplus.get)
        pos_give = max(my_surplus, key=my_surplus.get)

        offer_pool = [p for p in my_team["players"] if p["position"] == pos_give and not p["is_starter"]]
        request_pool = [p for p in team["players"] if p["position"] == pos_get and not p["is_starter"]]

        candidate = {
            "manager": team["manager"],
            "they_have_extra": list(their_surplus.keys()),
            "you_have_extra": list(my_surplus.keys()),
            "offer": None,
            "request": None,
        }

        best_pair = None
        best_diff = None
        for o in offer_pool:
            o_ppg = get_ppg(o["name"], all_stats)
            for r in request_pool:
                r_ppg = get_ppg(r["name"], all_stats)
                diff = abs(o_ppg - r_ppg)
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_pair = (o, o_ppg, r, r_ppg)

        if best_pair:
            offer, o_ppg, request, r_ppg = best_pair
            candidate["offer"] = {
                "name": offer["name"], "position": offer["position"], "team": offer["team"], "ppg": o_ppg,
            }
            candidate["request"] = {
                "name": request["name"], "position": request["position"], "team": request["team"], "ppg": r_ppg,
            }

        candidates.append(candidate)

    return candidates


def find_advantages(opponent_team):
    """
    Points to look for where you have an edge on your current-week
    opponent: bench positions with no depth beyond their own starters, and
    any starter carrying a live Sleeper injury tag.
    """
    counts = position_counts(opponent_team["players"])
    starters = [p for p in opponent_team["players"] if p["is_starter"]]
    starter_counts = position_counts(starters)

    thin_positions = [
        pos for pos in POSITIONS
        if counts[pos] > 0 and counts[pos] <= starter_counts[pos]
    ]

    injured_starters = [
        p for p in opponent_team["players"]
        if p.get("injury_status") and p["is_starter"]
    ]

    return thin_positions, injured_starters


def format_trade_line(c):
    line = (
        f"\n**{c['manager']}** — deep at {', '.join(c['they_have_extra'])}; "
        f"you're deep at {', '.join(c['you_have_extra'])}.\n"
    )
    if c["offer"] and c["request"]:
        o, r = c["offer"], c["request"]
        o_ppg = f"{o['ppg']:.1f} PPG" if o["ppg"] else "no current stat sample"
        r_ppg = f"{r['ppg']:.1f} PPG" if r["ppg"] else "no current stat sample"
        line += (
            f"  Suggested offer: your **{o['name']}** ({o['position']}, {o['team']}, {o_ppg}) "
            f"for their **{r['name']}** ({r['position']}, {r['team']}, {r_ppg}).\n"
        )
    else:
        line += "  No bench player on one side to build a specific offer around.\n"
    return line


def _fmt_sample(ppg, games):
    """PPG with its sample size, so a one-game number can't pose as a trend."""
    if not ppg:
        return "no current stat sample"
    return f"{ppg:.1f} PPG over {games} game{'s' if games != 1 else ''}"


def format_weak_spots(my_positions):
    md = "## Your Weak Spots\n"
    rows = []
    for pos in POSITIONS:
        info = my_positions.get(pos)
        if not info:
            continue
        worst = info["worst"]
        flags = []
        if info["no_bench"]:
            flags.append("**no bench**")
        if worst and not worst["ppg"]:
            flags.append("no stat sample on the weakest body")
        detail = (
            f"worst: {worst['name']} ({_fmt_sample(worst['ppg'], worst['games'])})"
            if worst else "nobody rostered"
        )
        rows.append(
            f"- **{pos}** — {info['count']} rostered, {detail}"
            + (f" — {', '.join(flags)}" if flags else "")
        )
    return md + "\n".join(rows) + "\n"


def format_free_agents(upgrades, available_defenses, my_positions):
    md = "\n## Free Agent Upgrades\n"
    md += (
        "\nEvery player below is on **no roster in this league** — computed by diffing the"
        " league's rostered players against Sleeper's player DB, so availability is real."
        " Each one out-produces the weakest body you currently hold at that position."
        " Ranked by current PPG; there are no projections in this pipeline, so players with"
        " no stat sample are omitted rather than recommended on reputation.\n"
    )

    if not upgrades:
        md += "\nNo unrostered player currently out-produces what you already have at any position.\n"
    else:
        for pos in POSITIONS:
            info = upgrades.get(pos)
            if not info:
                continue
            bar = info["bar"]
            bar_text = (
                f"beating {bar['name']} at {_fmt_sample(bar['ppg'], bar['games'])}"
                if bar else "you have nobody rostered here"
            )
            depth_note = " — **no bench here**" if my_positions.get(pos, {}).get("no_bench") else ""
            md += f"\n**{pos}** ({bar_text}{depth_note})\n"
            for c in info["options"]:
                line = f"  - **{c['name']}** ({c['team']}) — {_fmt_sample(c['ppg'], c['games'])}"
                if c["depth_chart_order"] == 1:
                    line += ", his team's starter"
                elif c["depth_chart_order"]:
                    line += f", depth chart #{c['depth_chart_order']}"
                if c["injury_status"]:
                    line += f", ⚠️ {c['injury_status']}"
                md += line + "\n"
            if info["total_better"] > len(info["options"]):
                md += f"  - ...and {info['total_better'] - len(info['options'])} more clearing that bar\n"

    if available_defenses:
        md += (
            f"\n**Unrostered team defenses** (no nflverse player stats exist for these, so this is"
            f" availability only — stream on matchup): {', '.join(available_defenses)}\n"
        )

    return md


def generate_markdown(opponent_team, candidates, thin_positions, injured_starters, week,
                      real_week=None, my_positions=None, upgrades=None, available_defenses=None):
    md = f"# League Scan — Week {week}\n\n"

    # A stale week here means the advantage section scanned the wrong opponent.
    stale = week_mismatch_note(week, real_week)
    if stale:
        md += f"> **⚠️ Wrong week:** {stale}\n\n"

    if my_positions:
        md += format_weak_spots(my_positions)
        md += format_free_agents(upgrades or {}, available_defenses or [], my_positions)
        md += "\n"

    md += "## Suggested Trades\n"
    if candidates:
        for c in candidates:
            md += format_trade_line(c)
    else:
        md += "\nNo complementary surplus/need imbalance found this week.\n"

    md += f"\n## Where You Have an Advantage"
    if opponent_team:
        md += f" — Week {week} vs {opponent_team['manager']}\n"
        points = []
        if thin_positions:
            points.append(
                f"No bench depth at {', '.join(thin_positions)} — an injury or bad "
                f"matchup there has no fallback for them."
            )
        if injured_starters:
            names = ", ".join(f"{p['name']} ({p['injury_status']})" for p in injured_starters)
            points.append(f"Starters carrying a Sleeper injury tag: {names}.")

        if points:
            for point in points:
                md += f"\n- {point}\n"
        else:
            md += "\nNone found this week — their roster has no visible soft spot.\n"
    else:
        md += "\n\nNo opponent found for this week (bye, or matchups not posted yet).\n"

    return md


if __name__ == "__main__":
    config = load_config()

    if "YOUR_" in config["sleeper_username"]:
        print("Update config.json with your Sleeper username and league ID first.")
    else:
        week = config["current_week"]
        print(f"Scanning league for Week {week} trade opportunities and matchup advantages...\n")

        league = get_league_rosters(config)
        my_team = next((t for t in league["teams"] if t["roster_id"] == league["my_roster_id"]), None)

        if not my_team:
            print("Could not find your roster in this league. Check config.json.")
        else:
            other_teams = [t for t in league["teams"] if t["roster_id"] != my_team["roster_id"]]
            opponent_team = next(
                (t for t in league["teams"] if t["roster_id"] == league["opponent_roster_id"]),
                None,
            )

            all_stats = pull_player_stats(config["season"])
            real_week = current_nfl_week(pull_schedule(config["season"]))
            stale = week_mismatch_note(week, real_week)
            if stale:
                print(f"\n  WARNING: {stale}\n")

            my_positions = summarize_my_positions(my_team, all_stats)

            print("Scanning free agents...")
            player_db = get_player_db()
            upgrades, available_defenses = find_free_agents(
                league, player_db, all_stats, my_positions
            )
            print(f"  free agents: upgrades found at {', '.join(upgrades) or 'no position'}")

            candidates = find_trade_candidates(my_team, other_teams, all_stats)
            if opponent_team:
                thin_positions, injured_starters = find_advantages(opponent_team)
            else:
                thin_positions, injured_starters = [], []

            md = generate_markdown(
                opponent_team, candidates, thin_positions, injured_starters, week, real_week,
                my_positions, upgrades, available_defenses,
            )

            filename = f"week_{week:02d}_trades.md"
            out_path = os.path.join(OUTPUT_DIR, filename)
            with open(out_path, "w") as f:
                f.write(md)

            print(md)
            print(f"Saved to output/{filename}")
