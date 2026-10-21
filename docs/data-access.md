# Data access and configuration

The integration reads BlockFront statistics from an external API. Access is limited and provided on request. Availability and permitted use depend on authorization from the service provider.

## API key

The key is optional in initial setup and in the integration's **Configure** options. Use it only when the provider has authorized this integration. Home Assistant stores it with the integration entry and sends it only to the statistics service. The key is not included in the repository. Leave the field empty when editing options to retain a previously saved key.

Without an authorized key, personal profile and statistics may be unavailable. Online-player counts may still be obtained from alternative sources, and per-mode counts are handled separately.

## Data groups

The integration provides personal profile values, recent matches, recorded-match analysis, personal history and rank progression, plus selected game-wide statistics. Archived or optional values may be missing or older than the main profile data. Each entity exposes freshness details when the source provides them.

The integration reads previously collected statistics; polling does not force the game or provider to capture new data. Missing values remain unknown, and a failed refresh preserves the last good value.

## Refresh intervals

The data groups have independent refresh schedules. Defaults range from five minutes for online counts to six hours for archived values. The full default and minimum intervals are listed in the [README](../README.md#refresh-intervals). Faster polling does not guarantee fresher game observations. The integration follows rate-limit responses when available.

## Scope

This document describes the user-facing access model and configuration. It intentionally leaves provider addresses, request paths and other service identifiers unspecified while access arrangements are being clarified.
