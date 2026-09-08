"""
analyze.py
Combines your Sleeper roster with nflreadpy stats into a condensed
markdown file ready to paste into Claude for lineup advice.

Usage: python analyze.py
"""

import json
import os
import sys
from datetime import datetime

# Import the other modules
from pull_roster import build_roster_data, load_config
from pull_stats import pull_player_stats, summarize_player, pull_injuries

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# Sleeper and nflverse disagree on a handful of team abbreviations. Without
# this, an unmatched team silently renders as "BYE" — a false bye that reads
# as "do not start this player."
TEAM_ALIASES = {
    "LAR": "LA",
    "JAX": "JAC",
    "WAS": "WSH",
    "OAK": "LV",
    "SD": "LAC",
    "STL": "LA",
}


def get_team_schedule(schedule, team, week):
    """Find a team's opponent for a given week."""
    candidates = {team, TEAM_ALIASES.get(team, team)}

    for game in schedule:
        if game.get("week") == week:
            home = game.get("home_team", "")
            away = game.get("away_team", "")
            if home in candidates:
                return f"vs {away}"
            elif away in candidates:
                return f"@ {home}"
    return "BYE"


def get_injury_status(injuries, player_name, week):
    """Check injury report for a player."""
    for inj in injuries:
        if (inj.get("full_name") == player_name or inj.get("player_name") == player_name):
            if inj.get("week") == week or inj.get("report_status"):
                status = inj.get("report_status", inj.get("game_status", ""))
                desc = inj.get("report_primary_injury", inj.get("primary_injury", ""))
                if status:
                    return f"{status} ({desc})" if desc else status
    return None


def build_weekly_report(config):
    """Generate the weekly markdown report."""
    season = config["season"]
    week = config["current_week"]

    print(f"Building Week {week} report...\n")

    # Pull roster from Sleeper
    roster_data = build_roster_data(config)
    if not roster_data:
        print("Failed to pull roster. Check config.json.")
        return

    # Pull stats (this may take a moment on first run)
    print()
    all_stats = pull_player_stats(season)
    injuries = pull_injuries(season)

    # Try loading schedule from cache or pull fresh
    schedule = []
    try:
        from pull_stats import pull_schedule
        schedule = pull_schedule(season)
    except Exception:
        pass

    # Build player summaries
    starters = []
    bench = []

    for player in roster_data["players"]:
        name = player["name"]
        pos = player["position"]
        team = player["team"]

        # Get stat summary
        summary = summarize_player(all_stats, name)

        # Get matchup
        matchup = get_team_schedule(schedule, team, week) if schedule else "?"

        # Get injury info
        injury = get_injury_status(injuries, name, week)
        if not injury and player.get("injury_status"):
            injury = player["injury_status"]

        entry = {
            "name": name,
            "position": pos,
            "team": team,
            "matchup": matchup,
            "injury": injury,
            "stats": summary,
        }

        if player["is_starter"]:
            starters.append(entry)
        else:
            bench.append(entry)

    # Generate markdown
    md = generate_markdown(roster_data, starters, bench, week, season)

    # Write output
    filename = f"week_{week:02d}.md"
    out_path = os.path.join(OUTPUT_DIR, filename)
    with open(out_path, "w") as f:
        f.write(md)

    print(f"\nReport saved to: output/{filename}")
    print(f"Paste this file's contents into Claude for lineup recommendations.")
    return out_path


def format_player_line(entry):
    """Format a single player into a compact markdown line."""
    p = entry
    stats = p.get("stats") or {}

    line = f"**{p['name']}** ({p['position']}, {p['team']}) | {p['matchup']}"

    if p.get("injury"):
        line += f" | ⚠️ {p['injury']}"

    # Add key stats based on position
    stat_parts = []
    pos = p["position"]

    if pos == "QB":
        if stats.get("passing_yards"):
            stat_parts.append(f"Pass: {stats['passing_yards']}yds/{stats.get('passing_tds',0)}TD/{stats.get('interceptions',0)}INT")
        if stats.get("rushing_yards"):
            stat_parts.append(f"Rush: {stats['rushing_yards']}yds")
        if stats.get("fantasy_points_ppr_per_game"):
            stat_parts.append(f"PPG: {stats['fantasy_points_ppr_per_game']}")

    elif pos == "RB":
        if stats.get("carries"):
            stat_parts.append(f"Rush: {stats['carries']}att/{stats['rushing_yards']}yds/{stats.get('rushing_tds',0)}TD")
        if stats.get("receptions"):
            stat_parts.append(f"Rec: {stats['targets']}tgt/{stats['receptions']}rec/{stats['receiving_yards']}yds")
        if stats.get("fantasy_points_ppr_per_game"):
            stat_parts.append(f"PPG: {stats['fantasy_points_ppr_per_game']}")

    elif pos in ("WR", "TE"):
        if stats.get("targets"):
            stat_parts.append(f"Rec: {stats['targets']}tgt/{stats.get('receptions',0)}rec/{stats.get('receiving_yards',0)}yds/{stats.get('receiving_tds',0)}TD")
        if stats.get("avg_target_share"):
            stat_parts.append(f"TgtSh: {stats['avg_target_share']:.1%}")
        if stats.get("fantasy_points_ppr_per_game"):
            stat_parts.append(f"PPG: {stats['fantasy_points_ppr_per_game']}")

    elif pos == "K":
        if stats.get("fantasy_points_per_game"):
            stat_parts.append(f"PPG: {stats['fantasy_points_per_game']}")

    elif pos == "DEF":
        stat_parts.append("(team defense)")

    if stat_parts:
        line += "\n  " + " | ".join(stat_parts)

    return line


def generate_markdown(roster_data, starters, bench, week, season):
    """Build the final markdown output."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    md = f"""# Fantasy Football Week {week} ({season})
**League:** {roster_data['league_name']} | **Scoring:** {roster_data['scoring_type']}
**Matchup:** vs {roster_data['matchup']['opponent']}
**Generated:** {now}
"""

    # Early in a season nflverse has not published the current year yet, so the
    # stat lines below are last year's. Say so, or they read as current form.
    import pull_stats

    if pull_stats.LAST_STATS_SEASON and pull_stats.LAST_STATS_SEASON != season:
        md += (
            f"\n> **Note:** {season} stats are not published yet. All stat lines"
            f" below are **{pull_stats.LAST_STATS_SEASON} season totals**, shown"
            f" as a baseline — not current-season form.\n"
        )

    md += "\n## Current Starters\n"

    # Group starters by position
    pos_order = ["QB", "RB", "WR", "TE", "K", "DEF"]
    for pos in pos_order:
        pos_players = [p for p in starters if p["position"] == pos]
        for p in pos_players:
            md += f"\n{format_player_line(p)}\n"

    # FLEX (players not in standard position slots)
    flex_players = [p for p in starters if p["position"] not in pos_order]
    for p in flex_players:
        md += f"\n{format_player_line(p)}\n"

    md += "\n## Bench\n"
    for p in bench:
        md += f"\n{format_player_line(p)}\n"

    md += f"""
## Roster Slots
{', '.join(roster_data['roster_positions'])}

---
*Paste everything above this line into Claude and ask:*
*"Review my Week {week} lineup. Any start/sit changes? Who should I target on waivers?"*
"""
    return md


if __name__ == "__main__":
    config = load_config()

    if "YOUR_" in config["sleeper_username"]:
        print("=" * 50)
        print("SETUP REQUIRED")
        print("=" * 50)
        print()
        print("1. Open config.json")
        print("2. Replace YOUR_USERNAME_HERE with your Sleeper username")
        print("3. Replace YOUR_LEAGUE_ID_HERE with your league ID")
        print("   (Sleeper app → League → Settings → General)")
        print("4. Set current_week to the correct NFL week")
        print("5. Run this script again: python analyze.py")
    else:
        build_weekly_report(config)
