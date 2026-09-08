"""
pull_stats.py
Pulls season stats, injury reports, and the schedule from nflverse
via nflreadpy. No API key needed.

Early in a season, nflverse has not published the current year's stats or
injury reports yet, so those two fall back to the most recent season that
does exist. The schedule is published in advance and is not backfilled.
"""

import json
import os
import re

import nflreadpy as nfl

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# How many seasons back to walk when the requested one is not published yet.
MAX_FALLBACK_SEASONS = 3

# Suffixes stripped when matching Sleeper names against nflverse names.
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _normalize(name):
    """
    Fold a player name for matching: lowercase, drop punctuation and
    generational suffixes. "A.J. Brown" and "AJ Brown" both -> "aj brown".
    """
    if not name:
        return ""
    cleaned = re.sub(r"[^a-z\s]", "", name.lower())
    parts = [p for p in cleaned.split() if p not in _SUFFIXES]
    return " ".join(parts)


def _load_with_fallback(loader, season, label):
    """
    Call an nflreadpy loader, walking back a season at a time until one
    resolves. Missing data surfaces as a 404 ConnectionError, and out-of-range
    seasons as a ValueError; both mean "not published yet".
    """
    for offset in range(MAX_FALLBACK_SEASONS + 1):
        attempt = season - offset
        try:
            df = loader(seasons=attempt)
        except (ConnectionError, ValueError) as e:
            if offset == MAX_FALLBACK_SEASONS:
                print(f"  {label}: unavailable back to {attempt} ({type(e).__name__})")
                return None, None
            continue
        if offset:
            print(f"  {label}: {season} not published yet, using {attempt} instead")
        else:
            print(f"  {label}: loaded {season}")
        return df, attempt
    return None, None


# Which season the last stats pull actually resolved to. analyze.py reads this
# to label the report when it differs from the season being played.
LAST_STATS_SEASON = None


def pull_player_stats(season):
    """
    Season-to-date regular season totals, one row per player.
    Returned as-is for summarize_player; analyze.py treats it as opaque.
    """
    global LAST_STATS_SEASON

    print("Pulling player stats...")
    df, used = _load_with_fallback(
        lambda seasons: nfl.load_player_stats(seasons=seasons, summary_level="reg"),
        season,
        "stats",
    )
    LAST_STATS_SEASON = used
    return df


def pull_injuries(season):
    """
    Weekly injury reports as a list of dicts (empty if unavailable).

    Deliberately does NOT fall back to a prior season. analyze.py matches
    injuries on any row with a report_status, so a prior season's reports
    would surface last year's injuries as if they were current — worse than
    showing none. Sleeper's own injury_status covers the current week.
    """
    print("Pulling injury reports...")
    df, used = _load_with_fallback(nfl.load_injuries, season, "injuries")
    if df is None:
        return []
    if used != season:
        print(f"  injuries: discarding {used} data, stale for {season}")
        return []
    return df.to_dicts()


def pull_schedule(season):
    """Game schedule as a list of dicts (empty if unavailable)."""
    print("Pulling schedule...")
    df, _ = _load_with_fallback(nfl.load_schedules, season, "schedule")
    if df is None:
        return []
    return df.to_dicts()


# Name index is rebuilt only when a different stats frame comes through.
_index_cache = {"key": None, "index": None}


def _build_index(all_stats):
    """Map normalized player name -> stat row, for O(1) repeated lookups."""
    key = id(all_stats)
    if _index_cache["key"] == key:
        return _index_cache["index"]

    index = {}
    for row in all_stats.iter_rows(named=True):
        for field in ("player_display_name", "player_name"):
            norm = _normalize(row.get(field))
            # First writer wins: player_display_name is the fuller form.
            if norm and norm not in index:
                index[norm] = row

    _index_cache["key"] = key
    _index_cache["index"] = index
    return index


def _per_game(total, games):
    if not total or not games:
        return None
    return round(total / games, 1)


def summarize_player(all_stats, name):
    """
    Condense one player's season totals into the keys format_player_line reads.
    Returns None when the player has no stats (rookie, or a name that did not
    match), which analyze.py renders as a player line without a stat row.
    """
    if all_stats is None:
        return None

    row = _build_index(all_stats).get(_normalize(name))
    if row is None:
        return None

    games = row.get("games") or 0

    summary = {
        "games": games,
        "passing_yards": row.get("passing_yards"),
        "passing_tds": row.get("passing_tds"),
        # nflverse names this passing_interceptions; analyze.py expects
        # `interceptions` for the QB line.
        "interceptions": row.get("passing_interceptions"),
        "carries": row.get("carries"),
        "rushing_yards": row.get("rushing_yards"),
        "rushing_tds": row.get("rushing_tds"),
        "targets": row.get("targets"),
        "receptions": row.get("receptions"),
        "receiving_yards": row.get("receiving_yards"),
        "receiving_tds": row.get("receiving_tds"),
        "avg_target_share": row.get("target_share"),
        "fantasy_points_ppr_per_game": _per_game(row.get("fantasy_points_ppr"), games),
        # Kickers are scored the same in PPR and standard; the K line reads
        # the non-PPR key.
        "fantasy_points_per_game": _per_game(row.get("fantasy_points"), games),
    }

    # Drop empties so format_player_line's truthiness checks stay meaningful.
    return {k: v for k, v in summary.items() if v}


if __name__ == "__main__":
    from pull_roster import load_config

    config = load_config()
    season = config["season"]

    stats = pull_player_stats(season)
    injuries = pull_injuries(season)
    schedule = pull_schedule(season)

    out = {
        "season": season,
        "stat_rows": stats.height if stats is not None else 0,
        "injury_rows": len(injuries),
        "schedule_rows": len(schedule),
    }
    out_path = os.path.join(CACHE_DIR, "stats.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSummary saved to {out_path}")
    print(json.dumps(out, indent=2))
