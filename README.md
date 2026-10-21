# BlockFront Stats for Home Assistant

A small custom Home Assistant integration for BlockFront player statistics, match performance, game-wide trends, maps and leaderboards, online-player counts, and Blocklytics service health.

Player data uses the versioned [Blocklytics API](https://api.blocklytics.naknu.li/docs), which stores observations from the official BlockFront API. Blocklytics is an independent community project. Its current API requires a contributor-issued key. The provider's terms prohibit using that key to track players, so add a key to this integration only if Blocklytics explicitly authorizes this use.

## Install

### HACS custom repository

1. In Home Assistant, open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/denkz0ne/blockfront_ha_integration` with category **Integration**.
3. Install **BlockFront Stats** and restart Home Assistant when prompted.
4. Open **Settings → Devices & services → Add integration**, then select **BlockFront Stats**.
5. Enter the BlockFront username. Add a Blocklytics API key only if the provider has explicitly authorized its use in Home Assistant.

### Blocklytics API key

The key is optional in the setup form and in **Settings → Devices & services → BlockFront Stats → Configure**. It is stored with the config entry and sent as a Bearer token only to `api.blocklytics.naknu.li/v1/`. It is never sent to Vuis, the preview API, or the official BlockFront API. In the options form, leaving the password field empty keeps the saved key.

Blocklytics issues keys to contributors rather than through self-service registration. Its current terms prohibit using a contributor key to track players. Do not enter a key unless the provider has explicitly authorized this integration use. Without an authorized key, Blocklytics profile and statistics requests cannot succeed, so the player statistics are unavailable. The online-player count still has its official website fallback, and Vuis cloud mode counts are independent.

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
| Class XP | Preview archive class values with named breakdown and original capture time |
| Trophies | Unknown because neither the public profile schema nor the inspected preview page publishes this value |
| Highest kill/death streak, infected rounds/matches won, headshot kill ratio | Additional public player values when the API supplies them |
| Clan, bootcamp | Clan text sensor and a bootcamp binary sensor |
| Latest match | Result as state; map, mode, time, kills, deaths, assists, score, teams, duration, placement, and match ID as attributes |
| Latest match score, duration, end | Numeric score, duration in seconds and end timestamp |
| Tracked matches, recorded wins/losses, recorded win rate, average score | Recorded sample statistics, not lifetime win totals |
| Most played map | Map name; `maps` and `modes` attributes contain performance tables |
| Recorded profile history | Snapshot count and the API's cumulative lifetime-stat timeline |
| Competitive rank history | Latest recorded rank, badge index/color, rating band and observed rank history |
| Current season score | Most recently recorded official score; unknown outside the published top 100 |
| Saved inventory items | Preview archive item IDs, mint values and original capture time |
| Maps with statistics | All maps with official mode/team totals, wins, win rate, K/D and score |
| Online history readings | Seven days of population samples for graphs |
| Recorded match trend days | Ninety days of recorded-match and distinct-player counts |
| Player/clan/competitive leaderboard entries | First 100 rows, with the configured player's row when present |
| Most played map details | Public map detail for the player's most-played map when available |
| Players online | Public `/v1/online`, falling back through Vuis, official count API, then the official website |
| Bootcamp, Domination, Offensive, Defusal, Team Deathmatch, Gun Game, Free For All, Infected, Trouble Town players | Current player count by game mode from the direct cloud API |
| Cloud API polling status | Direct API polling state (`available`, `rate_limited`, or `unavailable`) |
| Statistics service status | `online`, `degraded`, or `unavailable`, based on active datasets and player-data availability |
| Statistics API polling status, requests remaining | Public API backoff and last observed quota, with reset timestamp and header details |

Existing unique IDs, units and bundled rank pictures are preserved. The skill-rank sensor exposes title, index, color and an inferred `rating_band`, not an exact competitive rating. Class XP comes from a preview-only archived endpoint and can be several days old; its source timestamp is visible. Missing values remain unknown instead of becoming zero.

Profile, matches, analytics and online sensors distinguish successful fetch time (`last_successful_update`) from source capture time (`source_timestamp`) and freshness (`source_stale`, also reflected in `stale`). Failed refreshes retain the last good values. Optional karma/bootcamp lookup failures cannot take the public profile offline.

The latest-match attributes add environment, estimated start (`started_at_estimated`) and pagination details. The start is end minus duration, not a verified video recording timestamp. The newest page of up to 100 matches is fetched; older pages are not crawled automatically.

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
| Personal history and ranks | 60 minutes | 30 minutes |
| Class XP and saved inventory | 6 hours | 1 hour |
| Global maps, trends, population history and leaderboards | 60 minutes | 30 minutes |

Change each interval independently from the integration's **Configure** options. Existing settings remain valid. Analytics makes three requests per refresh; history makes three public requests; global data makes six public requests and one conditional map-detail request. The official website is fetched only when all online-count API sources fail.

The existing BlockFront online-player parser in your Home Assistant setup is not changed by this integration. Its refresh schedule remains under your control.

## Data freshness and limitations

Profile, matches, online total/history, status, recorded analytics/history, maps, trends and leaderboards use `https://api.blocklytics.naknu.li/v1/`. Vuis `cloud_data` remains the per-mode source. Karma/bootcamp use a narrow optional legacy profile lookup. Class XP and saved inventory use the preview site's archived endpoints because the public contract does not expose them. See [the full API inventory](docs/blocklytics-api-inventory-2026-10.md) and [migration notes](docs/api-migration-2026-10.md).

A recent fetch does not guarantee newer game data: public reads do not trigger upstream refreshes. Class XP and inventory can be days old. Analytics and match history cover recorded samples only; tracked, paginated and lifetime match counts may differ. Unchanged public responses reuse their prior body after ETag revalidation. Ratio values and performance-table decimals are rounded to two places. Ambiguous percentile fields are not exposed as percentages.

Public quota diagnostics expose last observed headers and timestamps without extra HTTP requests. The limit is token-bucket capacity, not requests per minute; remaining is a snapshot, not a predicted live balance. Reset is converted from delta seconds to a UTC timestamp. HTTP 429 pauses subsequent public requests by this client until Retry-After expires, otherwise reset or a conservative 60 seconds. Other entries/apps behind the same public IP share the quota. Vuis polling diagnostics remain separate; no fixed quota is invented for missing headers.

The official website fallback parses `N Players Online Now!`. Markup changes produce an error and retained stale data, never a fabricated zero.

Recent match history and public profile availability are controlled by BlockFront and its data provider. The integration makes no game-changing requests. Follow the provider's access terms; do not use a contributor key for player tracking unless the provider explicitly authorizes that use. Key setup and storage behavior are described above and in the [API migration notes](docs/api-migration-2026-10.md).

## Troubleshooting

- **Could not contact the statistics service:** Check that Blocklytics is reachable and that an authorized API key is configured. The username is resolved during setup, so the API must accept that request at that time.
- **Service status is degraded:** Check `datasets`, `stale_datasets`, `player_data_available` and `last_error`. This does not imply that HA needs a restart.
- **Online count uses a fallback:** `public_api_error` and `api_error` distinguish public API and Vuis failures.
- **A value is unknown:** The API has not supplied that value or the first fetch has not succeeded. Check `last_error` and `last_successful_update` before changing the interval.

## Development checks

On Linux or macOS, install both development requirement files and run `pytest -q` and `ruff check custom_components tests`. `requirements_ha_test.txt` installs the Home Assistant integration test environment. GitHub Actions also runs hassfest and HACS validation.

After an update, check setup, preserved entity IDs, source freshness, all eight intervals, optional-field failures, fallback counts and quota backoff in a test environment. No live HA installation or restart is performed by repository changes.
