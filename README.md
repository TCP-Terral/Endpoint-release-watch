# Endpoint Release Watch

Tracks significant changes, new releases, and emerging tech across Windows, Intune, Apple platforms, and Microsoft 365. A Claude Code cloud routine runs each weekday morning, adds new entries to the [tracker page](https://claude.ai/artifact/Q5R6nnLxW8wX374qE7cD2M), and posts a digest card to the IT Teams channel.

## Files

- `INSTRUCTIONS.md` has the steps the routine follows each run, including what to keep, how to sort it, and the writing style
- `fetch_sources.py` pulls recent items from 18 official Microsoft and Apple sources into `candidates.json`
- `post_teams_digest.py` builds the Teams card from `digest.json` and posts it to the channel webhook

## Setup

- **Schedule:** weekdays at 12:00 UTC (7 a.m. Central during daylight saving time, 6 a.m. after the November time change)
- **Cloud environment:** "Default" on claude.ai, with custom network access for the source sites and `*.powerplatform.com`
- **Secret:** `TEAMS_WEBHOOK_URL` is set as an environment variable in the cloud environment, never in this repo

## Common Changes

- **Change what gets kept or skipped:** edit step 3 in `INSTRUCTIONS.md`
- **Add a source:** add an entry to `SOURCES` in `fetch_sources.py`, then add its domain to the cloud environment's allowed domains
- **Change the Teams card:** edit `build_card` in `post_teams_digest.py`, then preview it with `python3 post_teams_digest.py --dry-run`
- **New Teams webhook:** update `TEAMS_WEBHOOK_URL` in the cloud environment settings

Changes pushed to the default branch take effect on the next run.
