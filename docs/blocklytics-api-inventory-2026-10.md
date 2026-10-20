# Blocklytics API inventory — 20 October 2026

## What was inspected

The production contract is the live [OpenAPI document](https://api.blocklytics.naknu.li/openapi.json), cross-checked against the full API guide and the preview website's requests and rendered player/analytics pages. The public API has 20 documented routes. It is unauthenticated, read-only, and returns `{data, meta}` envelopes. A `GET` reads stored observations; it does not request a fresh capture from BlockFront.

The API documents a default per-IP token bucket of 30 burst requests and 60 requests per minute sustained. `RateLimit-*`, `Retry-After`, `ETag` and `Cache-Control` headers are the runtime authority. The integration records the quota headers and now revalidates cached public responses with `If-None-Match`; a `304` reuses the previous JSON body without losing its source timestamp.

## Documented routes and Home Assistant coverage

| Route | Use in this integration |
| --- | --- |
| `GET /v1/status` | Service state and freshness of upstream datasets. |
| `GET /v1/online` | Current player count; existing fallback chain remains available. |
| `GET /v1/online/history?hours=168` | Seven days of sampled online population for a graph. |
| `GET /v1/trends?days=90` | Daily recorded-match and distinct-player trend. This is the collected sample, not every match in the game. |
| `GET /v1/maps` | Official map, mode and team performance for all maps. |
| `GET /v1/maps/{map}` | Detail for the player's most-played map when that key is available. |
| `GET /v1/leaderboards/{kind}?limit=100` (`players` or `clans`) | First page of the current official season leaderboard; the player's row is exposed if present. |
| `GET /v1/leaderboards/competitive?limit=100` | First page of the stored competitive-rank ladder; the player's row is exposed if present. |
| `GET /v1/players/search?q=...` | Exact username resolution during setup. |
| `GET /v1/players/{uuid}` | Current stored profile and lifetime values. |
| `GET /v1/players/{uuid}/history?days=365` | Cumulative profile snapshots; gaps remain gaps and decreases can mean a reset/correction. |
| `GET /v1/players/{uuid}/competitive-history` | Official skill-rank observations and rank-change time. The API does not publish an exact rating. |
| `GET /v1/players/{uuid}/score-history?days=365` | Season rank and score snapshots; data exists only while the player is in the official top 100. |
| `GET /v1/players/{uuid}/matches?limit=100` | Largest documented recent-match page, with pagination metadata. Older pages are not fetched automatically. |
| `GET /v1/players/{uuid}/analytics` | Recorded sample size and calculation time. |
| `GET /v1/players/{uuid}/analytics/maps` | Per-map recorded match totals and performance. |
| `GET /v1/players/{uuid}/analytics/modes` | Per-mode recorded match totals and performance. |
| `GET /v1/clans?q=...`, `GET /v1/clans/{clan}` | Resolve and load the configured player's clan when their profile includes one. These calls are skipped when no clan is published. |
| `GET /v1/clans/{uuid}/score-history?days=365` | Clan season score when the configured player has a resolvable clan. |

The API guide says the `/v1` contract is additive: clients should ignore unknown fields. Missing `null` values are unknown, never zero. Durations are seconds, ratios are numeric decimals, and timestamps are UTC. Leaderboards are top-100 collections; the matches endpoint is a recent sample. Per-player API access can be disabled by the service.

## Preview website and freshness

The preview frontend calls same-origin `/api/v1` routes. The observed player page uses profile, match, history, rank, class and inventory routes; its analytics page adds daily totals, map/mode performance, score history, percentiles and comparative insights. Many are website-oriented routes outside the production `/v1` OpenAPI contract. The integration uses preview requests only for class XP and saved inventory, which are explicitly unavailable in the documented profile schema.

The preview endpoints observed for those missing values are:

| Preview route | Returned data | Observed capture on the preview page |
| --- | --- | --- |
| `/api/v1/players/{uuid}/classes` | Class IDs and raw XP values; the page maps IDs to class names. | 16 October 2026, 18:12 UTC. |
| `/api/v1/players/{uuid}/inventory` | Saved item IDs and mint values. Item names/textures are resolved by the website's bundled asset catalog, not this response. | 10 October 2026, 06:16 UTC. |

These are archived observations, not live reads. The profile's four recorded captures ran from 17 October 2026, 14:12 UTC to 19 October 2026, 21:09 UTC. The page reported that official competitive ranks are re-read about once a day, so a new HA poll cannot make a rank newer than its upstream capture. On the inspected preview page, the newest listed match was 20 October at 18:29 (site display time). A recent browser/API fetch time must not be presented as a fresh game-data capture.

The old website routes `/history/player/{uuid}`, `/history/matches/{uuid}`, `/players/{uuid}/classes`, `/players/{uuid}/inventory`, and website analytics routes are not treated as stable substitutes for the documented API. Class XP and inventory are the narrow compatibility exception, and their original `captured_at` is kept visible in HA.

## Refresh schedule and request budget

| Group | Default | Minimum | Requests per refresh |
| --- | ---: | ---: | ---: |
| Profile and optional compatibility fields | 15 min | 5 min | 1 public + optional preview profile |
| Recent matches | 15 min | 5 min | 1 public |
| Online count and cloud modes | 5 min | 1 min | 1 public; cloud data is a separate host |
| Service status | 15 min | 5 min | 1 public |
| Recorded match analytics | 30 min | 15 min | 3 public |
| Player history, competitive rank and season score | 1 h | 30 min | 3 public; clan routes are conditional |
| Class XP and saved inventory | 6 h | 1 h | 2 preview |
| Global population, trends, maps and leaderboards | 1 h | 30 min | 6 public + a conditional map-detail request |

At defaults this is about 40 public requests per hour, plus the separate preview/cloud requests and initial setup lookup. Conditional clan requests add a few per hour only for a player with a resolvable clan. The defaults are comfortably below the documented sustained quota, but other apps and Home Assistant entries behind the same public IP share it. The source's collection schedules and its caches control freshness; polling faster does not force a new game capture.

## Interpretation and limits

- Profile counters are lifetime values; history is a series of snapshots, not daily totals. The integration retains the API's timestamps and freshness markers.
- Analytics, match history and global match trends describe recorded samples. They do not guarantee complete career or server-wide match history.
- Season score and rank may be unknown when the player is outside the top 100.
- Competitive `ratingBand` is inferred from the published rank. It is not an official rating.
- Class XP and inventory come from the preview API and can be stale for days. The inventory endpoint only returns item IDs and mint values; the API itself does not return display names or item pictures.
- The integration keeps only the first 100 recent matches and leaderboard rows; response totals and pagination are exposed so truncation is visible.
- The official online count and Vuis per-mode count are separate sources. Their values need not agree at the exact same instant.

## GitHub issue check

The repository's open issue list was checked on 20 October 2026; it contained no open issues to resolve. This API inventory and the integration changes are being delivered together for review.

References: [OpenAPI](https://api.blocklytics.naknu.li/openapi.json), [complete API guide](https://api.blocklytics.naknu.li/llms-full.txt), [preview site](https://preview.blocklytics.naknu.li/), [Blocklytics source](https://git.naknu.li/emilybzh/blocklytics).
