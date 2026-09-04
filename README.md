# Fantasy Football CLI

Weekly lineup analysis powered by Sleeper API + nflreadpy + Claude.

## Setup (one time)

1. Install Python dependency:
   ```
   pip install nflreadpy
   ```

2. Edit `config.json` with your info:
   - `sleeper_username`: your Sleeper username
   - `league_id`: found in Sleeper app → League → Settings → General
   - `season`: current NFL season year
   - `current_week`: update this each week

## Weekly Usage

1. Update `current_week` in `config.json`
2. Run the analysis:
   ```
   python analyze.py
   ```
3. Open the generated file in `output/week_XX.md`
4. Paste its contents into Claude (chat or Claude Code) along with the prompt from `prompts/lineup.md`

## File Structure

```
fantasy-football/
├── config.json          ← your settings (edit this)
├── analyze.py           ← run this each week
├── pull_roster.py       ← pulls roster from Sleeper (called by analyze)
├── pull_stats.py        ← pulls stats via nflreadpy (called by analyze)
├── prompts/
│   └── lineup.md        ← reusable prompt template
├── output/
│   └── week_XX.md       ← generated reports (paste into Claude)
├── cache/
│   ├── players.json     ← Sleeper player DB (auto-cached, refreshes daily)
│   ├── roster.json      ← latest roster pull
│   └── stats.json       ← latest stats pull
└── README.md
```

## Notes

- The Sleeper player database (~30MB) is cached locally and refreshes once per day
- nflreadpy stats are pulled fresh each run (they update Tuesday/Wednesday)
- The output file is deliberately compact to minimize Claude token usage
- You can also run individual scripts: `python pull_roster.py` or `python pull_stats.py`
