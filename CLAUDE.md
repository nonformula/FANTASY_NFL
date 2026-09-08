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

On a python.org macOS build, `pull_roster.py` fails with `SSL: CERTIFICATE_VERIFY_FAILED` because `urllib` uses OpenSSL's default store, which those builds ship empty. `nflreadpy` is unaffected (it bundles certifi), so the failure looks like a Sleeper-only problem. Fix once with `/Applications/Python\ 3.12/Install\ Certificates.command`.

`config.json` is gitignored; `config.example.json` is the tracked template. `config.json` ships with `YOUR_USERNAME_HERE` / `YOUR_LEAGUE_ID_HERE` placeholders. Both entry points guard on the literal substring `"YOUR_"` in `sleeper_username` and print setup instructions instead of running — so an unconfigured checkout exits cleanly rather than hitting the API.

## Season-boundary behavior — read this first

nflverse publishes data only after games are played, so **early in a season the current year does not exist yet**. As of the 2026 opener:

- `load_schedules(2026)` → works (272 games; schedules are published in advance)
- `load_player_stats(2026)` → **404**
- `load_injuries(2026)` → **`ValueError: Season must be between 2009 and 2025`** (nflreadpy 0.1.5 hard-caps the range)

`_load_with_fallback` in `pull_stats.py` absorbs both failure modes by walking back up to `MAX_FALLBACK_SEASONS` years. Consequences worth preserving:

- **Stats fall back** to the prior season and the report header says so. `pull_stats.LAST_STATS_SEASON` records what actually resolved; `generate_markdown` reads it to emit the note. Without that label, last year's totals read as current form.
- **Injuries deliberately do NOT fall back.** `get_injury_status` matches any row with a `report_status` regardless of week, so a prior season's reports would surface last year's injuries as current — it flagged Burrow "Out (Toe)" and Nacua "Out (Ankle)" from 2025 finals. `pull_injuries` discards a fallback result and returns `[]`, leaving Sleeper's own live `injury_status` as the source. Do not "fix" this by enabling the fallback.

### Contract between `analyze.py` and `pull_stats.py`

All keyed on player **full name** (there is no ID join — see below):

| Function | Signature | Returned shape as consumed |
|---|---|---|
| `pull_player_stats` | `(season)` | polars DataFrame, opaque; only passed back into `summarize_player` |
| `summarize_player` | `(all_stats, name)` → dict or `None` | season-to-date totals; keys read in `format_player_line` |
| `pull_injuries` | `(season)` | list of dicts |
| `pull_schedule` | `(season)` | list of dicts with `week`, `home_team`, `away_team` |

`nflreadpy` returns **polars**, not pandas. `summarize_player` builds a normalized-name index once per frame (memoized on `id(all_stats)`) rather than filtering per player.

`summarize_player` keys consumed by `format_player_line`, by position:

- QB — `passing_yards`, `passing_tds`, `interceptions`, `rushing_yards`, `fantasy_points_ppr_per_game`
- RB — `carries`, `rushing_yards`, `rushing_tds`, `targets`, `receptions`, `receiving_yards`, `fantasy_points_ppr_per_game`
- WR/TE — `targets`, `receptions`, `receiving_yards`, `receiving_tds`, `avg_target_share` (a 0–1 float, rendered `.1%`), `fantasy_points_ppr_per_game`
- K — `fantasy_points_per_game` (note: **not** the `_ppr_` variant)
- DEF — none read; renders a literal `(team defense)`

Every read is a `.get()` with a falsy fallback, so a partial dict degrades gracefully rather than raising. Note the nflverse column for QB picks is `passing_interceptions`; `summarize_player` remaps it to the `interceptions` key `format_player_line` expects.

`pull_injuries` dicts are probed permissively in `get_injury_status` (`analyze.py:36-45`) — name under `full_name` **or** `player_name`, status under `report_status` **or** `game_status`, injury text under `report_primary_injury` **or** `primary_injury` — because nflverse column naming varies by feed. Keep that tolerance when editing.

## Architecture

Three layers, coupled only through plain dicts:

1. **`pull_roster.py`** — Sleeper REST via `urllib.request` (stdlib; no `requests`, no API key, no auth). `build_roster_data(config)` is the single public entry: it resolves username → `user_id`, fetches league settings, scans all rosters for the one whose `owner_id` matches, then resolves player IDs against the player DB and locates the week's matchup by pairing `matchup_id` across roster entries. Returns `None` (not an exception) on roster-not-found, and callers check for it.
2. **`pull_stats.py`** — nflverse data via `nflreadpy` (stats, injuries, schedule), with the season fallback described above.
3. **`analyze.py`** — orchestration and rendering only. No network calls of its own; it calls into the two pullers, merges per player, and emits markdown.

### Things that constrain edits

- **Two-tier caching, by design.** The Sleeper player DB (~30MB) is cached at `cache/players.json` and refreshed only when older than 24h (`pull_roster.py:36-49`). Stats are pulled fresh every run because nflverse updates Tue/Wed. Don't add caching to the stats path without a staleness check tighter than the game week.
- **Name-based joining is the central fragility.** Sleeper gives numeric `player_id`s; stats are looked up by `full_name` string. `_normalize` in `pull_stats.py` folds case, punctuation, and generational suffixes ("A.J. Brown" ≡ "AJ Brown"), but any remaining mismatch silently yields a statless player rather than an error. If you touch the join, prefer adding an ID crosswalk (`nfl.load_ff_playerids()`) over loosening string matching further.
- **Team abbreviations differ between the two sources.** nflverse calls the Rams `LA`, Sleeper calls them `LAR`. Unmatched teams render as `"BYE"` — a false bye that reads as "do not start this player," which is why `TEAM_ALIASES` exists in `analyze.py`. Add to it rather than special-casing at the call site.
- **The `schedule` pull is wrapped in a bare `except Exception: pass`**; on failure every matchup renders `"?"`. A missing team-week still renders `"BYE"`, conflating a real bye with absent data.
- **Output compactness is a feature, not an accident** — the file exists to be pasted into a chat context, so token count matters. Adding columns or prose to the report works against its purpose.
- **Position handling is hardcoded** to `["QB", "RB", "WR", "TE", "K", "DEF"]` in `generate_markdown`; anything else falls into a FLEX catch-all. Sleeper's `roster_positions` is echoed verbatim into the report but never used to drive slot logic.

## Prompt template

`prompts/lineup.md` is the reusable analysis prompt (start/sit, risk alerts, waiver targets, FLEX). `generate_markdown` also appends a shorter inline version of the same ask at the bottom of every report. Both exist; keep them consistent if you change one.
