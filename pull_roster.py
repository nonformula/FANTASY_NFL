"""
pull_roster.py
Pulls your roster, league settings, and matchup from the Sleeper API.
No API key needed.
"""

import json
import os
import time
import urllib.request

SLEEPER_BASE = "https://api.sleeper.app/v1"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
os.makedirs(CACHE_DIR, exist_ok=True)


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def api_get(endpoint):
    """Simple GET request to Sleeper API."""
    url = f"{SLEEPER_BASE}{endpoint}"
    req = urllib.request.Request(url, headers={"User-Agent": "FantasyFootballCLI/1.0"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def get_player_db():
    """
    Pull the full Sleeper player database. This is ~30MB so we cache it
    and only refresh once per day.
    """
    cache_file = os.path.join(CACHE_DIR, "players.json")

    if os.path.exists(cache_file):
        age_hours = (time.time() - os.path.getmtime(cache_file)) / 3600
        if age_hours < 24:
            with open(cache_file, "r") as f:
                return json.load(f)

    print("Downloading Sleeper player database (this takes a moment the first time)...")
    players = api_get("/players/nfl")
    with open(cache_file, "w") as f:
        json.dump(players, f)
    print(f"Cached {len(players)} players.")
    return players


def get_user_id(username):
    user = api_get(f"/user/{username}")
    return user["user_id"], user.get("display_name", username)


def get_league_info(league_id):
    return api_get(f"/league/{league_id}")


def get_rosters(league_id):
    return api_get(f"/league/{league_id}/rosters")


def get_league_users(league_id):
    return api_get(f"/league/{league_id}/users")


def get_matchups(league_id, week):
    return api_get(f"/league/{league_id}/matchups/{week}")


def _resolve_players(player_ids, player_db, starters):
    """Resolve a list of Sleeper player_ids into name/position/team dicts."""
    players = []
    for pid in player_ids:
        p = player_db.get(pid, {})
        # Team defenses are keyed by team code and carry no full_name.
        name = p.get("full_name")
        if not name:
            if p.get("position") == "DEF":
                name = f"{p.get('team') or pid} Defense"
            else:
                name = f"Unknown ({pid})"
        players.append({
            "player_id": pid,
            "name": name,
            "position": p.get("position", "?"),
            "team": p.get("team", "FA"),
            "is_starter": pid in starters,
            "injury_status": p.get("injury_status", None),
            "age": p.get("age", None),
            "number": p.get("number", None),
        })
    return players


def build_roster_data(config):
    """Main function: returns a dict with your roster, matchup, and league info."""
    username = config["sleeper_username"]
    league_id = config["league_id"]
    week = config["current_week"]

    # Get user
    user_id, display_name = get_user_id(username)
    print(f"Found user: {display_name} ({user_id})")

    # Get league settings
    league = get_league_info(league_id)
    scoring = league.get("scoring_settings", {})
    roster_positions = league.get("roster_positions", [])
    league_name = league.get("name", "Unknown League")

    # Determine scoring type
    ppr_value = scoring.get("rec", 0)
    if ppr_value == 1:
        scoring_type = "PPR"
    elif ppr_value == 0.5:
        scoring_type = "Half PPR"
    else:
        scoring_type = "Standard"

    print(f"League: {league_name} ({scoring_type})")

    # Get all rosters and find yours
    rosters = get_rosters(league_id)
    my_roster = None
    for r in rosters:
        if r.get("owner_id") == user_id:
            my_roster = r
            break

    if not my_roster:
        print(f"ERROR: Could not find roster for user {username} in league {league_id}")
        print("Check that your username and league ID are correct in config.json")
        return None

    roster_id = my_roster["roster_id"]
    player_ids = my_roster.get("players", [])
    starters = my_roster.get("starters", [])

    # Get player details
    player_db = get_player_db()
    players = _resolve_players(player_ids, player_db, starters)

    # Get matchup info
    matchups = get_matchups(league_id, week)
    my_matchup_id = None
    my_points = 0
    opponent_points = 0
    for m in matchups:
        if m.get("roster_id") == roster_id:
            my_matchup_id = m.get("matchup_id")
            my_points = m.get("points", 0)
            break

    # Find opponent
    opponent_roster_id = None
    if my_matchup_id:
        for m in matchups:
            if m.get("matchup_id") == my_matchup_id and m.get("roster_id") != roster_id:
                opponent_points = m.get("points", 0)
                opponent_roster_id = m.get("roster_id")
                break

    # Find opponent name
    opponent_name = "Unknown"
    if opponent_roster_id:
        users = get_league_users(league_id)
        user_map = {u["user_id"]: u.get("display_name", "?") for u in users}
        for r in rosters:
            if r["roster_id"] == opponent_roster_id:
                opponent_name = user_map.get(r.get("owner_id", ""), "Unknown")
                break

    return {
        "league_name": league_name,
        "scoring_type": scoring_type,
        "roster_positions": roster_positions,
        "week": week,
        "players": players,
        "starters": starters,
        "matchup": {
            "opponent": opponent_name,
            "your_points": my_points,
            "opponent_points": opponent_points,
        },
    }


# Sleeper's league settings.waiver_type. 2 is FAAB (a blind-bid budget); the
# others are order-based. Which one it is changes what "waiver position" means:
# under an order-based system it gates who gets a player at all, under FAAB it
# is only the tiebreaker between equal bids.
WAIVER_TYPE_FAAB = 2
WAIVER_TYPE_LABELS = {0: "rolling priority", 1: "reverse standings", 2: "FAAB (blind bidding)"}


def build_waiver_context(league, rosters, user_map, user_id):
    """
    Who can actually win a waiver claim, and at what cost.

    Every roster carries settings.waiver_position and settings.waiver_budget_used,
    which is the only place this pipeline can learn that a recommended add may
    be unwinnable — or free. Rival budgets matter as much as your own: an
    uncontested market means a minimum bid takes the player.
    """
    settings = league.get("settings", {})
    waiver_type = settings.get("waiver_type")
    budget = settings.get("waiver_budget")

    teams = []
    mine = None
    for r in rosters:
        rs = r.get("settings", {})
        spent = rs.get("waiver_budget_used", 0) or 0
        entry = {
            "roster_id": r["roster_id"],
            "manager": user_map.get(r.get("owner_id", ""), "Unknown"),
            "position": rs.get("waiver_position"),
            "spent": spent,
            "remaining": (budget - spent) if budget is not None else None,
            "record": f"{rs.get('wins', 0)}-{rs.get('losses', 0)}",
            "is_me": r.get("owner_id") == user_id,
        }
        if entry["is_me"]:
            mine = entry
        teams.append(entry)

    teams.sort(key=lambda t: (t["position"] is None, t["position"]))

    return {
        "type": waiver_type,
        "type_label": WAIVER_TYPE_LABELS.get(waiver_type, f"unknown ({waiver_type})"),
        "is_faab": waiver_type == WAIVER_TYPE_FAAB,
        "budget": budget,
        "bid_min": settings.get("waiver_bid_min"),
        "is_daily": bool(settings.get("daily_waivers")),
        "day_of_week": settings.get("waiver_day_of_week"),
        "clear_days": settings.get("waiver_clear_days"),
        "playoff_week_start": settings.get("playoff_week_start"),
        "trade_deadline": settings.get("trade_deadline"),
        "num_teams": settings.get("num_teams") or len(rosters),
        "me": mine,
        "teams": teams,
    }


def get_league_rosters(config):
    """
    Pull every roster in the league, resolved to player names/positions —
    not just your own. build_roster_data() throws this data away once it
    finds your roster; this is the same set of API calls, kept instead, for
    trade-opportunity and opponent-weakness scans. The weekly report never
    calls this — that report stays scoped to your own team by design.
    """
    username = config["sleeper_username"]
    league_id = config["league_id"]
    week = config["current_week"]

    user_id, _ = get_user_id(username)
    league = get_league_info(league_id)
    rosters = get_rosters(league_id)
    users = get_league_users(league_id)
    user_map = {u["user_id"]: u.get("display_name", "?") for u in users}
    player_db = get_player_db()

    matchups = get_matchups(league_id, week)
    matchup_by_roster = {
        m["roster_id"]: m.get("matchup_id")
        for m in matchups if m.get("roster_id") is not None
    }

    teams = []
    my_roster_id = None
    for r in rosters:
        roster_id = r["roster_id"]
        if r.get("owner_id") == user_id:
            my_roster_id = roster_id
        starters = r.get("starters", [])
        teams.append({
            "roster_id": roster_id,
            "manager": user_map.get(r.get("owner_id", ""), "Unknown"),
            "players": _resolve_players(r.get("players", []), player_db, starters),
            "matchup_id": matchup_by_roster.get(roster_id),
        })

    opponent_roster_id = None
    my_matchup_id = matchup_by_roster.get(my_roster_id) if my_roster_id is not None else None
    if my_matchup_id is not None:
        for t in teams:
            if t["roster_id"] != my_roster_id and t["matchup_id"] == my_matchup_id:
                opponent_roster_id = t["roster_id"]
                break

    return {
        "week": week,
        "teams": teams,
        "my_roster_id": my_roster_id,
        "opponent_roster_id": opponent_roster_id,
        "waivers": build_waiver_context(league, rosters, user_map, user_id),
    }


if __name__ == "__main__":
    config = load_config()

    if "YOUR_" in config["sleeper_username"]:
        print("Update config.json with your Sleeper username and league ID first.")
    else:
        data = build_roster_data(config)
        if data:
            out_path = os.path.join(CACHE_DIR, "roster.json")
            with open(out_path, "w") as f:
                json.dump(data, f, indent=2)
            print(f"\nRoster data saved to {out_path}")
            print(f"Players on roster: {len(data['players'])}")
