# Blocklytics API migration and expanded data — October 2026

## Scope

The integration uses the production `/v1` API as its main source and keeps existing config-entry data, sensor unique IDs, units, and local military/skill-rank images. The expanded inventory of all documented routes, preview-only findings, source timestamps, cache behavior, and limits is in [the API inventory](blocklytics-api-inventory-2026-10.md).

## Added data groups

- **Personal history:** 365-day lifetime snapshots, competitive-rank observations, and season score/rank history.
- **Matches:** the latest page of up to 100 recorded matches. Pagination metadata shows whether older pages exist.
- **Global game data:** seven-day online history, 90-day recorded-match/player trends, all map statistics, first pages of the player/clan/competitive leaderboards, and the detail for the player's most-played map.
- **Preview archive:** class XP and saved inventory, with original capture timestamps. These values are visibly separated from profile freshness because the preview can serve old stored data.
- **Efficiency:** production responses are conditionally fetched with ETags and a `304` reuses the last body. Quota diagnostics still use the actual response headers.

Unavailable values remain unknown. A successful poll of a stored snapshot is not treated as a new game observation. Public reads do not trigger a BlockFront refresh.

## Refresh defaults and limits

Profile/matches/status stay at 15 minutes, online at 5 minutes, and recorded analytics at 30 minutes. History and global data default to 60 minutes; preview archive data defaults to 6 hours. Each group has a separate options-flow interval and minimum. Detailed budgets and observed source capture times are in the [inventory](blocklytics-api-inventory-2026-10.md).

The newest 100 match records and leaderboard page are fetched; the integration does not crawl every historical page. The API's top-100 season ranking and sampled analytics are not lifetime standings or a complete career log. Clan lookup/history only runs when a clan is present on the profile.

## Deployment boundary

These changes update repository code and documentation. They do not restart Home Assistant, change the live config entry, or publish a release. GitHub currently has no open issues for this repository; the resulting branch is prepared for review.

References: [OpenAPI schema](https://api.blocklytics.naknu.li/openapi.json), [complete API guide](https://api.blocklytics.naknu.li/llms-full.txt), [preview site](https://preview.blocklytics.naknu.li/).
