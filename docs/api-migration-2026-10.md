# Blocklytics API migration and expanded data — October 2026

## Scope

The integration uses the production `/v1` API as its main source and keeps existing config-entry data, sensor unique IDs, units, and local military/skill-rank images. The expanded inventory of all documented routes, preview-only findings, source timestamps, cache behavior, and limits is in [the API inventory](blocklytics-api-inventory-2026-10.md).

## API key configuration

Version 0.3.1 adds an optional password field to initial setup and the integration's **Configure** options. A key is sent only as `Authorization: Bearer …` to the production `https://api.blocklytics.naknu.li/v1/` host. It is not sent to the Vuis cloud endpoint, preview archive, official BlockFront API, or official website. An empty options field preserves a key already saved in the config entry.

Blocklytics issues keys to contributors and its current terms prohibit using a contributor key to track players. Only configure one if the provider has explicitly authorized the integration use. A key is not bundled in the integration or needed to install it. Without an authorized key, Blocklytics profile and personal-statistics calls cannot succeed; the online count can still use its existing fallback chain, and Vuis mode counts are independent. Since no key was available during this release, authenticated live API behavior has not been verified against a provider-issued key.

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

Version 0.3.1 changes repository code and documentation only. It does not restart Home Assistant or edit a live config entry. After installing the release, configure a provider-authorized key in the integration options if one is available.

References: [OpenAPI schema](https://api.blocklytics.naknu.li/openapi.json), [complete API guide](https://api.blocklytics.naknu.li/llms-full.txt), [preview site](https://preview.blocklytics.naknu.li/).
