# Initial implementation record

The first implementation added a username-based Home Assistant config flow, personal statistics and match sensors, online-player counts with fallback sources, service health, and independently configurable polling.

The work established these lasting behaviors:

- Keep the last known value when an update fails.
- Keep unavailable values unknown instead of reporting zero.
- Expose data freshness and source errors where available.
- Use bounded refresh schedules and respect service rate limits.
- Do not modify or restart the user's Home Assistant installation as part of repository work.

This file is an archived planning note. See the [README](../../../README.md), [data access](../../data-access.md) and [data coverage](../../data-coverage.md) for current user-facing documentation.
