# BlockFront Home Assistant integration implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an initial Home Assistant custom integration for public BlockFront player stats, matches, online count with official-site fallback, and API service health.

**Architecture:** Use one config entry keyed by resolved player UUID and a small aiohttp API client. Four independent coordinators poll profile, matches, online count, and service status at validated options-flow intervals; sensors subscribe to the relevant coordinator and preserve last known good values across failed updates.

**Tech Stack:** Python 3.13+, Home Assistant config entries and DataUpdateCoordinator, aiohttp, pytest with pytest-homeassistant-custom-component, GitHub Actions and hassfest.

**Spec:** `docs/superpowers/specs/2026-10-09-blockfront-ha-integration-design.md`

## Global Constraints

- Config flow asks only for a BlockFront username and resolves it once to a UUID.
- Defaults are 900 seconds for profile and matches, 300 seconds for online count, and 900 seconds for service status.
- Online count uses Blocklytics `/overview` first and fetches `https://www.blockfrontmc.com/` only when the API request or payload fails validation.
- Never represent missing/failed values as numeric zero; preserve the last good value and expose source/error/time metadata.
- Do not modify or install/restart the user's Home Assistant environment.
- Do not assume undocumented endpoints or use the unconfirmed bulk endpoint.

## Review Focus

- Unknown usernames, duplicate UUID entries, invalid names, and timeouts must return useful config-flow errors without creating partial entries; test these in Task 1.
- Missing optional profile fields and an empty/malformed matches response must not fabricate values or crash sensors; test parsers in Task 1.
- Online API transport/HTTP/shape failure must invoke exactly one official page fetch and parse only a nonnegative `N Players Online Now!`; bad HTML must preserve prior state; test in Task 2.
- A successful service HTTP response with stale or failing upstream feeds must report degraded, not healthy; malformed status payload must not crash; test in Task 2.
- Different intervals must schedule independently, and successful API count cycles must not fetch the site; test interval setup and fallback call count in Task 2.

---

### Task 1: API client, config/options flow, and entry lifecycle

**Files:**
- Create: `custom_components/blockfront/const.py`
- Create: `custom_components/blockfront/manifest.json`
- Create: `custom_components/blockfront/__init__.py`
- Create: `custom_components/blockfront/api.py`
- Create: `custom_components/blockfront/config_flow.py`
- Create: `custom_components/blockfront/coordinator.py`
- Create: `custom_components/blockfront/strings.json`
- Create: `tests/conftest.py`
- Create: `tests/test_config_flow.py`
- Create: `tests/test_api.py`
- Create: `requirements_test.txt`
- Create: `pyproject.toml`

**Interfaces:** `BlockFrontApi(session)` provides `async_resolve_player(username) -> dict`, `async_get_player(uuid) -> dict`, `async_get_matches(uuid) -> dict`, `async_get_overview() -> dict`, `async_get_status() -> dict`, and `async_get_official_online_count() -> int`. `BlockFrontConfigFlow` stores normalized username and resolved UUID. `BlockFrontOptionsFlow` independently validates `profile_interval`, `matches_interval`, `online_interval`, and `status_interval` in seconds.

- [ ] Write tests for username resolution success, unknown/malformed response, duplicate config entry, and interval bounds; run and observe expected failures.
- [ ] Write API client parsing tests for non-200 responses, request timeout, malformed JSON/shape, profile null fields, and match lists; run and observe expected failures.
- [ ] Implement the client with Home Assistant's shared aiohttp session and bounded request timeout; no authentication or bulk endpoint.
- [ ] Implement config flow, options flow defaults/bounds, four independent coordinators, config-entry setup/unload, and strings/translations.
- [ ] Run `pytest -q tests/test_config_flow.py tests/test_api.py`; all tests must pass.
- [ ] Commit as `feat: add BlockFront config and API client`.

### Task 2: Sensors, independent updates, and online fallback

**Files:**
- Create: `custom_components/blockfront/sensor.py`
- Create: `tests/test_coordinator.py`
- Create: `tests/test_sensor.py`

**Interfaces:** `PlayerCoordinator.data` contains validated profile data and refresh metadata. `MatchesCoordinator.data` contains the newest match or an empty marker plus refresh metadata. `OnlineCoordinator.data` contains `count`, `source`, `updated_at`, and `last_error`. `StatusCoordinator.data` contains `status` (`online`, `degraded`, or `unavailable`), stale-feed count, version, uptime, timestamps, and last error.

- [ ] Test newest match extraction and sensor attributes for profile, match, online count, and diagnostic service status; run and observe expected failures.
- [ ] Test online API success avoids the official-site request; API failure requests the page once, parses the expected count, and reports source `official_website`; invalid page data raises a controlled update failure.
- [ ] Test service status reports degraded when any relevant feed is stale or has consecutive failures, even when HTTP status is 200.
- [ ] Implement sensor entities with stable UUID-based unique IDs, player device info, valid units/classes, and diagnostic entity category for service status.
- [ ] Add distinct coordinator schedules and ensure a failure keeps last good data; no rapid retry loop.
- [ ] Run `pytest -q tests/test_coordinator.py tests/test_sensor.py` and then the full `pytest -q`; all tests must pass.
- [ ] Commit as `feat: add BlockFront statistic sensors`.

### Task 3: Install docs, CI, and release readiness

**Files:**
- Create: `README.md`
- Create: `hacs.json`
- Create: `.github/workflows/validate.yml`
- Create or update: localization files under `custom_components/blockfront/translations/`

- [ ] Document HACS/manual install, config flow, each sensor and important attributes, default/options intervals, source freshness/staleness, fallback limits, troubleshooting, and user-run HAOS validation steps.
- [ ] Add GitHub Actions for pytest, Home Assistant hassfest, and HACS validation using supported official actions.
- [ ] Run local test suite, `python -m script.hassfest` in a compatible Home Assistant environment, `hacs.json` validation, and repository diff checks.
- [ ] Review implementation against every scope and failure requirement in the spec; correct any gap and rerun the affected checks.
- [ ] Commit as `docs: document and validate BlockFront integration`.
