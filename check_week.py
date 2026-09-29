"""
check_week.py
Compares config.json's hand-maintained `current_week` against the week the NFL
is actually in, derived from the published schedule's game dates.

Exists because `current_week` is the one input nothing validates, and a stale
value produces a complete, plausible-looking report for the wrong week — wrong
matchups, wrong opponent, wrong games. Every report now carries the mismatch as
a banner, but this runs first so the week can be corrected before anything is
generated rather than caveated after.

Usage:
    python check_week.py          # report only; exit 1 if config is stale
    python check_week.py --fix    # rewrite config.json's current_week to match
"""

import json
import os
import sys

from pull_roster import CONFIG_PATH, load_config
from pull_stats import current_nfl_week, pull_schedule


def resolve_week(config):
    """(config_week, real_week) — real_week is None if the schedule is empty."""
    return config["current_week"], current_nfl_week(pull_schedule(config["season"]))


def write_week(week):
    """Rewrite only current_week in config.json, preserving everything else."""
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    config["current_week"] = week
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    fix = "--fix" in sys.argv
    config = load_config()

    if "YOUR_" in config["sleeper_username"]:
        print("Update config.json with your Sleeper username and league ID first.")
        sys.exit(1)

    config_week, real_week = resolve_week(config)

    if real_week is None:
        print(f"Schedule unavailable for {config['season']}; cannot verify the week.")
        print(f"config.json current_week = {config_week} (unverified)")
        sys.exit(0)

    print(f"\nconfig.json current_week = {config_week}")
    print(f"Live NFL week             = {real_week}")

    if config_week == real_week:
        print("\nIn sync.")
        sys.exit(0)

    if fix:
        write_week(real_week)
        print(f"\nUpdated config.json: current_week {config_week} -> {real_week}")
        sys.exit(0)

    print(f"\nSTALE: config.json is set to week {config_week}, the NFL is in week {real_week}.")
    print("Re-run with --fix to update config.json, or edit it by hand.")
    sys.exit(1)
