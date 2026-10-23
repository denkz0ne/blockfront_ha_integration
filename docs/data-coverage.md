# Data coverage and limitations

Personal profile and recent-match pages are read from the public BlockFront player website. Additional personal history, archived data, analytics and game-wide datasets use the locally configured Statistics API when available. Online counts fall back to official public data. Use private API access only with authorization from its provider.

## Personal data

- Current profile, progression and lifetime statistics.
- Recent recorded matches and their map, mode, result and performance details.
- Recorded match analysis by map and mode.
- Profile snapshots, competitive rank observations and season progress where available.
- Optional archived class progression and saved inventory from the configured Statistics API.

## Game-wide data

- Current aggregate online-player total. Per-mode online counts and scoreboard reset time are not currently available.
- Recorded population trends and map statistics.
- Selected player, clan and competitive rankings.
- Statistics-service availability, data freshness and request-limit diagnostics.

## How to interpret values

- A fetch time describes when Home Assistant read the service. It does not mean the game data was captured at that time.
- Archived values and rank observations may be delayed. Check source timestamps and stale indicators.
- Match history, match analysis and population trends describe recorded samples and may not cover all game activity.
- Season and ranking values may be absent when the service does not publish them for the player.
- Ratios are numeric values rounded to two decimal places. Missing values remain unknown rather than becoming zero.
- The aggregate online total can come from separate sources and may differ slightly between snapshots.
- Mode counts are exposed as attributes of the aggregate online sensor when supplied; the integration does not create separate per-mode entities.
- If a request fails, the integration keeps the last good value and exposes freshness or error details.
- Activity attributes expose `playing_state`, `presence_source`, confidence, whether personal collection is paused, and the next personal check. `source_timestamp` is the upstream observation marker; it is separate from the HTTP check time.
- Personal delta sensors are labeled “since last observation.” They compare distinct source snapshots and do not imply an exact daily total. Rank or prestige resets can make an XP delta unknown.
- Each newly observed match with a stable ID fires `blockfront_new_match` once. The event contains `match_id`, `ended_at`, `map`, `mode`, `score`, and `result`; deduplication survives restarts. Existing matches are seeded on first setup without replay.
- Large list attributes retain up to 60 recent items and disclose the full count through a companion `*_total` attribute when truncated. This keeps existing dashboard keys while bounding normal Recorder payloads.

## Polling and limits

Refresh intervals are configurable by data group. Defaults and minimums are listed in the [README](../README.md#refresh-intervals). The integration observes rate-limit responses when provided. Other integrations or clients may share the same allowance, so frequent polling should be avoided. A faster refresh cannot make a stored upstream observation newer.

## Access details

The configured Statistics API is used for player lookup and supplementary data not available on the player pages. The integration stores its address and optional credential in the Home Assistant config entry and sends that credential only to the configured address. The Vuis player page scraper supplies current profile and recent-match data without an API credential. Scraped pages do not include reliable capture timestamps; their fetch time only records when Home Assistant read the page. If a public page changes its layout, affected scraped sensors may become unknown until the parser is updated.
