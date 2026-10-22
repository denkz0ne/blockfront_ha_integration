# Changelog

## Unreleased

- Fetch online fallback sources only when the primary count is unavailable or explicitly stale; report the selected source, its capture metadata and actual polling status.
- Parse optional class XP/inventory archive envelopes correctly, preserve last-good partial archive data and avoid repeated HTTP 404 polling for 24 hours.
- Add regression tests for fallback ordering, stale data, rate limits and archived response validation.

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
