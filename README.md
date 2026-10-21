# BlockFront Stats for Home Assistant

A custom Home Assistant integration for your BlockFront profile, match history, personal performance and selected game-wide statistics.

## Install

### HACS custom repository

1. Open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/denkz0ne/blockfront_ha_integration` as an **Integration**.
3. Install **BlockFront Stats** and restart Home Assistant when prompted.
4. Open **Settings → Devices & services → Add integration** and select **BlockFront Stats**.
5. Enter your BlockFront username. Enter an API key only if its provider has authorized this use.

### Manual

Copy `custom_components/blockfront` into `<Home Assistant config>/custom_components/blockfront`, restart Home Assistant, then add the integration from **Settings → Devices & services**.

## Data access

Most player and game statistics come from an external community statistics API. Access is currently limited and may be granted by its provider on request. Configure a key only when the provider has explicitly authorized its use with this integration. The key is optional, stored in the Home Assistant config entry, and sent only to that statistics service. Leaving the password field empty in **Configure** keeps the saved key.

Online totals can use alternative sources when the primary request is unavailable. Per-mode online counts use a separate cloud data source. The integration does not change game data.

## What you get

- **Profile and progression:** experience, military rank, skill rank, prestige, play time and career totals.
- **Personal performance:** combat, objective and support statistics, with ratios rounded to two decimal places.
- **Matches:** latest match details and a recent recorded match sample.
- **History and analysis:** personal trends, map and mode performance, rank history, and season progress when available.
- **Game overview:** online counts, maps, population trends and selected leaderboards.
- **Service diagnostics:** data freshness, availability and request-limit information.

The integration also includes local rank and skill-rank pictures. Some optional or archived values may be missing or delayed. Unknown values remain unknown rather than being shown as zero. Recorded match and analytics data may cover only a sample, not a player's full career.

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

## Freshness and troubleshooting

Every successful update can be newer than the underlying game observation. Check the entity's source timestamp and stale indicators to see when the game data was captured. When a refresh fails, the integration keeps the last good value and reports the error.

- **Statistics unavailable:** Check that the service is reachable and that the configured key is authorized and valid.
- **Service is degraded:** Review its dataset freshness and last error attributes.
- **Online count uses a fallback:** Check the source and error attributes on the online-count sensor.
- **A value is unknown:** The service may not publish it, or the first successful update has not arrived yet.

See [data coverage and limitations](docs/data-coverage.md) and [configuration notes](docs/data-access.md) for a short overview.

## Development checks

For local development, install the requirement files and run `pytest -q` and `ruff check custom_components tests`. GitHub Actions also runs Home Assistant and HACS validation.
