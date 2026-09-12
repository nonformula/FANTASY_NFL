---
name: nflweekly
description: Regenerate this week's report from Sleeper/nflreadpy and write a start/sit + waiver analysis to output/
allowed-tools: Bash(python3 analyze.py) Read(config.json) Read(output/**) Read(prompts/**) Write(output/**) Edit(output/**)
---

## Step 1 — Regenerate this week's report

!`python3 analyze.py`

## Step 2 — Analyze

Read `config.json` for `current_week`, then read the file just regenerated above,
`output/week_<current_week zero-padded to 2 digits>.md`, and `prompts/lineup.md` for the
analysis brief.

Answer the four questions in `prompts/lineup.md` (start/sit, risk alerts, waiver targets, FLEX
decision) for the roster in that report.

- If the report's header note says its stats are not the current season, open with a one-line
  caveat saying so before the analysis.
- For waivers, reason about roster composition and positional gaps rather than naming specific
  free agents — there is no live waiver-wire feed here, so a named player may not actually be
  available.

Write the result to `output/week_<current_week>_analysis.md`. If `output/week_01_analysis.md`
exists, match its structure (caveat block, summary table of moves, per-move detail with stat
comparisons, waiver strategy, and a tooling note only when something in the pipeline is worth
flagging).
