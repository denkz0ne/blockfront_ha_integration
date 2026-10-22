# BlockFront Stats for Home Assistant

A custom Home Assistant integration for your BlockFront profile, match history, personal performance and selected game-wide statistics.

## Install

### HACS custom repository

1. Open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/denkz0ne/blockfront_ha_integration` as an **Integration**.
3. Install **BlockFront Stats** and restart Home Assistant when prompted.
4. Open **Settings → Devices & services → Add integration** and select **BlockFront Stats**.
5. Enter your BlockFront username and the statistics API base URL provided for your access. Enter an API key only if its use has been authorized.

After updating an existing installation, open **Configure** and enter the statistics API base URL. The saved API key is migrated automatically; an empty key field keeps it.

### Manual

Copy `custom_components/blockfront` into `<Home Assistant config>/custom_components/blockfront`, restart Home Assistant, then add the integration from **Settings → Devices & services**.

## Data access

Most player and game statistics come from a separately configured statistics API. Enter its base URL and, if authorized, its API key in the integration setup or **Configure** options. Home Assistant stores both locally in the config entry; the key is sent only to the configured API. Leaving the password field empty in **Configure** keeps the saved key.

The aggregate online total tries alternative sources only when the primary response fails or is explicitly marked stale. If a backup has no capture timestamp, its observation age remains unknown. Online counts by game mode are not currently provided. The integration does not change game data.

## What you get

- **Profile and progression:** experience, military rank, skill rank, prestige, play time and career totals.
- **Personal performance:** combat, objective and support statistics, with ratios rounded to two decimal places.
- **Matches:** latest match details and a recent recorded match sample.
- **History and analysis:** personal trends, map and mode performance, rank history, and season progress when available.
- **Game overview:** online counts, maps, population trends and selected leaderboards.
- **Service diagnostics:** data freshness, availability and request-limit information.

The integration also includes local rank and skill-rank pictures. Some optional or archived values may be missing or delayed. Unknown values remain unknown rather than being shown as zero. Recorded match and analytics data may cover only a sample, not a player's full career.

## Dashboard example

A ready-to-paste three-column Home Assistant view is available in [examples/blockfront-dashboard.yaml](examples/blockfront-dashboard.yaml). It groups profile and progression, personal statistics, matches, online population, and trends in a light, compact style.

The example uses entity IDs for the BlockFront username `denkz0ne`; replace that prefix with the entity IDs created for your configured player. It requires the separate HACS frontend cards `button-card`, `apexcharts-card`, and `tabbed-card`. Add the file contents as a view in a YAML-mode dashboard. Colors follow Home Assistant theme variables. The new activity card shows the selected presence state, collection status and source time; the refresh button's generated entity ID may need the same username-prefix adjustment.

## Refresh intervals

Each data group can be adjusted independently under **Settings → Devices & services → BlockFront Stats → Configure**.

| Data group | Default | Minimum |
| --- | ---: | ---: |
| Player profile and recent matches | 15 minutes | 5 minutes |
| Online count | 5 minutes | 1 minute |
| Service status | 15 minutes | 5 minutes |
| Recorded match analysis | 30 minutes | 15 minutes |
| Personal history and rank | 60 minutes | 30 minutes |
| Archived progression and inventory | 6 hours | 1 hour |
| Game-wide statistics | 60 minutes | 30 minutes |

Polling more often does not make stored game data newer. The integration follows the service's rate-limit instructions and reports the last observed request allowance where available. Other clients using the same key or network may share that allowance.

## Activity-aware collection

Under **Configure**, optionally select a binary sensor or text sensor. A binary sensor uses `on` / `off`; a text sensor is active when its state contains the configured case-insensitive match (default `BlockFront`). A matching active-window title is a probable foreground-game signal, not proof of a live multiplayer match. Unavailable values remain `UNKNOWN` and use a sparse heartbeat. A selected binary sensor that stays off pauses only player-specific polling after the cooldown; online count, global statistics and service health continue on their own schedules. Presence mode can be set to `auto`, `force_active` or `force_idle`. The default cooldown is 30 minutes and the default unknown/idle heartbeat is 60 minutes.

Source-cadence learning observes distinct valid source timestamps and stays within each group's configured interval and minimum. It needs several timestamp changes before adapting; missing, stale or unchanged timestamps keep the conservative configured cadence. A small configurable safety margin helps avoid checking before publication.

The **Refresh all data** button processes profile and recent matches first, then status/population, analytics/history, global rankings and archive data. It runs one coordinator at a time, reports deferred groups and failures, and observes per-group minimum intervals and shared API backoff. For full, untruncated history or inventory, call `blockfront.get_dataset` with any BlockFront `entity_id` and a dataset name. The response returns the latest in-memory value and freshness metadata without recording the full payload in entity attributes.

## Freshness and troubleshooting

Every successful update can be newer than the underlying game observation. Check the entity's source timestamp and stale indicators to see when the game data was captured. When a refresh fails, the integration keeps the last good value and reports the error.

- **Statistics unavailable:** Check that the service is reachable and that the configured key is authorized and valid.
- **Service is degraded:** Review its dataset freshness and last error attributes.
- **Online count uses a fallback:** Check the source and error attributes on the online-count sensor.
- **A value is unknown:** The service may not publish it, or the first successful update has not arrived yet. Optional archive endpoints returning HTTP 404 are rechecked no more than once per day.

See [data coverage and limitations](docs/data-coverage.md) and [configuration notes](docs/data-access.md) for a short overview.

## Development checks

For local development, install the requirement files and run `pytest -q` and `ruff check custom_components tests`. GitHub Actions also runs Home Assistant and HACS validation.
