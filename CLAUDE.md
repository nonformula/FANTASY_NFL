# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A small, dependency-light Python CLI that assembles a weekly fantasy football briefing. It pulls a Sleeper roster + league settings, joins them with NFL stats/injuries/schedule from `nflreadpy`, and writes a deliberately compact markdown file to `output/week_XX.md`. That file is meant to be pasted into Claude together with `prompts/lineup.md` — the repo does **not** call any LLM API itself.

There is no build system, no test suite, no linter config, and no package manifest. It is plain scripts run directly.

## Commands

```bash
pip install nflreadpy        # the only third-party dependency
python analyze.py            # main entry point: full weekly report
python pull_roster.py        # Sleeper roster only → cache/roster.json
python pull_stats.py         # stats only → cache/stats.json
```

Each week, bump `current_week` in `config.json` before running `analyze.py`.

`config.json` ships with `YOUR_USERNAME_HERE` / `YOUR_LEAGUE_ID_HERE` placeholders. Both entry points guard on the literal substring `"YOUR_"` in `sleeper_username` and print setup instructions instead of running — so an unconfigured checkout exits cleanly rather than hitting the API.

## Current state — known gaps

Verify these before assuming the pipeline runs:

- **`pull_stats.py` does not exist.** `analyze.py:16` imports `pull_player_stats`, `summarize_player`, and `pull_injuries` from it, and `analyze.py:69` lazily imports `pull_schedule`. So `python analyze.py` currently fails with `ModuleNotFoundError` at import time. `pull_roster.py` runs standalone and is unaffected. The README documents `pull_stats.py` as if it were present.
- `nflreadpy` is not installed in the ambient Python 3.12 environment.
- `cache/` does not exist yet; both scripts `os.makedirs(..., exist_ok=True)` it on import, so this resolves itself on first run.

### Contract `pull_stats.py` must satisfy

Reconstructed from its call sites in `analyze.py`, all keyed on player **full name** (there is no ID join — see below):

| Function | Signature | Returned shape as consumed |
|---|---|---|
| `pull_player_stats` | `(season)` | opaque; only passed back into `summarize_player` |
| `summarize_player` | `(all_stats, name)` → dict or `None` | season-to-date totals; keys read in `format_player_line` |
| `pull_injuries` | `(season)` | iterable of dicts |
| `pull_schedule` | `(season)` | iterable of dicts with `week`, `home_team`, `away_team` |

`summarize_player` keys consumed by `format_player_line` (`analyze.py:122-170`), by position:

- QB — `passing_yards`, `passing_tds`, `interceptions`, `rushing_yards`, `fantasy_points_ppr_per_game`
- RB — `carries`, `rushing_yards`, `rushing_tds`, `targets`, `receptions`, `receiving_yards`, `fantasy_points_ppr_per_game`
- WR/TE — `targets`, `receptions`, `receiving_yards`, `receiving_tds`, `avg_target_share` (a 0–1 float, rendered `.1%`), `fantasy_points_ppr_per_game`
- K — `fantasy_points_per_game` (note: **not** the `_ppr_` variant)
- DEF — none read; renders a literal `(team defense)`

Every read is a `.get()` with a falsy fallback, so a partial dict degrades gracefully rather than raising. `pull_stats.py` is also expected to write `cache/stats.json` and be runnable as `__main__`, matching `pull_roster.py`.

`pull_injuries` dicts are probed permissively in `get_injury_status` (`analyze.py:36-45`) — name under `full_name` **or** `player_name`, status under `report_status` **or** `game_status`, injury text under `report_primary_injury` **or** `primary_injury` — because nflverse column naming varies by feed. Keep that tolerance when editing.

## Architecture

Three layers, coupled only through plain dicts:

1. **`pull_roster.py`** — Sleeper REST via `urllib.request` (stdlib; no `requests`, no API key, no auth). `build_roster_data(config)` is the single public entry: it resolves username → `user_id`, fetches league settings, scans all rosters for the one whose `owner_id` matches, then resolves player IDs against the player DB and locates the week's matchup by pairing `matchup_id` across roster entries. Returns `None` (not an exception) on roster-not-found, and callers check for it.
2. **`pull_stats.py`** — nflverse data via `nflreadpy`. *Missing; see above.*
3. **`analyze.py`** — orchestration and rendering only. No network calls of its own; it calls into the two pullers, merges per player, and emits markdown.

### Things that constrain edits

- **Two-tier caching, by design.** The Sleeper player DB (~30MB) is cached at `cache/players.json` and refreshed only when older than 24h (`pull_roster.py:36-49`). Stats are pulled fresh every run because nflverse updates Tue/Wed. Don't add caching to the stats path without a staleness check tighter than the game week.
- **Name-based joining is the central fragility.** Sleeper gives numeric `player_id`s; stats are looked up by `full_name` string. Any mismatch (suffixes, punctuation, nicknames) silently yields a statless player rather than an error. If you touch the join, prefer adding an ID crosswalk over loosening string matching.
- **The `schedule` pull is wrapped in a bare `except Exception: pass`** (`analyze.py:66-72`); on failure every matchup renders `"?"`. A missing team-week in the schedule renders `"BYE"`, which conflates a real bye with absent data.
- **Output compactness is a feature, not an accident** — the file exists to be pasted into a chat context, so token count matters. Adding columns or prose to the report works against its purpose.
- **Position handling is hardcoded** to `["QB", "RB", "WR", "TE", "K", "DEF"]` in `generate_markdown`; anything else falls into a FLEX catch-all. Sleeper's `roster_positions` is echoed verbatim into the report but never used to drive slot logic.

## Prompt template

`prompts/lineup.md` is the reusable analysis prompt (start/sit, risk alerts, waiver targets, FLEX). `generate_markdown` also appends a shorter inline version of the same ask at the bottom of every report. Both exist; keep them consistent if you change one.
