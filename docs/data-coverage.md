# Data coverage and limitations

The integration combines data from an external statistics API with separate online-count sources. Access is limited and may be granted on request. Use it only with authorization from its provider.

## Personal data

- Current profile, progression and lifetime statistics.
- Recent recorded matches and their map, mode, result and performance details.
- Recorded match analysis by map and mode.
- Profile snapshots, competitive rank observations and season progress where available.
- Optional archived class progression and saved inventory.

## Game-wide data

- Current online-player totals and mode counts.
- Recorded population trends and map statistics.
- Selected player, clan and competitive rankings.
- Statistics-service availability, data freshness and request-limit diagnostics.

## How to interpret values

- A fetch time describes when Home Assistant read the service. It does not mean the game data was captured at that time.
- Archived values and rank observations may be delayed. Check source timestamps and stale indicators.
- Match history, match analysis and population trends describe recorded samples and may not cover all game activity.
- Season and ranking values may be absent when the service does not publish them for the player.
- Ratios are numeric values rounded to two decimal places. Missing values remain unknown rather than becoming zero.
- Online totals and per-mode counts can come from separate sources and may differ slightly.
- If a request fails, the integration keeps the last good value and exposes freshness or error details.

## Polling and limits

Refresh intervals are configurable by data group. Defaults and minimums are listed in the [README](../README.md#refresh-intervals). The integration observes rate-limit responses when provided. Other integrations or clients may share the same allowance, so frequent polling should be avoided. A faster refresh cannot make a stored upstream observation newer.

## Access details

The service is described here only as an external statistics API with access available by request. Provider addresses, request paths and other service identifiers are omitted while access arrangements are being clarified.
