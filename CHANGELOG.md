# Changelog

## 0.5.1 — 2026-10-22

- Render the optional activity entity as a native Home Assistant entity selector so it can be selected or changed in integration settings.
- Clarify configuration fields with help text in English and Slovak, including window matching, cooldown, idle checks and manual activity modes.
- Prefix player-specific entity names with the configured username and clarify the Statistics API request status sensor; leave global entities and entity IDs unchanged.

## 0.5.0 — 2026-10-22

- Coordinate and coalesce API requests by origin and credential scope; prioritize profile and match freshness, share quota cooldowns and back off transient failures.
- Learn conservative polling intervals from distinct source timestamps and retain each successful sibling dataset when another endpoint fails.
- Add configurable activity-aware personal polling with binary/text sensors, a 30-minute cooldown, idle heartbeat, manual override and a staged refresh button.
- Preserve distinct-source progression deltas, publish restart-safe `blockfront_new_match` events and expose full datasets through a response-only service.
- Bound recorded list attributes, suppress unchanged snapshot writes and make the example dashboard activity/freshness-aware and theme-safe.
- Parse archive response envelopes correctly and skip unused online fallback requests; stale primary counts now yield to fresher sources.

## 0.4.0 — 2026-10-22

- Configure the statistics API base URL locally instead of identifying its host in the repository.
- Rename the saved API credential to a generic field and migrate existing credentials automatically.
- Remove per-game-mode online sensors because no usable data source is currently available.
- Remove the private provider profile URL from the dashboard example.
- Keep aggregate online-player count fallback sources and report their source generically.
- Clarify API URL and key setup, authorization, and polling behavior in the documentation.

## 0.3.1 — 2026-10-21

- Add optional API key configuration during setup and in integration options.
- Send the key only to the external statistics service.
- Document that provider authorization is required and explain behavior when no key is configured.

## 0.3.0 — 2026-10-20

- Cover personal profiles, recent matches, analytics, history, rank progression, season scores, clans, maps, trends, online history, leaderboards and service status.
- Add archived class XP and saved inventory sensors, including their original capture timestamps.
- Fetch up to 100 recent matches and expose pagination metadata.
- Add independently configurable refresh intervals for personal history, archived data and game-wide statistics.
- Revalidate unchanged service responses to reduce repeated data transfer and preserve source capture times.
- Preserve entity IDs, local rank badges, duration units and last good values on failures.
- Add recorded-match analytics, map/mode performance tables and latest-match duration/end entities.
- Expose source freshness, service health, request-limit diagnostics and backoff after rate limits.
- Retain per-mode counts from a separate cloud source and optional legacy karma/bootcamp fields.
- Keep unsupported trophies and missing values unknown instead of reporting zero.
- Document data coverage, freshness, optional archived data and request budgets.
