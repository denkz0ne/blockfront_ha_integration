# Data access and configuration

The integration reads BlockFront statistics from a separately configured API. Enter its base URL during setup or in **Configure** options. Availability and permitted use depend on authorization from the service provider. After updating an older installation, configure the base URL once; a saved API key is migrated automatically.

## API key

The API key is optional in initial setup and in the integration's **Configure** options. Use it only when its provider has authorized this integration. Home Assistant stores the URL and key with the integration entry and sends the key only to the configured statistics API. Neither credential is included in the repository. Leave the key field empty when editing options to retain a previously saved key.

Without an authorized key, personal profile and statistics may be unavailable. The aggregate online-player count may still be obtained from alternative sources.

## Data groups

The integration provides personal profile values, recent matches, recorded-match analysis, personal history and rank progression, plus selected game-wide statistics. Archived or optional values may be missing or older than the main profile data. Each entity exposes freshness details when the source provides them.

The integration reads previously collected statistics; polling does not force the game or provider to capture new data. Missing values remain unknown, and a failed refresh preserves the last good value.

## Refresh intervals

The data groups have independent refresh schedules. Defaults range from five minutes for online counts to six hours for archived values. The full default and minimum intervals are listed in the [README](../README.md#refresh-intervals). Faster polling does not guarantee fresher game observations. The integration follows rate-limit responses when available.

## Scope

This document describes the user-facing access model and configuration. It intentionally leaves provider addresses, request paths and other service identifiers unspecified while access arrangements are being clarified.
