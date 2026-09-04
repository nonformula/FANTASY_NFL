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
os.makedirs(CACHE_DIR, exist_ok=True)


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(config_path, "r") as f:
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

    players = []
    for pid in player_ids:
        p = player_db.get(pid, {})
        players.append({
            "player_id": pid,
            "name": p.get("full_name", f"Unknown ({pid})"),
            "position": p.get("position", "?"),
            "team": p.get("team", "FA"),
            "is_starter": pid in starters,
            "injury_status": p.get("injury_status", None),
            "age": p.get("age", None),
            "number": p.get("number", None),
        })

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
