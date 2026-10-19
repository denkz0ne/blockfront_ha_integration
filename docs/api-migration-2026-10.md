# Blocklytics public API migration — 19 October 2026

## Scope

Move to the public `/v1` contract without changing config entry version, player UUID, entity unique IDs, units or local badge paths. The manifest is prepared as 0.3.0; this does not mean a release is published or installed.

Primary base: `https://api.blocklytics.naknu.li/v1/`. Blocklytics is a community project using observations from the official BlockFront API. Public reads need no key and never force an upstream refresh.

| Purpose | Endpoint | Behavior |
| --- | --- | --- |
| Setup | `players/search?q=NAME` | Select only a case-insensitive exact username. |
| Profile | `players/{uuid}` | Normalize nested camelCase values into existing local keys; durations stay seconds. |
| Recent matches | `players/{uuid}/matches?limit=20` | Keep end, duration, environment, estimated start and pagination metadata. |
| Total online | `online` | Keep capture timestamp and freshness. |
| Health | `status` | Evaluate active datasets and player-data availability, excluding retired legacy feeds. |
| Recorded summary | `players/{uuid}/analytics` | Tracked sample size. |
| Map performance | `players/{uuid}/analytics/maps` | Most-played map and map table. |
| Mode performance | `players/{uuid}/analytics/modes` | Sample wins/losses, win percentage, score average and mode table. |

New responses use `{data, meta}`. `meta.updatedAt` is source capture time, distinct from the HA fetch time; `meta.stale` is preserved. Failed refreshes keep previous values marked stale. Unknown fields never become zero.

## Compatibility and limitations

- Vuis `cloud_data` remains the live per-mode source because public v1 has no mode breakdown. Retained mode counts have `cloud_stale: true` when Vuis fails, independently of the public total.
- A public online-total failure falls back through Vuis total, official `https://api.blockfrontmc.com/api/v2/?type=player_count`, then the existing official website parser.
- Karma and bootcamp use a narrow optional legacy profile request. If it fails, these values are unknown with a supplement error; public profile statistics still update. This temporary compatibility API is not a stable public contract.
- Class XP and trophies remain unknown: the source currently does not publish them. Existing entities are retained for dashboards.
- Competitive rating band is an inferred range, not an exact rating.
- Recorded analytics are a sample, not lifetime totals. Tracked totals, pagination totals and lifetime matches may differ. Analytic counters use measurement statistics because the sample may shrink or be recomputed.
- The newest page of 20 matches is fetched, without automatic full-history pagination. Estimated match start is end minus duration, not a verified video recording timestamp.
- Most-played map exposes `maps` and `modes` table attributes, with decimals rounded to two places. Ambiguous percentile fields are intentionally omitted.
- API history, global leaderboards/maps and trends are not polled in this migration. Existing HA recorder history continues; remote history is not imported into recorder.

## Polling

Existing intervals remain valid: profile/matches/status default to 15 minutes, online to 5 minutes. Analytics adds a 30-minute default with a 15-minute minimum. Profile uses one public call plus an optional legacy call; analytics uses three public calls per refresh.

Rate-limit headers describe a shared-IP token bucket. Capacity is not requests per minute. Remaining requests are the last observed count, not an estimate of the current balance. Reset is a delta in seconds, converted to a UTC reset timestamp. HTTP 429 pauses subsequent public calls by this client until Retry-After expires (numeric seconds or HTTP date); fallback is reset or 60 seconds. Other HA entries and apps behind the same public IP share the quota.

Quota entities update after data coordinator refreshes without extra HTTP requests. Vuis cloud polling diagnostics remain separate.

## Verification and deployment boundary

Public search, status, analytics and matches were inspected live before implementation. Static verification uses source compilation, Ruff and whitespace review. Existing API/config-flow fixtures are adapted to the new contract; no new tests are added and the test suite is not executed in this task.

Live HA setup, reload/unload, dashboard rendering, throttling and outage recovery require runtime verification. No installed HA files, restart or release publication are part of this code change.

References: [OpenAPI schema](https://api.blocklytics.naknu.li/openapi.json), [API documentation](https://api.blocklytics.naknu.li/docs). Direct official upstream player access needs an author-issued API key; this integration does not require or store one.
