# BlockFront Stats for Home Assistant

A small custom Home Assistant integration for public BlockFront player statistics, recent match details, the public online-player count, and Blocklytics service health.

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
| Matches played, time played, rank, prestige | Public profile values when supplied by the API |
| Latest match | Result as the state; map, game mode, date, kills, deaths, assists, score, team, duration, placement, and match ID as attributes |
| Players online | Blocklytics overview count, with the official website as a fallback |
| Statistics service status | `online`, `degraded`, or `unavailable`, with stale-feed and error details |

Missing values remain unknown; they are not converted to zero. Profile, latest match, and online sensors include their last successful update and stale/error attributes. The online sensor's `source` is `blocklytics` or `official_website`.

The service status sensor checks both API reachability and the feed-health information returned by `/status`. A reachable API can still be `degraded` when its upstream feeds are stale or failing.

## Refresh intervals

Initial defaults are deliberately conservative:

| Data group | Default | Minimum |
| --- | ---: | ---: |
| Player profile | 15 minutes | 5 minutes |
| Recent matches | 15 minutes | 5 minutes |
| Online count | 5 minutes | 1 minute |
| Service status | 15 minutes | 5 minutes |

Change each interval independently from the integration's **Configure** options. The official website is fetched only when the online-count API request fails or returns an unusable count. It is not fetched on successful API updates.

The existing BlockFront online-player parser in your Home Assistant setup is not changed by this integration. Its refresh schedule remains under your control.

## Data freshness and limitations

The integration uses the public API at `https://preview.blocklytics.naknu.li/api/v1/`. The API has its own cache and upstream collection schedule. A recent Home Assistant fetch does not guarantee fresh game data; the integration exposes timestamps and stale/error information where available.

The official website fallback reads the server-rendered `N Players Online Now!` text from `https://www.blockfrontmc.com/`. This is not a documented API. If the website markup changes, the fallback reports an error and retains the last known count rather than reporting zero.

Recent match history and public profile availability are controlled by BlockFront and its data provider. The integration makes no game-changing requests and needs no credentials.

## Troubleshooting

- **Could not contact the statistics service:** Retry setup later. The username is resolved during setup, so the API must be reachable at that time.
- **Service status is degraded:** Check the sensor's `stale_feed_count`, `upstream_error`, `last_error`, and update attributes. A degraded state reflects the service's upstream feed status, not a Home Assistant restart requirement.
- **Online count uses the official website:** The API count failed validation or could not be fetched. The `api_error` attribute shows the API-side reason.
- **A value is unknown:** The API has not supplied that value or the first fetch has not succeeded. Check `last_error` and `last_successful_update` before changing the interval.

## Development checks

On Linux or macOS, install both development requirement files and run `pytest -q` and `ruff check custom_components tests`. `requirements_ha_test.txt` installs the Home Assistant integration test environment. GitHub Actions also runs hassfest and HACS validation.

After installing this first version, verify the username setup flow, each sensor's state and attributes, the four independent options intervals, and the official-site fallback by temporarily simulating an API failure in a test environment. No live Home Assistant installation or restart is performed by the project checks.
