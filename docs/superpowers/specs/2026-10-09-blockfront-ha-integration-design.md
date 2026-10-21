# Initial integration design

This archived note records the original scope for the BlockFront Home Assistant integration. For current setup, data coverage, refresh schedules and limitations, see the [README](../../../README.md), [data access](../../data-access.md) and [data coverage](../../data-coverage.md) documents.

The initial design called for a username-based config flow, personal profile and match sensors, online-player counts with fallbacks, service health reporting, and independently scheduled updates. It also established that unavailable values should remain unknown, failed updates should preserve the last good value, and polling should not be treated as proof that source data is fresh.

This note is historical. Current behavior and configuration are described in the user documentation.
