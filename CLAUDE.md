# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A small, dependency-light Python CLI that assembles a weekly fantasy football briefing. It pulls a Sleeper roster + league settings, joins them with NFL stats/injuries/schedule from `nflreadpy`, and writes a deliberately compact markdown file to `output/week_XX.md`. A second script, `find_trades.py`, separately scans every roster in the league for trade opportunities and opponent weaknesses, writing `output/week_XX_trades.md`. Both files are meant to be pasted into Claude together with `prompts/lineup.md` — the repo does **not** call any LLM API itself (the `/nflweekly` slash command automates that paste-in step locally, but the underlying scripts still assume a human or Claude Code, not an API key, does the analysis).

There is no build system, no test suite, no linter config, and no package manifest. It is plain scripts run directly.

## Commands

```bash
pip install nflreadpy        # the only third-party dependency
python check_week.py         # is config.json on the real NFL week? (--fix rewrites it)
python analyze.py            # main entry point: full weekly report
python find_trades.py        # league-wide trade + opponent-advantage scan → output/week_XX_trades.md
python find_games.py         # this week's games your players are in, w/ series history → output/week_XX_games.md
python pull_roster.py        # Sleeper roster only → cache/roster.json
python pull_stats.py         # stats only → cache/stats.json
```

### `current_week` is the one unvalidated input

`config.json`'s `current_week` is hand-maintained, and a stale value produces a complete,
plausible-looking report for the **wrong week** — wrong matchups, wrong opponent in the trade scan,
wrong games. It was found two weeks stale (set to 1 on Sep 28, 2026, real week 3), which is why
nothing trusts it silently any more:

- `pull_stats.current_nfl_week(schedule)` derives the live week from the schedule's `gameday` dates
  **and results**. It rolls **forward** in two cases, because a week you can no longer act on is not
  the week you want analysis for: the Tue/Wed gap between weeks, and a week whose every game is
  final even though today is still inside its span (the Monday-night case — without it, a Monday run
  returns a week whose lineup has already locked). A week with any unplayed game stays current,
  since those slots are still live. Returns `None` on an empty schedule, and every caller treats
  that as "unverifiable", not week 0.
- `pull_stats.week_progress(schedule, week)` → `(games_final, games_scheduled)`. The main report
  renders it as `**Games final:** N/M` plus a banner when the week is partly or fully played, and
  `find_games.py` splits its output into "Still to play" vs "Already final". This exists because a
  mid-week report otherwise reads as entirely forward-looking when most slots have locked — the
  week 3 analysis was written against a 15/16-decided week before this was added.
- `pull_stats.week_mismatch_note(config_week, real_week)` is the single wording of the discrepancy;
  all three reports render it as a `⚠️ Wrong week` banner and print it to the console. Don't
  re-word it per report.
- `check_week.py` is the pre-flight: report-only by default (exit 1 when stale), `--fix` rewrites
  just `current_week` in place. `/nflweekly` runs `--fix` as Step 0 so the week is corrected before
  anything is generated rather than caveated afterwards.

The main report header also carries a `**Live NFL week:**` line whether or not it matches.

The `/nflweekly` slash command (`.claude/commands/nflweekly.md`) chains `check_week.py --fix` →
`analyze.py` →
`find_trades.py` → `find_games.py` → an analysis pass that reads all three outputs plus
`prompts/lineup.md` and writes `output/week_<NN>_analysis.md` in four fixed sections (ANALYSIS,
TRADES & FREE AGENTS, GAMES TO WATCH, TOOLING NOTE) → emails it → **commits and pushes that one file
itself**. `.gitignore` is `output/*` with `!output/*_analysis.md`, so the three raw reports and
`cache/` stay ignored as regenerated data and only the analysis is ever tracked.

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
| `pull_schedule_history` | `(season, seasons_back)` | list of **completed** game dicts across a season range (`find_games.py` only) |
| `current_nfl_week` | `(schedule, today=None)` | int week, or `None` when the schedule is empty |
| `week_progress` | `(schedule, week)` | `(games_final, games_scheduled)` |
| `week_mismatch_note` | `(config_week, real_week)` | one-line warning string, or `None` when they agree |

`pull_schedule_history` is the one loader that deliberately skips `_load_with_fallback`: an empty
list is a meaningful answer ("no history"), and silently walking seasons back would change the
window the caller asked for. It filters to rows with a `result`, so unplayed games never count as
history. Useful columns beyond the basics: `home_score`/`away_score`, `result` (= home − away),
`home_qb_name`/`away_qb_name` (populated for played and near-future weeks, **null for distant
ones**), `spread_line` (**positive = home favored**; verified at 69% home win rate over 2024-25),
`total_line`, `div_game`, `roof`, `stadium`, `location` (`"Neutral"` for international games, where
the listed home team has no home field).

`nflreadpy` returns **polars**, not pandas. `summarize_player` builds a normalized-name index once per frame (memoized on `id(all_stats)`) rather than filtering per player.

`summarize_player` keys consumed by `format_player_line`, by position:

- QB — `passing_yards`, `passing_tds`, `interceptions`, `rushing_yards`, `fantasy_points_ppr_per_game`
- RB — `carries`, `rushing_yards`, `rushing_tds`, `targets`, `receptions`, `receiving_yards`, `fantasy_points_ppr_per_game`
- WR/TE — `targets`, `receptions`, `receiving_yards`, `receiving_tds`, `avg_target_share` (a 0–1 float, rendered `.1%`), `fantasy_points_ppr_per_game`
- K — `fg_made`, `fg_att`, `pat_made`, `fantasy_points_per_game` (note: **not** the `_ppr_` variant)
- DEF — none read; renders a literal `(team defense)`

**nflverse does not score kicking.** Every kicker row comes back with
`fantasy_points = fantasy_points_ppr = 0.0`, while the raw kicking columns (`fg_made`, `fg_att`, the
`fg_made_<range>` buckets, `pat_made`) are fully populated. So the K contract above was silently
dead for three weeks — kickers rendered with no stat line at all and could not be compared to each
other. `summarize_player` now rebuilds kicker points from the made-kick buckets via
`_kicker_points` / `KICKER_FG_POINTS` (3 / 4 / 5 by distance tier, 1 per PAT) whenever
`fantasy_points` is falsy and `position == "K"`. **Misses are not penalized** — that value is
league-specific and Sleeper's setting is not exposed to this pipeline, so the number is a floor on
real output, not an exact league score. Don't "simplify" this back to reading `fantasy_points`.

Every read is a `.get()` with a falsy fallback, so a partial dict degrades gracefully rather than raising. Note the nflverse column for QB picks is `passing_interceptions`; `summarize_player` remaps it to the `interceptions` key `format_player_line` expects.

`pull_injuries` dicts are probed permissively in `get_injury_status` (`analyze.py:36-45`) — name under `full_name` **or** `player_name`, status under `report_status` **or** `game_status`, injury text under `report_primary_injury` **or** `primary_injury` — because nflverse column naming varies by feed. Keep that tolerance when editing.

## Architecture

Five scripts, coupled only through plain dicts:

1. **`pull_roster.py`** — Sleeper REST via `urllib.request` (stdlib; no `requests`, no API key, no auth). `build_roster_data(config)` is the main entry for the weekly report: it resolves username → `user_id`, fetches league settings, scans all rosters for the one whose `owner_id` matches, then resolves player IDs against the player DB and locates the week's matchup by pairing `matchup_id` across roster entries. Returns `None` (not an exception) on roster-not-found, and callers check for it. `get_league_rosters(config)` is the other entry point, used only by `find_trades.py`: it re-does the same roster/matchup calls but keeps *every* team's resolved players instead of discarding all but your own, plus which roster is your current-week opponent. Both share the private `_resolve_players` helper.
2. **`pull_stats.py`** — nflverse data via `nflreadpy` (stats, injuries, schedule), with the season fallback described above.
3. **`analyze.py`** — orchestration and rendering only for the weekly report. No network calls of its own; it calls into the two pullers, merges per player, and emits `output/week_XX.md`.
4. **`find_games.py`** — answers "which real games should I watch this week," which needs the whole schedule rather than per-player matchup strings. Maps your roster's Sleeper teams into nflverse spelling (imports `TEAM_ALIASES` from `analyze.py` — the one place that mapping lives), finds the current week's games involving them, and annotates each with series history from `pull_schedule_history`: the home team's record in the series and its home split, the last meeting's score, and each listed starting QB's record against that opponent. Ranks games by starters-then-players on the field, writes `output/week_XX_games.md`. **Every hook is computed from nflverse rows on purpose** — the section it feeds invites exactly the kind of claim ("1-4 against them at home") that is trivially hallucinated, so the script emits the facts and the analysis step is told to use only those. Guards worth keeping: meetings are filtered to `(season, week) < (this game)` so a stale `current_week` cannot pull already-played later games in as history; series shorter than `MIN_SERIES_GAMES` report as thin instead of trending; a QB with fewer than `MIN_QB_SERIES_GAMES` starts in the series gets no line; and neutral-site games suppress the home split.
5. **`find_trades.py`** — free agents, trades, opponent weaknesses. **The free agent scan makes "who is available" a computed fact, not a guess:** `rostered_player_ids` collects every `player_id` held by any team in the league and `find_free_agents` diffs that against the full Sleeper player DB, so a named free agent really is unrostered (verified: 10 teams, 156 rostered players, zero overlap with suggestions, 10 rostered + 22 unrostered defenses = 32). Because of that, **naming free agents in the report is correct** — the old "no live waiver feed, so reason about roster shape instead" constraint is obsolete and was removed from the command. Constraints that remain: candidates must be `active` with a real `team` and `status == "Active"` (the DB carries ~2,800 inactive and practice-squad entries that cannot be started); a player with **no stat sample is dropped rather than recommended on reputation**, since there are no projections here; and a suggestion is only made when the player out-produces the worst body already rostered at that position (`summarize_my_positions`). Two Sleeper quirks to preserve: **team defenses are pseudo-players** keyed by team code with `full_name: null` and `status: null`, so they must bypass the status check and are returned as a bare availability list (no nflverse player stats exist for them); and `depth_chart_order == 1` is the signal that separates a genuine add from a backup with one good week. `STARTERS_NEEDED` encodes the league's slots (QB1/RB2/WR2/TE1/K1/DEF1) to flag positions with no bench. Also a league-wide scan, separate from `analyze.py`'s single-team report. Calls `get_league_rosters` + `pull_player_stats`/`summarize_player`, then: (a) for each other team, finds a position where they out-roster you by `SURPLUS_GAP` and vice versa, and pairs a bench player on each side by closest current PPG — a "best offer isn't a lopsided best-for-best" heuristic, not a real trade calculator; (b) for your current-week opponent, flags bench positions with no depth beyond their own starters and any starter carrying a live Sleeper injury tag. Writes `output/week_XX_trades.md`. No trade-value or projections feed backs this — it's roster-composition + PPG only.

### Things that constrain edits

- **Two-tier caching, by design.** The Sleeper player DB (~30MB) is cached at `cache/players.json` and refreshed only when older than 24h (`pull_roster.py:36-49`). Stats are pulled fresh every run because nflverse updates Tue/Wed. Don't add caching to the stats path without a staleness check tighter than the game week.
- **Name-based joining is the central fragility.** Sleeper gives numeric `player_id`s; stats are looked up by `full_name` string. `_normalize` in `pull_stats.py` folds case, punctuation, and generational suffixes ("A.J. Brown" ≡ "AJ Brown"), but any remaining mismatch silently yields a statless player rather than an error. If you touch the join, prefer adding an ID crosswalk (`nfl.load_ff_playerids()`) over loosening string matching further.
- **Team abbreviations differ between the two sources.** nflverse calls the Rams `LA`, Sleeper calls them `LAR`. Unmatched teams render as `"BYE"` — a false bye that reads as "do not start this player," which is why `TEAM_ALIASES` exists in `analyze.py`. Add to it rather than special-casing at the call site; `find_games.py` imports it, so a missing alias there drops a game from "games to watch" entirely rather than mislabeling it.
- **The `schedule` pull is wrapped in a bare `except Exception: pass`**; on failure every matchup renders `"?"`. A missing team-week still renders `"BYE"`, conflating a real bye with absent data.
- **Output compactness is a feature, not an accident** — the file exists to be pasted into a chat context, so token count matters. Adding columns or prose to the report works against its purpose.
- **Position handling is hardcoded** to `["QB", "RB", "WR", "TE", "K", "DEF"]` in `generate_markdown`; anything else falls into a FLEX catch-all. Sleeper's `roster_positions` is echoed verbatim into the report but never used to drive slot logic. `find_trades.py` hardcodes the same list independently (`POSITIONS`) rather than importing it — keep both in sync if a position is added.
- **`find_trades.py` reuses the name-based stats join** from `pull_stats.py` (`get_ppg` → `summarize_player`), so the same silent-mismatch caveat applies: a player `find_trades.py` can't match gets treated as 0.0 PPG, not flagged as missing data, which can make a bench player look like a worse trade piece than they are.

## Prompt template

`prompts/lineup.md` is the reusable analysis prompt (start/sit, risk alerts, waiver targets, FLEX). `generate_markdown` also appends a shorter inline version of the same ask at the bottom of every report. Both exist; keep them consistent if you change one.
