# BlockFront Stats for Home Assistant

A small custom Home Assistant integration for public BlockFront player statistics, recent match details, the public online-player count, and Blocklytics service health.

Player data now uses the versioned [Blocklytics public API](https://api.blocklytics.naknu.li/docs), which stores observations from the official BlockFront API. Blocklytics is an independent community project. No API key is required.

## Install

### HACS custom repository

1. In Home Assistant, open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/denkz0ne/blockfront_ha_integration` with category **Integration**.
3. Install **BlockFront Stats** and restart Home Assistant when prompted.
4. Open **Settings → Devices & services → Add integration**, then select **BlockFront Stats**.
5. Enter the BlockFront username to track.

### Manual

Copy `custom_components/blockfront` into `<Home Assistant config>/custom_components/blockfront`, then restart Home Assistant and add the integration from **Settings → Devices & services**.

## Sensors

The integration creates one BlockFront player device with these entities:

| Sensor | Data |
| --- | --- |
| Kills, deaths, kill/death ratio, headshots, first bloods, no-scopes | Public lifetime profile values |
| Assists, back stabs, bot kills, fire kills, infected kills, vehicle kills | Public lifetime combat statistics |
| Captures, objective score, heal assists | Public objective and support statistics |
| Experience, rank, skill rank, prestige | Public military and competitive progression, with local rank badge pictures |
| Karma, bootcamp | Optional compatibility lookup; absent from the new public profile contract |
| Class XP, trophies | Existing entities retained, but unknown because the current source does not publish these values |
| Highest kill/death streak, infected rounds/matches won, headshot kill ratio | Additional public player values when the API supplies them |
| Clan, bootcamp | Clan text sensor and a bootcamp binary sensor |
| Latest match | Result as state; map, mode, time, kills, deaths, assists, score, teams, duration, placement, and match ID as attributes |
| Latest match score, duration, end | Numeric score, duration in seconds and end timestamp |
| Tracked matches, recorded wins/losses, recorded win rate, average score | Recorded sample statistics, not lifetime win totals |
| Most played map | Map name; `maps` and `modes` attributes contain performance tables |
| Players online | Public `/v1/online`, falling back through Vuis, official count API, then the official website |
| Bootcamp, Domination, Offensive, Defusal, Team Deathmatch, Gun Game, Free For All, Infected, Trouble Town players | Current player count by game mode from the direct cloud API |
| Cloud API polling status | Direct API polling state (`available`, `rate_limited`, or `unavailable`) |
| Statistics service status | `online`, `degraded`, or `unavailable`, based on active datasets and player-data availability |
| Statistics API polling status, requests remaining | Public API backoff and last observed quota, with reset timestamp and header details |

Existing unique IDs, units and bundled rank pictures are preserved. The skill-rank sensor exposes title, index, color and an inferred `rating_band`, not an exact competitive rating. Class XP attributes are retained for compatibility, but the current source does not publish class XP. Missing values remain unknown instead of becoming zero.

Profile, matches, analytics and online sensors distinguish successful fetch time (`last_successful_update`) from source capture time (`source_timestamp`) and freshness (`source_stale`, also reflected in `stale`). Failed refreshes retain the last good values. Optional karma/bootcamp lookup failures cannot take the public profile offline.

The latest-match attributes add environment, estimated start (`started_at_estimated`) and pagination details. The start is end minus duration, not a verified video recording timestamp. Only the newest page of 20 matches is fetched.

Mode counts use Vuis independently of the public total. When Vuis fails, previous values remain with `cloud_stale: true`; check `cloud_last_successful_update` before using them.

The service status evaluates active datasets returned by `/v1/status`, excluding retired legacy feeds. A reachable API can still be `degraded` when data is stale or player data is disabled.

The rank badge PNGs are bundled from the public [Vuis BlockFront stats page](https://vuis.dev/blockfront_stats/player.html) and served locally by Home Assistant, so entity pictures do not need to load image assets from Vuis at display time.

## Refresh intervals

Initial defaults are deliberately conservative:

| Data group | Default | Minimum |
| --- | ---: | ---: |
| Player profile | 15 minutes | 5 minutes |
| Recent matches | 15 minutes | 5 minutes |
| Online count | 5 minutes | 1 minute |
| Service status | 15 minutes | 5 minutes |
| Recorded-match analytics | 30 minutes | 15 minutes |

Change each interval independently from the integration's **Configure** options. Existing settings remain valid; analytics defaults to 30 minutes and makes three requests per refresh. The official website is fetched only when all online-count API sources fail.

The existing BlockFront online-player parser in your Home Assistant setup is not changed by this integration. Its refresh schedule remains under your control.

## Data freshness and limitations

Profile, matches, online total, status and recorded analytics use `https://api.blocklytics.naknu.li/v1/`. Vuis `cloud_data` remains the per-mode source. Karma/bootcamp use a narrow optional legacy profile lookup until the public contract exposes them. See [migration notes](docs/api-migration-2026-10.md) for endpoint mappings and compatibility limits.

A recent fetch does not guarantee newer game data: public reads do not trigger upstream refreshes. Analytics cover recorded matches only; tracked, paginated and lifetime match counts may differ. Ratio values and performance-table decimals are rounded to two places. Ambiguous percentile fields are not exposed as percentages.

Public quota diagnostics expose last observed headers and timestamps without extra HTTP requests. The limit is token-bucket capacity, not requests per minute; remaining is a snapshot, not a predicted live balance. Reset is converted from delta seconds to a UTC timestamp. HTTP 429 pauses subsequent public requests by this client until Retry-After expires, otherwise reset or a conservative 60 seconds. Other entries/apps behind the same public IP share the quota. Vuis polling diagnostics remain separate; no fixed quota is invented for missing headers.

The official website fallback parses `N Players Online Now!`. Markup changes produce an error and retained stale data, never a fabricated zero.

Recent match history and public profile availability are controlled by BlockFront and its data provider. The integration makes no game-changing requests and needs no credentials.

## Troubleshooting

- **Could not contact the statistics service:** Retry setup later. The username is resolved during setup, so the API must be reachable at that time.
- **Service status is degraded:** Check `datasets`, `stale_datasets`, `player_data_available` and `last_error`. This does not imply that HA needs a restart.
- **Online count uses a fallback:** `public_api_error` and `api_error` distinguish public API and Vuis failures.
- **A value is unknown:** The API has not supplied that value or the first fetch has not succeeded. Check `last_error` and `last_successful_update` before changing the interval.

## Development checks

On Linux or macOS, install both development requirement files and run `pytest -q` and `ruff check custom_components tests`. `requirements_ha_test.txt` installs the Home Assistant integration test environment. GitHub Actions also runs hassfest and HACS validation.

After an update, check setup, preserved entity IDs, source freshness, all five intervals, optional-field failures, fallback counts and quota backoff in a test environment. No live HA installation or restart is performed by repository changes.
