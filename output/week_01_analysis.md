# Week 1 Analysis — Radley 2026 (Half PPR)

**Matchup:** vs krs1radley
**Source report:** `week_01.md`
**Analysis date:** 2026-09-16

No stats-fallback note fired in this report's header, so every line below is genuine 2026
Week 1 data. Every rostered player with a Week 1 game now shows a *completed* box score (Henry,
Egbuka, Higgins, London, Nacua, Fannin, Thomas, Burden, Andrews, Lawrence, Gainwell all have full
lines) — a big change from the single-game, mostly-empty sample used last time. That means this
read is a real Week 1 postmortem, not a projection: treat it as the signal for Week 2 roster
moves, not as advice for a week that's already been played.

---

## Summary of moves

| # | Move | Confidence |
|---|---|---|
| 1 | Bench Drake London in favor of Luther Burden in the FLEX spot he's occupying | High |
| 2 | Evaluate Harold Fannin vs. Mark Andrews at TE — Andrews more than doubled Fannin's output | Medium |
| 3 | Hold Burrow at QB despite being outscored by bench arm Trevor Lawrence — one week, and Burrow carries an injury flag worth tracking | Informational |
| 4 | Waivers: shore up RB depth and grab a K/DEF alternative — both positions currently have zero bench coverage | High |

---

## 1. Start/Sit

**Swap: London → Burden.** London's line (4 targets / 2 catches / 29 yards / 5.5 PPG, 21.1%
target share) was the weakest of any starting receiver, including the bench. Burden, sitting on
the bench, outscored him (5 targets / 5 catches / 63 yards / 9.5 PPG) on better volume efficiency.
With four WRs already filling the WR/FLEX pool, this is a straight lateral swap with no cost
elsewhere on the roster — the clearest actionable move this week.

**TE is now a real question.** Fannin's rookie role (13.6% target share, 4.1 PPG) was
outproduced by Andrews (25.0% target share, 8.9 PPG) despite Andrews playing in what's usually a
run-first Baltimore offense. One game isn't a role change, but it's enough to stop assuming Fannin
is the automatic start — check Cleveland's early-season passing script before locking him in
again.

**RB and DEF/K: no changes.** Henry (35.3 PPG) and Jones (10.0 PPG) both clear bench option
Gainwell (2.8 PPG) comfortably. Cam Little and BAL DEF have no bench alternative at all, so there's
nothing to compare them against — see the waiver section.

## 2. Risk Alerts

- **Burrow's Questionable tag plus a quiet game (254 yds/1 TD/1 INT, 14.2 PPG) is worth tracking
  into Week 2**, not because Lawrence's 26.1 PPG bench line means a QB change — one game against
  a Jacksonville defense at home is not the same matchup shape Burrow will see — but because an
  injury designation attached to a below-normal box score is exactly the pattern to double-check
  against the practice report before next week's lineup locks.
- **Brian Thomas is also tagged Questionable and still out-produced a starter** (7.0 PPG vs.
  London's 5.5). If he clears the tag fully, he's a stronger FLEX claim than either London or, on
  a bad week, Higgins.
- **Henry's workload (24 carries in a single game) is efficient production now but a
  volume/health item to watch over a season**, especially paired with no bench RB behind him if
  he needs a maintenance week.
- **Fannin's target share (13.6%) is thin for a starting TE.** Nothing here says bench him
  outright, but it's the kind of number that erodes fast if Cleveland's passing distribution
  shifts.

## 3. FLEX Decision

The FLEX pool is effectively all four rostered WRs (Egbuka, Higgins, London, Nacua) plus whatever
sits on the bench. This week's data makes the call directly: **Burden (9.5 PPG) over London (5.5
PPG)** for the marginal FLEX/WR slot, with Nacua (12.4 PPG, 33.3% target share) and Egbuka (11.3
PPG, 22.2% target share) as the clear top two locks. Higgins (8.9 PPG) sits in the middle — safe
to hold, not a priority swap target this week.

---

## Waiver strategy

No specific names — there's no live waiver-wire feed in this pipeline, and pulling a name from
memory risks recommending someone who isn't actually available or has already been rostered.
Reasoning from roster shape instead:

### The gap: running back depth, still unaddressed

Same structural hole flagged last time and still true: **Henry, Jones, and Gainwell are the
entire RB room.** Gainwell's 2.8 PPG on low volume confirms he's insurance in name only — if
Henry or Jones misses time, there is no in-house replacement, only a cross-position scramble into
FLEX. This is the single highest-priority add.

### A second gap: zero bench coverage at K and DEF

Cam Little and BAL DEF are each one bye week or bad matchup away from an auto-loss at that slot,
with nothing on the roster to rotate in. A low-cost streaming K or DEF pickup (matchup-based,
not name-based) closes this at minimal roster cost.

### Funding it

**Trevor Lawrence** is the obvious cut candidate to open a bench spot — a backup QB in what looks
like a 1-QB league, and his strong Week 1 line (26.1 PPG) is more useful as trade value to a
QB-needy team than as a stashed backup, now that Burrow's Week 1 floor is established.

### Target profile

Prioritize a **pass-catching RB** who can function as this roster's true FLEX-caliber handcuff —
receiving work is the safest floor in Half PPR and the exact thing this RB room lacks depth at.
Secondary priority: a streamable K or DEF with a favorable Week 2 matchup, purely to stop those
two slots from being single points of failure.

---

## Tooling note

- **`config.json`'s `current_week` is still `1`, but Week 1 appears fully played out** — every
  rostered player with a scheduled game now shows a finished box score, unlike the prior run where
  only Nacua's Thursday game had concluded. Bump `current_week` to `2` before the next `analyze.py`
  run, or the next pull will just re-fetch this same, now-final week.
- **Cam Little and BAL DEF still render without stat lines**, consistent with `CLAUDE.md`'s
  documented contract (K reads `fantasy_points_per_game`, not the `_ppr_` variant; DEF never reads
  stats at all) — not a join failure, just the expected shape for those two positions.
