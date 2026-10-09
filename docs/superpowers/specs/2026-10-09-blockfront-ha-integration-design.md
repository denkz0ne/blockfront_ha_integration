# BlockFront Home Assistant integration: initial release design

Date: 2026-10-09

## Goal

Provide a small Home Assistant custom integration for public BlockFront statistics. The first release is intended for the user's own installation and for sensors that can be shown on a dashboard or geek display. The configured identity is a BlockFront username. Live HAOS installation and activation are outside this repository change; the user will install and test the initial release later.

## Scope

The initial release will:

- Add one config entry per BlockFront username. The config flow resolves the name to a UUID and rejects unknown or invalid names with a useful form error.
- Create profile sensors for the player's public summary, including kills, deaths, K/D, headshots, rank/prestige, games, and time played when those fields exist.
- Create a latest-match sensor whose state is the result and whose attributes contain the timestamp, map, mode, kills, deaths, assists, score, team, duration, placement, and match ID when provided.
- Create an online-player-count sensor. It reads the Blocklytics overview endpoint first and fetches the official BlockFront website only if the API request fails or its online count cannot be parsed. The website count is a fallback source and is marked as such in sensor attributes.
- Create a Blocklytics service-status sensor that reports online/degraded/unavailable based on the service status endpoint and recent coordinator outcomes. Attributes expose last successful update, stale feed count, API version/uptime if available, and a concise last error.
- Leave the user's existing approximately 15-second online-player parser untouched. This integration's online count is independent and slower.
- Document HACS/manual installation, sensors, data freshness, configuration, polling, and known upstream limitations.

Not in the first release: bulk-player requests, broad analytics/leaderboards, history graphs, controls/actions, and changes to Home Assistant or the existing parser.

## Configuration and polling

The config flow asks for a username only. The resolved UUID is stored in the entry so later refreshes do not need to resolve the name repeatedly. An options flow independently controls profile, matches, online-count, and service-status refresh intervals. Defaults are 900 seconds for profile and matches, 300 seconds for online count, and 900 seconds for service status. Values are validated to avoid rapid requests; the README will state that low intervals do not make upstream data fresher.

The online endpoint is polled at its own interval. The official page is fetched only after a failed/invalid online API result, never as an additional request on a successful cycle. A website parse failure retains the previous online count and exposes the source/error state rather than reporting zero.

Profile, matches, online count, and service health have separate refresh schedules. Failure handling preserves last known sensor values, marks the affected source unavailable/degraded, and does not retry rapidly. Timeouts, HTTP errors, invalid JSON, missing values, and stale/source timestamps are represented explicitly.

## Data sources verified during design

The current Blocklytics API base is `https://preview.blocklytics.naknu.li/api/v1/`:

- `GET /resolve?name=<username>` returned a UUID for `denkz0ne`.
- `GET /players/{uuid}` returned a public summary with fields such as `kills`, `deaths`, `kd`, `head_shots`, `rank`, `prestige`, `total_games`, and `time_played`.
- `GET /players/{uuid}/matches` returned a `matches` list containing match result, map, game mode, kills, deaths, assists, score, team, duration, placement, and end time.
- `GET /overview` returned `online.playersOnline` and a `generatedAt` timestamp.
- `GET /status` returned `feeds`, `budget`, `etl`, `version`, and `uptimeS`; some feeds in the live response were stale or had recent upstream 503 errors.

The official page `https://www.blockfrontmc.com/` currently serves HTML containing a literal `N Players Online Now!` count. The fallback parser will only accept that expected phrase and a nonnegative integer. This markup is not a formal API and can change; failures are visible and do not silently become zero.

Live endpoint responses are observations, not a stable published API contract. The implementation will tolerate absent optional fields, use request timeouts, validate response shape, and document the API dependency. The API's short HTTP cache lifetime does not prove that its upstream feed is fresh; timestamps and stale indicators must be surfaced when provided.

## Home Assistant structure

Use the standard custom integration layout under `custom_components/blockfront/` with a config flow, options flow, one coordinator per data group (or equivalent independently scheduled coordinators), sensor platform, translations, manifest, and diagnostics-safe error handling. No credentials are required. Entity IDs and unique IDs derive from the resolved UUID and statistic key, not mutable display names. Sensor metadata follows Home Assistant conventions, with units/device classes only where semantically valid. The config entry creates a shared device named for the BlockFront player.

## Failure and freshness behavior

- Name resolution errors remain in the config form and do not create a partial entry.
- A transient request failure preserves the previous good value and records a last error and last success time.
- An unavailable first fetch yields `unknown`/unavailable as appropriate, never a fabricated numeric zero.
- Online count records whether its value came from the API or the official website.
- Service status distinguishes successful API access from degraded upstream feeds; HTTP 200 alone is not treated as proof that every feed is fresh.
- Retries are bounded to normal coordinator scheduling; no tight retry loop is allowed.

## Validation and delivery

Before calling the initial release ready, validate the integration with focused tests for config flow resolution/validation, response parsing, independent update intervals, website fallback, stale/error handling, and sensor attributes. Run Home Assistant's available validation/lint checks and CI. Verify the final repository contents and provide the user installation and manual HAOS test steps. Do not install, reload, or restart the user's HAOS without a separate explicit request.

## Open implementation detail

The page currently exposes the online count as server-rendered HTML. If that changes to client-rendered content, the fallback should fail visibly and retain the previous value; do not silently depend on undocumented private browser endpoints.

