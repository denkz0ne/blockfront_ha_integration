# Changelog

## 0.3.0 — 2026-10-20

- Cover the documented Blocklytics v1 API for player profiles, recent matches, analytics, lifetime history, competitive rank history, season scores, clans, maps, trends, online history, leaderboards and service status.
- Add preview archive sensors for class XP and saved inventory, including their original capture timestamps.
- Fetch up to 100 recent matches and expose pagination metadata.
- Add independently configurable refresh intervals for personal history, preview archives and global game data.
- Revalidate public API responses with ETags to reduce repeated data transfer and preserve source capture times.
- Preserve entity IDs, local rank badges, duration units and last good values on failures.
- Add recorded-match analytics, map/mode performance tables and latest-match duration/end entities.
- Expose source freshness, active-dataset health, quota diagnostics and HTTP 429 backoff.
- Retain Vuis per-mode counts and optional legacy karma/bootcamp fields.
- Keep unsupported trophies and missing values unknown instead of reporting zero.
- Document endpoint coverage, data freshness, preview-only compatibility data and request budgets.
