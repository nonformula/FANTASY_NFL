---
name: nflweekly
description: Regenerate this week's report from Sleeper/nflreadpy, then write analysis + trades + games to watch to output/ and email it
allowed-tools: Bash(python3 check_week.py:*) Bash(python3 analyze.py) Bash(python3 find_trades.py) Bash(python3 find_games.py) Bash(git add:*) Bash(git commit:*) Bash(git push:*) Read(config.json) Read(output/**) Read(prompts/**) Write(output/**) Edit(output/**) mcp__claude_ai_Gmail__send_message
---

## Step 0 — Sync to the real NFL week

!`python3 check_week.py --fix`

`current_week` in `config.json` is hand-maintained and is the one input nothing else validates — a
stale value yields a complete, plausible report for the wrong week. This derives the live week from
the published schedule's game dates and rewrites `config.json` to match.

Note in your final response which week the analysis is for, and say so explicitly if Step 0 moved it
(e.g. "Week 3 — config was still on week 1"). Every step below reads the corrected value, so use the
week this step reports, not one carried over from earlier in the conversation. If it says the
schedule is unavailable and it cannot verify the week, flag that in the TOOLING NOTE section and
carry on with whatever `config.json` holds.

## Step 1 — Regenerate this week's report

!`python3 analyze.py`

## Step 2 — Scan the league for free agents, trades, and matchup advantages

!`python3 find_trades.py`

This writes `output/week_<current_week zero-padded to 2 digits>_trades.md` with four things: your
weak spots by position (count rostered, worst body, whether there's any bench), **free agent
upgrades** at each position, a suggested trade where a complementary roster imbalance exists, and
points of advantage against this week's opponent.

The free agent list is computed by diffing every rostered player_id in the league against Sleeper's
player DB, so **availability is real, not guessed** — naming these players is correct. Each one
already out-produces the worst body on your roster at that position.

## Step 3 — Find the games worth watching

!`python3 find_games.py`

This writes `output/week_<current_week zero-padded to 2 digits>_games.md` — this week's real NFL
games that your players are in, ranked by how much of your lineup is on the field, each with fact
bullets (closing line, series record, the listed QB's record in that series, last meeting).

Steps 2 and 3 both write intermediate files for Step 4 to read, not things to publish on their own.

## Step 4 — Write the analysis

Read `config.json` for `current_week`, then read all three generated files — `output/week_<NN>.md`,
`output/week_<NN>_trades.md`, `output/week_<NN>_games.md` — and `prompts/lineup.md` for the
analysis brief.

Write the result to `output/week_<current_week>_analysis.md` using exactly these four sections, in
this order:

### ANALYSIS

Answer the four questions in `prompts/lineup.md` (start/sit, risk alerts, waiver targets, FLEX
decision) for the roster in the report.

**Always point the advice at a week that can still be changed.** The report header carries a
`Games final: N/M` line and `week_XX_games.md` splits "Still to play" from "Already final". Read
them first:

- `0/M` final — the normal case. Straight-ahead advice for this week.
- Partly played — advise on the players in the "Still to play" games, which are the only slots that
  can move. Say plainly that everyone else has locked, and direct the rest of the read at next week.
- All final — this week is closed. Say so up front and write the whole analysis as **next week's**
  setup, with the moves table headed for that week. Do not present a locked week's lineup as a
  decision.
- If the report's header note says its stats are not the current season, or it still carries a
  "Wrong week" banner, open with a one-line caveat saying so before anything else.
- Answer the waiver-targets question by pointing at the named free agents from the scan (they're in
  the TRADES & FREE AGENTS section below) rather than repeating them here — cover *which gap* is
  most urgent and what to drop to make room.
- If `output/week_01_analysis.md` exists, match its structure within this section (summary table of
  moves, then per-move detail with stat comparisons, then the roster-gap read).

### TRADES & FREE AGENTS

From `output/week_<NN>_trades.md`. Frame the whole section as acquisition: what is weak on this
roster, and who fixes it — off waivers first, by trade second. Name specific players; there is real
roster and availability data behind every name here.

**Free agents first**, because they cost nothing but a roster spot. Lead with the positions where
the scan says there's **no bench**, since that's where an injury has no in-house answer. For each
one worth acting on, give the player, his production with its sample size, and whether he's his NFL
team's starter — a depth-chart #2 or #3 with a good two weeks is a different bet than a #1. Say
what to drop to make room. Two caveats to carry, both honest:

- The scan ranks on **current production only** — there are no projections in this pipeline, so a
  high PPG over one or two games is a small sample, not a forecast. Say so when the sample is thin.
- Unrostered means available, but Sleeper may route a recently-dropped player through **waivers**
  rather than a free add, so a claim may need priority or FAAB.

**Then the trade.** Pass along the scan's suggested offer, and say which side of the deal actually
helps this team and why. Compare it honestly against the free agent option: if an FA at that
position is as good or better, the trade isn't worth making, and you should say that.

**Then the opponent advantage** points. If the scan found nothing in a subsection, say so in a line
rather than dropping it.

### GAMES TO WATCH

From `output/week_<NN>_games.md`. For each game, one or two sentences on what to pay attention to,
built from that game's fact bullets and which of your players are in it — a close line plus a
lopsided series, a QB who has struggled in the matchup, a shootout total with two of your starters
on the field. Lead with the games carrying the most of your lineup.

Respect the file's split: games under "Still to play" are the ones to actually watch, so lead with
them. Anything under "Already final" is a recap — keep those to the hooks worth remembering and
don't write them as though they are upcoming.

**Only use the hooks the file actually gives you.** Do not add head-to-head records, streaks, or
history from memory — the file's numbers are computed from nflverse results, and anything beyond
them is a guess that will read as researched. If a game's bullets say the series is thin, the
honest note is the line and who you have in it.

### TOOLING NOTE

Only when something in the pipeline is worth flagging (a player with no stat match, a schedule pull
that came back empty, a false BYE). Omit the section entirely when there is nothing to report.

## Step 5 — Email the findings

Send the finished analysis to **antonio@radleystudios.tv** with
`mcp__claude_ai_Gmail__send_message`.

- Subject: `Week <current_week> Fantasy Brief — <start/sit headline>` (e.g. "Week 4 Fantasy Brief —
  start Egbuka over Higgins"). Use the week Step 0 confirmed.
- Use `htmlBody` for the real content and pass a plain-text version in `body` as the fallback.
  Do not put markdown in either field — `body` must be plain prose, `htmlBody` must be real tags.
- Design it to be read on a phone: one inline `<style>`-free layout using inline `style`
  attributes only (mail clients strip `<style>` blocks), a max width around 600px, system font
  stack, generous line height, and section headings matching the four sections above. Put the
  start/sit moves in a simple bordered table (lineup change, in, out, why); keep everything else as
  short paragraphs and lists. No images, no web fonts, no dark-mode-only colors — set both text
  and background colors explicitly so it survives either mode.
- Carry the stats-season caveat into the email if the report had one, near the top where it cannot
  be missed.
- Confirm to me that the email was sent, with the subject line used.

## Step 6 — Publish the analysis

Stage and commit only the analysis file (`output/week_<current_week>_analysis.md`) and `.gitignore`
if it changed — never the raw `week_<NN>.md`, `week_<NN>_trades.md`, or `week_<NN>_games.md`
reports, nor `cache/`, all of which stay gitignored as regenerated data. Then push to the current
branch's upstream.

```
git add output/week_<current_week>_analysis.md
git commit -m "Week <current_week> lineup analysis"
git push
```

If the push fails (no upstream, diverged branch, network error), report the failure and stop — do
not force-push or reset.
