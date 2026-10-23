"""HTTP client for configured statistics and public BlockFront endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import Any
from urllib.parse import quote, urlencode, urlsplit
from uuid import UUID

import aiohttp

from .request_scheduler import RequestScheduler

OFFICIAL_API_BASE_URL = "https://api.blockfrontmc.com/api/v2/"
CLOUD_API_BASE_URL = "https://blockfrontapi.vuis.dev/api/v1/"
OFFICIAL_WEBSITE_URL = "https://www.blockfrontmc.com/"
REQUEST_TIMEOUT_SECONDS = 15

_ONLINE_COUNT_PATTERN = re.compile(
    r"(?<![\w-])(\d+)\s+Players\s+Online\s+Now!(?=\s|<|$)", re.IGNORECASE
)
_REQUEST_SCHEDULER = RequestScheduler()
_IN_FLIGHT_REQUESTS: dict[str, asyncio.Task[dict[str, Any]]] = {}


class ApiError(Exception):
    """An API request or response could not be used."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: str | None = None,
        rate_limit: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
        self.rate_limit = rate_limit or {}


class PlayerNotFound(ApiError):
    """The requested player could not be resolved."""


def normalize_api_base_url(value: str) -> str:
    """Validate and normalize a user-supplied API base URL."""
    candidate = value.strip()
    parsed = urlsplit(candidate)
    try:
        _ = parsed.port
    except ValueError as err:
        raise ValueError("Invalid API base URL") from err
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or any(character.isspace() for character in candidate)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Invalid API base URL")
    return f"{candidate.rstrip('/')}/"


class BlockFrontApi:
    """Small async client using Home Assistant's shared aiohttp session."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        timeout: int = REQUEST_TIMEOUT_SECONDS,
        api_key: str | None = None,
        api_base_url: str | None = None,
        scheduler: RequestScheduler | None = None,
    ) -> None:
        self._session = session
        self._api_key = api_key.strip() if api_key and api_key.strip() else None
        try:
            self._api_base_url = normalize_api_base_url(api_base_url or "")
        except ValueError:
            self._api_base_url = None
        self._scheduler = scheduler or _REQUEST_SCHEDULER
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._last_rate_limit: dict[str, str] = {}
        self._last_retry_after: str | None = None
        self.public_rate_limit: dict[str, str] = {}
        self.public_last_attempt: str | None = None
        self.public_last_success: str | None = None
        self.public_last_error: str | None = None
        self._public_retry_until = 0.0
        self._public_reset_at: str | None = None
        self._etag_cache: dict[str, tuple[str, dict[str, Any]]] = {}
        self._archive_unsupported_until: dict[str, float] = {}

    async def _get_json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        base_url: str | None = None,
        service_name: str = "Statistics API",
    ) -> dict[str, Any]:
        """Coalesce identical GETs within the same origin and credential scope."""
        selected_base = base_url or self._api_base_url
        if selected_base is None:
            return await self._async_get_json(
                path, params=params, base_url=base_url, service_name=service_name
            )
        primary = selected_base == self._api_base_url
        scope_material = f"{selected_base}|{self._api_key if primary else ''}"
        scope = hashlib.sha256(scope_material.encode()).hexdigest()
        request_key = hashlib.sha256(
            f"{scope}|{selected_base}{path}|{urlencode(sorted((params or {}).items()))}".encode()
        ).hexdigest()
        task = _IN_FLIGHT_REQUESTS.get(request_key)
        if task is None:
            task = asyncio.create_task(
                self._async_get_json(
                    path, params=params, base_url=base_url, service_name=service_name
                )
            )
            _IN_FLIGHT_REQUESTS[request_key] = task

            def clear(completed: asyncio.Task[dict[str, Any]]) -> None:
                if _IN_FLIGHT_REQUESTS.get(request_key) is completed:
                    _IN_FLIGHT_REQUESTS.pop(request_key, None)

            task.add_done_callback(clear)
        return await asyncio.shield(task)

    async def _async_get_json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        base_url: str | None = None,
        service_name: str = "Statistics API",
    ) -> dict[str, Any]:
        if base_url is None:
            if self._api_base_url is None:
                raise ApiError("Statistics API base URL is not configured")
            base_url = self._api_base_url
        url = f"{base_url}{path}"
        primary = base_url == self._api_base_url
        scope_material = f"{base_url}|{self._api_key if primary else ''}"
        request_scope = hashlib.sha256(scope_material.encode()).hexdigest()
        cache_key = f"{url}?{urlencode(sorted((params or {}).items()))}"
        if primary and self._public_retry_until > monotonic():
            raise ApiError(
                "Statistics API polling paused until the request quota recovers",
                status_code=429,
                retry_after=str(math.ceil(self._public_retry_until - monotonic())),
                rate_limit=self.public_rate_limit,
            )
        if primary:
            self.public_last_attempt = datetime.now(UTC).isoformat()
        try:
            request_headers = {}
            if primary and self._api_key:
                request_headers["Authorization"] = f"Bearer {self._api_key}"
            cached = self._etag_cache.get(cache_key)
            if cached is not None:
                request_headers["If-None-Match"] = cached[0]
            request_options: dict[str, Any] = {
                "params": params,
                "timeout": self._timeout,
                "allow_redirects": False,
            }
            if request_headers:
                request_options["headers"] = request_headers
            async with (
                self._scheduler.request(request_scope, priority=_request_priority(path)),
                self._session.get(url, **request_options) as response,
            ):
                headers = getattr(response, "headers", {})
                rate_limit = _rate_limit_headers(headers)
                retry_after = headers.get("Retry-After")
                self._last_rate_limit = rate_limit
                self._last_retry_after = retry_after
                if primary:
                    self.public_rate_limit = rate_limit
                    reset = _retry_seconds(headers.get("RateLimit-Reset"))
                    self._public_reset_at = (
                        (datetime.now(UTC) + timedelta(seconds=reset)).isoformat()
                        if reset is not None
                        else None
                    )
                    if response.status == 429:
                        delay = _retry_seconds(retry_after)
                        delay = delay if delay is not None else (reset or 60)
                        self._public_retry_until = monotonic() + max(delay, 1)
                        self._scheduler.pause(request_scope, max(delay, 1))
                    elif rate_limit.get("RateLimit-Remaining") == "0" and reset is not None:
                        self._public_retry_until = monotonic() + max(reset, 1)
                        self._scheduler.pause(request_scope, max(reset, 1))
                if response.status == 304:
                    if cached is None:
                        raise ApiError(f"{service_name} returned 304 without a cached response")
                    if primary:
                        self.public_last_success = datetime.now(UTC).isoformat()
                        self.public_last_error = None
                    self._scheduler.successful(request_scope)
                    return cached[1]
                if response.status == 404:
                    raise ApiError(
                        "Player or endpoint was not found",
                        status_code=404,
                        retry_after=retry_after,
                        rate_limit=rate_limit,
                    )
                if response.status >= 400:
                    if response.status >= 500:
                        self._scheduler.transient_failure(request_scope)
                    raise ApiError(
                        f"{service_name} returned HTTP {response.status}",
                        status_code=response.status,
                        retry_after=retry_after,
                        rate_limit=rate_limit,
                    )
                try:
                    payload = await response.json(content_type=None)
                except (aiohttp.ContentTypeError, json.JSONDecodeError, UnicodeDecodeError) as err:
                    raise ApiError(f"{service_name} returned invalid JSON") from err
                if not isinstance(payload, dict):
                    raise ApiError(f"{service_name} returned an invalid response")
                if primary:
                    _validate_public_response(path, payload)
                etag = headers.get("ETag")
                if isinstance(etag, str) and etag:
                    if len(self._etag_cache) >= 256 and cache_key not in self._etag_cache:
                        self._etag_cache.pop(next(iter(self._etag_cache)))
                    self._etag_cache[cache_key] = (etag, payload)
        except ApiError as err:
            if primary:
                self.public_last_error = str(err)
            raise
        except (TimeoutError, aiohttp.ClientError) as err:
            self._scheduler.transient_failure(request_scope)
            if primary:
                self.public_last_error = f"Request failed: {err.__class__.__name__}"
            if isinstance(err, TimeoutError):
                raise ApiError(f"{service_name} request timed out") from err
            raise ApiError(f"{service_name} request failed: {err.__class__.__name__}") from err

        if primary:
            self.public_last_success = datetime.now(UTC).isoformat()
            self.public_last_error = None
        self._scheduler.successful(request_scope)
        return payload

    def polling_data(self) -> dict[str, Any]:
        """Return the last observed shared-IP token bucket, not a fixed RPM quota."""
        return {
            "api_polling_status": (
                "rate_limited"
                if self._public_retry_until > monotonic()
                else "unavailable"
                if self.public_last_error or not self.public_last_success
                else "available"
            ),
            "api_rate_limit_limit": _header_number(self.public_rate_limit, "RateLimit-Limit"),
            "api_rate_limit_remaining": _header_number(
                self.public_rate_limit, "RateLimit-Remaining"
            ),
            "api_rate_limit_reset_at": self._public_reset_at,
            "api_retry_after": max(0, math.ceil(self._public_retry_until - monotonic())),
            "api_rate_limit_headers": dict(self.public_rate_limit),
            "api_last_attempt": self.public_last_attempt,
            "api_last_successful_update": self.public_last_success,
            "api_last_error": self.public_last_error,
        }

    async def _get_text(self, url: str) -> str:
        try:
            async with self._session.get(url, timeout=self._timeout) as response:
                if response.status >= 400:
                    raise ApiError(
                        f"Official BlockFront website returned HTTP {response.status}",
                        status_code=response.status,
                    )
                return await response.text()
        except ApiError:
            raise
        except (TimeoutError, aiohttp.ClientError) as err:
            if isinstance(err, TimeoutError):
                raise ApiError("Official BlockFront website request timed out") from err
            raise ApiError(
                f"Official BlockFront website request failed: {err.__class__.__name__}"
            ) from err

    async def async_resolve_player(self, username: str) -> str:
        """Resolve only an exact username match; search results may be partial."""
        payload = await self._get_json("players/search", params={"q": username})
        players, _ = unpack_response(payload, list)
        for player in players:
            if not isinstance(player, dict):
                raise ApiError("Statistics API returned an invalid player search result")
            name = player.get("username")
            if isinstance(name, str) and name.casefold() == username.casefold():
                try:
                    return str(UUID(player["uuid"]))
                except (KeyError, ValueError, TypeError, AttributeError) as err:
                    raise ApiError("Statistics API returned an invalid player UUID") from err
        raise PlayerNotFound("BlockFront player was not found", status_code=404)

    async def async_get_player(self, player_uuid: str) -> dict[str, Any]:
        """Normalize the public profile without changing existing HA entity keys."""
        data, meta = unpack_response(await self._get_json(f"players/{player_uuid}"), dict)
        stats = data.get("stats")
        if not isinstance(stats, dict):
            raise ApiError("Statistics API returned invalid lifetime statistics")
        profile = {local: stats.get(remote) for local, remote in PROFILE_STAT_FIELDS.items()}
        clan = data.get("clan")
        profile.update(
            {
                "uuid": data.get("uuid"),
                "username": data.get("username"),
                "exp": data.get("exp"),
                "rank": data.get("militaryRank"),
                "prestige": data.get("prestige"),
                "skill_rank": data.get("competitiveRank"),
                "clan": (clan.get("name") or clan.get("tag")) if isinstance(clan, dict) else None,
                "clan_uuid": clan.get("uuid") if isinstance(clan, dict) else None,
                "source": data.get("source"),
                "source_timestamp": meta.get("updatedAt"),
                "source_stale": meta.get("stale", True),
                "unavailable_fields": data.get("unavailableFields", []),
                "match_karma": None,
                "bootcamp": None,
                "class_exp": None,
                "trophies": None,
            }
        )
        return profile

    async def async_get_match_data(self, player_uuid: str) -> dict[str, Any]:
        """Fetch the largest documented recent-match page and its metadata."""
        data, meta = unpack_response(
            await self._get_json(f"players/{player_uuid}/matches", params={"limit": "100"}), list
        )
        if any(not isinstance(item, dict) for item in data):
            raise ApiError("Statistics API returned an invalid matches list")
        matches = []
        for item in data:
            match = {MATCH_FIELDS.get(key, key): value for key, value in item.items()}
            ended = match.get("ended_at")
            duration = match.get("duration_seconds")
            if isinstance(ended, str) and isinstance(duration, int) and duration > 0:
                try:
                    match["started_at_estimated"] = (
                        datetime.fromisoformat(ended.replace("Z", "+00:00"))
                        - timedelta(seconds=duration)
                    ).isoformat()
                except ValueError:
                    pass
            matches.append(match)
        return {
            "matches": matches,
            "pagination": meta.get("pagination"),
            "source_timestamp": meta.get("updatedAt"),
            "source_stale": meta.get("stale", True),
            "source": "statistics_api",
        }

    async def async_get_matches(self, player_uuid: str) -> list[dict[str, Any]]:
        """Return the most recent match page for existing client consumers."""
        return (await self.async_get_match_data(player_uuid))["matches"]

    async def async_get_overview(self) -> dict[str, Any]:
        """Read the new online endpoint through the existing online abstraction."""
        data, meta = unpack_response(await self._get_json("online"), dict)
        return {
            "online": data,
            "generatedAt": data.get("capturedAt"),
            "source_stale": meta.get("stale", True),
        }

    async def async_get_analytics(self, player_uuid: str) -> dict[str, Any]:
        """Fetch recorded-match analytics with map and mode breakdowns."""
        base = f"players/{player_uuid}/analytics"
        errors: dict[str, str | None] = {
            "summary_error": None,
            "maps_error": None,
            "modes_error": None,
        }
        summary: dict[str, Any] = {}
        maps: list[dict[str, Any]] = []
        modes: list[dict[str, Any]] = []
        meta: dict[str, Any] = {}
        map_meta: dict[str, Any] = {}
        mode_meta: dict[str, Any] = {}
        for key, path, expected in (
            ("summary", base, dict),
            ("maps", f"{base}/maps", list),
            ("modes", f"{base}/modes", list),
        ):
            try:
                data, response_meta = unpack_response(await self._get_json(path), expected)
                if isinstance(data, list) and any(not isinstance(row, dict) for row in data):
                    raise ApiError("Statistics API returned invalid performance rows")
            except ApiError as err:
                errors[f"{key}_error"] = str(err)
                continue
            if key == "summary":
                summary, meta = data, response_meta
            elif key == "maps":
                maps, map_meta = data, response_meta
            else:
                modes, mode_meta = data, response_meta
        if all(errors.values()):
            raise ApiError("Statistics API recorded analytics are unavailable")
        # Mode groups partition the recorded sample. Never substitute lifetime totals.
        totals = {}
        for key in ("games", "wins", "losses", "score"):
            values = [row.get(key) for row in modes]
            totals[key] = (
                sum(values)
                if values
                and all(
                    isinstance(value, int) and not isinstance(value, bool) and value >= 0
                    for value in values
                )
                else None
            )
        games = totals["games"]
        most_played = max(maps, key=lambda row: _valid_count(row.get("games")), default={})
        return {
            "tracked_matches": summary.get("trackedMatches"),
            "recorded_wins": totals["wins"],
            "recorded_losses": totals["losses"],
            "recorded_win_rate": (
                round(totals["wins"] / games * 100, 2)
                if games and totals["wins"] is not None
                else None
            ),
            "average_match_score": (
                round(totals["score"] / games, 2) if games and totals["score"] is not None else None
            ),
            "most_played_map": most_played.get("mapName") or most_played.get("map"),
            "most_played_map_key": most_played.get("map"),
            "maps": maps,
            "modes": modes,
            "sample_matches": games,
            "computed_at": summary.get("computedAt"),
            "source_timestamp": meta.get("updatedAt"),
            "source_stale": any(m.get("stale", True) for m in (meta, map_meta, mode_meta))
            or any(errors.values()),
            "source": "statistics_api",
            **errors,
            "datasets": {
                "summary": {
                    "data": summary or None,
                    "source_timestamp": meta.get("updatedAt"),
                    "source_stale": meta.get("stale", True),
                    "error": errors["summary_error"],
                },
                "maps": {
                    "data": maps if not errors["maps_error"] else None,
                    "source_timestamp": map_meta.get("updatedAt"),
                    "source_stale": map_meta.get("stale", True),
                    "error": errors["maps_error"],
                },
                "modes": {
                    "data": modes if not errors["modes_error"] else None,
                    "source_timestamp": mode_meta.get("updatedAt"),
                    "source_stale": mode_meta.get("stale", True),
                    "error": errors["modes_error"],
                },
            },
        }

    async def async_get_player_history(
        self, player_uuid: str, *, clan_uuid: str | None = None, clan_name: str | None = None
    ) -> dict[str, Any]:
        """Fetch the player's cumulative, competitive-rank and season-score histories."""
        result: dict[str, Any] = {}
        requests = {
            "lifetime": (f"players/{player_uuid}/history", {"days": "365"}),
            "competitive": (f"players/{player_uuid}/competitive-history", None),
            "season": (f"players/{player_uuid}/score-history", {"days": "365"}),
        }
        for key, (path, params) in requests.items():
            try:
                data, meta = unpack_response(await self._get_json(path, params=params), dict)
                points = data.get("points")
                if not isinstance(points, list) or any(
                    not isinstance(point, dict) for point in points
                ):
                    raise ApiError(f"Statistics API returned invalid {key} history")
                result[key] = {
                    "points": points,
                    "observed_until": data.get("observedUntil"),
                    "days": data.get("days"),
                    "source_timestamp": meta.get("updatedAt"),
                    "source_stale": meta.get("stale", True),
                    "error": None,
                }
            except ApiError as err:
                result[key] = {
                    "points": None,
                    "source_timestamp": None,
                    "source_stale": True,
                    "error": str(err),
                }

        if clan_uuid or clan_name:
            resolved_clan = clan_uuid
            if not resolved_clan and clan_name:
                try:
                    data, _ = unpack_response(
                        await self._get_json("clans", params={"q": clan_name, "limit": "20"}), list
                    )
                    exact = next(
                        (
                            item
                            for item in data
                            if isinstance(item, dict)
                            and any(
                                isinstance(candidate, str)
                                and candidate.casefold() == clan_name.casefold()
                                for candidate in (item.get("name"), item.get("tag"))
                            )
                        ),
                        None,
                    )
                    resolved_clan = exact.get("uuid") if exact else None
                except (ApiError, AttributeError):
                    result["clan"] = {"error": "Clan could not be resolved"}
            if resolved_clan:
                clan_data: dict[str, Any] = {}
                try:
                    detail, meta = unpack_response(
                        await self._get_json(f"clans/{resolved_clan}"), dict
                    )
                    clan_data["detail"] = detail
                    clan_data["source_timestamp"] = meta.get("updatedAt")
                    clan_data["source_stale"] = meta.get("stale", True)
                except ApiError as err:
                    clan_data["detail_error"] = str(err)
                try:
                    score, meta = unpack_response(
                        await self._get_json(
                            f"clans/{resolved_clan}/score-history", params={"days": "365"}
                        ),
                        dict,
                    )
                    clan_data["score_history"] = score.get("points", [])
                    clan_data["score_history_timestamp"] = meta.get("updatedAt")
                except ApiError as err:
                    clan_data["score_history_error"] = str(err)
                result["clan"] = clan_data

        if not any(
            isinstance(value, dict)
            and value.get("error") is None
            and isinstance(value.get("points"), list)
            for value in result.values()
        ):
            raise ApiError("Statistics API player history is unavailable")
        result["source"] = "statistics_api"
        return result

    async def async_get_archive_data(self, player_uuid: str) -> dict[str, Any]:
        """Read optional archived class XP and inventory from API envelopes."""
        result: dict[str, Any] = {}
        for key, suffix in (("classes", "classes"), ("inventory", "inventory")):
            path = f"players/{player_uuid}/{suffix}"
            try:
                if self._archive_unsupported_until.get(path, 0.0) > monotonic():
                    raise ApiError(
                        f"Statistics API {key} archive endpoint is unavailable (HTTP 404)",
                        status_code=404,
                    )

                payload = await self._get_json(path)
                if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                    items, meta = unpack_response(payload, list)
                    data: dict[str, Any] = {}
                else:
                    data, meta = unpack_response(payload, dict)
                    items = data.get("items")
                if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                    raise ApiError(f"Statistics API returned invalid {key} archive data")
                captured_at = data.get("captured_at")
                if captured_at is None:
                    captured_at = meta.get("updatedAt")
                if captured_at is not None and (
                    isinstance(captured_at, bool)
                    or not isinstance(captured_at, (int, float, str))
                    or (
                        isinstance(captured_at, (int, float))
                        and (not math.isfinite(captured_at) or captured_at < 0)
                    )
                ):
                    raise ApiError(f"Statistics API returned an invalid {key} capture timestamp")

                result[key] = {
                    "items": items,
                    "captured_at": captured_at,
                    "source_timestamp": meta.get("updatedAt"),
                    "source_stale": meta["stale"],
                    "source": "statistics_api_archive",
                    "error": None,
                }
            except ApiError as err:
                if err.status_code == 404:
                    # Optional endpoints may not exist; one re-probe per day is enough.
                    self._archive_unsupported_until[path] = monotonic() + 86_400
                result[key] = {
                    "items": None,
                    "captured_at": None,
                    "source_timestamp": None,
                    "source_stale": True,
                    "source": "statistics_api_archive",
                    "error": str(err),
                }
        if all(result[key]["error"] for key in ("classes", "inventory")):
            raise ApiError("Statistics API archive data is unavailable")
        result["source_stale"] = any(
            result[key]["source_stale"] for key in ("classes", "inventory")
        )
        return result

    async def async_get_global_data(self, *, featured_map: str | None = None) -> dict[str, Any]:
        """Fetch public game-wide trends, maps and leaderboards in bounded pages."""
        endpoints: dict[str, tuple[str, dict[str, str] | None, type]] = {
            "online_history": ("online/history", {"hours": "168"}, dict),
            "trends": ("trends", {"days": "90"}, dict),
            "maps": ("maps", None, list),
            "players": ("leaderboards/players", {"limit": "100"}, list),
            "clans": ("leaderboards/clans", {"limit": "100"}, list),
            "competitive": ("leaderboards/competitive", {"limit": "100"}, list),
        }
        result: dict[str, Any] = {"source": "statistics_api", "datasets": {}}
        for key, (path, params, expected) in endpoints.items():
            try:
                data, meta = unpack_response(await self._get_json(path, params=params), expected)
                if isinstance(data, list) and any(not isinstance(item, dict) for item in data):
                    raise ApiError(f"Statistics API returned invalid {key} data")
                result["datasets"][key] = {
                    "data": data,
                    "source_timestamp": meta.get("updatedAt"),
                    "source_stale": meta.get("stale", True),
                    "pagination": meta.get("pagination"),
                    "error": None,
                }
            except ApiError as err:
                result["datasets"][key] = {
                    "data": None,
                    "source_timestamp": None,
                    "source_stale": True,
                    "error": str(err),
                }
        if all(item.get("error") for item in result["datasets"].values()):
            raise ApiError("Statistics API global statistics are unavailable")
        result["featured_map"] = None
        if featured_map:
            try:
                map_path = quote(featured_map, safe="")
                data, meta = unpack_response(await self._get_json(f"maps/{map_path}"), dict)
                result["featured_map"] = {
                    "data": data,
                    "source_timestamp": meta.get("updatedAt"),
                    "source_stale": meta.get("stale", True),
                    "error": None,
                }
            except ApiError as err:
                result["featured_map"] = {"data": None, "error": str(err), "source_stale": True}
        result["source_stale"] = any(item["source_stale"] for item in result["datasets"].values())
        return result

    async def async_get_cloud_data(self) -> dict[str, Any]:
        """Fetch the aggregate online-player count and response limit metadata."""
        payload = await self._get_json(
            "cloud_data",
            base_url=CLOUD_API_BASE_URL,
            service_name="BlockFront cloud API",
        )
        return {
            **payload,
            "_rate_limit": self._last_rate_limit,
            "_retry_after": self._last_retry_after,
        }

    async def async_get_status(self) -> dict[str, Any]:
        """Fetch service and upstream-feed status."""
        payload = await self._get_json("status")
        return {**payload, "_polling": self.polling_data()}

    async def async_get_official_online_count(self) -> int:
        """Fetch and parse the online count rendered on the official site."""
        return parse_official_online_count(await self._get_text(OFFICIAL_WEBSITE_URL))


async def async_fetch_online_data(api: BlockFrontApi) -> dict[str, Any]:
    """Fetch the API online count, falling back to the official web page."""
    try:
        overview = await api.async_get_overview()
        return {
            "online_count": parse_online_count(overview),
            "source": "statistics_api",
            "source_timestamp": overview.get("generatedAt"),
            "api_error": None,
        }
    except ApiError as api_error:
        try:
            count = await api.async_get_official_online_count()
        except ApiError as website_error:
            raise ApiError(
                f"Online count unavailable from API and official website: {website_error}"
            ) from api_error
        return {
            "online_count": count,
            "source": "official_website",
            "source_timestamp": None,
            "api_error": str(api_error),
        }


def parse_cloud_data(payload: object) -> dict[str, Any]:
    """Validate the cloud service's aggregate online-player count."""
    if not isinstance(payload, dict):
        raise ApiError("BlockFront cloud API returned an invalid response")

    online = payload.get("players_online")
    if isinstance(online, bool) or not isinstance(online, int) or online < 0:
        raise ApiError("BlockFront cloud API online player count was missing or invalid")

    return {
        "online_count": online,
        "rate_limit": payload.get("_rate_limit", {}),
        "retry_after": payload.get("_retry_after"),
    }


async def async_fetch_cloud_data(api: BlockFrontApi) -> dict[str, Any]:
    """Select the first usable online source without probing unnecessary fallbacks."""
    errors: dict[str, str] = {}
    primary_candidate: tuple[int, str | int | None] | None = None

    def selected(
        count: int,
        source: str,
        *,
        captured_at: str | int | None = None,
        stale: bool | None = None,
        rate_limit: dict[str, str] | None = None,
        retry_after: str | None = None,
    ) -> dict[str, Any]:
        return {
            "online_count": count,
            "source": source,
            "source_timestamp": captured_at,
            "source_stale": stale,
            # Backups without capture metadata are live HTTP reads with unknown age.
            "source_freshness": (
                "stale"
                if stale is True
                else "reported_current"
                if stale is False and captured_at is not None
                else "unknown"
            ),
            "rate_limit": rate_limit or {},
            "retry_after": retry_after,
            "public_api_error": errors.get("statistics_api"),
            "api_error": errors.get("blockfront_official_api") or errors.get("official_website"),
            "fallback_errors": dict(errors),
            "polling_status": "degraded" if stale is True else "available",
        }

    try:
        overview = await api.async_get_overview()
        count = parse_online_count(overview)
        captured_at = overview.get("generatedAt")
        if overview.get("source_stale") is True:
            # An explicit upstream stale marker triggers a fallback probe.
            primary_candidate = (count, captured_at)
        else:
            return selected(
                count,
                "statistics_api",
                captured_at=captured_at,
                stale=overview.get("source_stale")
                if isinstance(overview.get("source_stale"), bool)
                else None,
            )
    except ApiError as err:
        errors["statistics_api"] = str(err)

    official_error: ApiError | None = None
    try:
        official = await api._get_json(
            "",
            params={"type": "player_count"},
            base_url=OFFICIAL_API_BASE_URL,
            service_name="Official BlockFront API",
        )
        official_count = parse_online_count({"online": official})
    except ApiError as err:
        official_error = err
        errors["blockfront_official_api"] = str(err)
    else:
        return selected(official_count, "blockfront_official_api", stale=False)

    website_error: ApiError | None = None
    try:
        website_count = await api.async_get_official_online_count()
    except ApiError as err:
        website_error = err
        errors["official_website"] = str(err)
    else:
        return selected(website_count, "official_website", stale=False)

    if primary_candidate is not None:
        # The only valid reading is old; don't discard it or invent a new capture time.
        return selected(
            primary_candidate[0],
            "statistics_api",
            captured_at=primary_candidate[1],
            stale=True,
        )

    last_error = official_error or website_error
    raise ApiError(
        "Online player data unavailable from all sources",
        status_code=last_error.status_code if last_error else None,
        retry_after=last_error.retry_after if last_error else None,
        rate_limit=last_error.rate_limit if last_error else None,
    )


def _rate_limit_headers(headers: Any) -> dict[str, str]:
    """Return rate-limit headers when the upstream publishes them."""
    names = (
        "RateLimit-Limit",
        "RateLimit-Remaining",
        "RateLimit-Reset",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    )
    return {name: str(headers[name]) for name in names if name in headers}


def _request_priority(path: str) -> int:
    """Prioritize fresh online/player data ahead of bulky archive endpoints."""
    lowered = path.casefold()
    if lowered.endswith("/classes") or lowered.endswith("/inventory"):
        return 0
    if "leaderboards" in lowered or lowered.startswith("trends") or lowered.startswith("maps"):
        return 1
    if "/history" in lowered or "analytics" in lowered:
        return 2
    if lowered.endswith("/matches") or lowered in {"online", "status"}:
        return 10
    if lowered.startswith("players/"):
        return 8
    return 4


def parse_online_count(payload: object) -> int:
    """Return a validated player count from the Statistics API overview payload."""
    if not isinstance(payload, dict):
        raise ApiError("Statistics API online count response was malformed")
    online = payload.get("online")
    if not isinstance(online, dict):
        raise ApiError("Statistics API online count response was malformed")
    count = online.get("playersOnline")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ApiError("Statistics API online count was missing or invalid")
    return count


def parse_official_online_count(html: str) -> int:
    """Parse only the expected server-rendered official-site count phrase."""
    match = _ONLINE_COUNT_PATTERN.search(html)
    if match is None:
        raise ApiError("Official BlockFront website online count was not found")
    return int(match.group(1))


def parse_service_status(payload: object) -> dict[str, Any]:
    """Use active dataset freshness, excluding retired legacy feeds."""
    data, meta = unpack_response(payload, dict)
    datasets = data.get("datasets")
    if not isinstance(datasets, dict) or not datasets:
        raise ApiError("Statistics API service status response has invalid datasets")
    if any(not isinstance(dataset, dict) for dataset in datasets.values()):
        raise ApiError("Statistics API service status response has invalid datasets")
    affected = [name for name, item in datasets.items() if item.get("stale") is not False]
    healthy = data.get("status") == "ok" and data.get("playerData") is True
    return {
        "status": "online"
        if healthy and not affected and meta.get("stale") is False
        else "degraded",
        "stale_feed_count": len(affected),
        "stale_datasets": affected,
        "datasets": datasets,
        "player_data_available": data.get("playerData"),
        "version": data.get("apiVersion"),
        "server_version": data.get("serverVersion"),
        "uptime_seconds": None,
        "upstream_error": "; ".join(affected) or None,
        "source_timestamp": meta.get("updatedAt"),
        "source_stale": meta.get("stale", True),
        **payload.get("_polling", {}),
    }


def unpack_response(payload: object, expected_type: type) -> tuple[Any, dict[str, Any]]:
    """Validate the documented public envelope, including freshness metadata."""
    if not isinstance(payload, dict):
        raise ApiError("Statistics API returned an invalid response")
    data, meta = payload.get("data"), payload.get("meta")
    if not isinstance(data, expected_type) or not isinstance(meta, dict):
        raise ApiError("Statistics API returned an invalid public API envelope")
    if not isinstance(meta.get("stale"), bool):
        raise ApiError("Statistics API returned invalid freshness metadata")
    return data, meta


def _validate_public_response(path: str, payload: dict[str, Any]) -> None:
    """Validate endpoint structure before recording a successful public request."""
    archive_collection = path.endswith(("/classes", "/inventory"))
    collection = path in {
        "players/search",
        "maps",
        "leaderboards/players",
        "leaderboards/clans",
        "leaderboards/competitive",
        "clans",
    } or path.endswith(("/matches", "/maps", "/modes", "/classes", "/inventory"))
    data, _ = unpack_response(
        payload,
        (list, dict) if archive_collection else list if collection else dict,
    )
    if archive_collection and isinstance(data, dict):
        if not isinstance(data.get("items"), list):
            raise ApiError("Statistics API returned invalid archive data")
        data = data["items"]
    if collection and any(not isinstance(item, dict) for item in data):
        raise ApiError("Statistics API returned invalid collection entries")
    if path == "players/search":
        for item in data:
            if not isinstance(item.get("username"), str):
                raise ApiError("Statistics API returned an invalid player search result")
            try:
                UUID(item["uuid"])
            except (KeyError, ValueError, TypeError, AttributeError) as err:
                raise ApiError("Statistics API returned an invalid player UUID") from err
    elif re.fullmatch(r"players/[^/]+", path):
        if not isinstance(data.get("stats"), dict):
            raise ApiError("Statistics API returned invalid lifetime statistics")
    elif path == "online":
        parse_online_count({"online": data})
    elif path == "status":
        parse_service_status(payload)


def _retry_seconds(value: object) -> float | None:
    """Read delta seconds or an HTTP Retry-After date, never an epoch reset."""
    if not isinstance(value, str):
        return None
    try:
        seconds = float(value)
        return max(0, seconds) if math.isfinite(seconds) else None
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


def _header_number(headers: dict[str, str], key: str) -> int | None:
    try:
        value = int(headers[key])
        return value if value >= 0 else None
    except (KeyError, ValueError):
        return None


def _valid_count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


PROFILE_STAT_FIELDS = {
    "total_games": "totalGames",
    "time_played": "timePlayedSeconds",
    "kills": "kills",
    "deaths": "deaths",
    "assists": "assists",
    "kd": "kd",
    "head_shots": "headshots",
    "hs_kr": "headshotsPerKill",
    "back_stabs": "backstabs",
    "no_scopes": "noScopes",
    "first_bloods": "firstBloods",
    "fire_kills": "fireKills",
    "heal_assists": "healAssists",
    "captures": "captures",
    "objective_score": "objectiveScore",
    "bot_kills": "botKills",
    "infected_kills": "infectedKills",
    "infected_rounds_won": "infectedRoundsWon",
    "infected_matches_won": "infectedMatchesWon",
    "vehicle_kills": "vehicleKills",
    "highest_kill_streak": "highestKillStreak",
    "highest_death_streak": "highestDeathStreak",
}
MATCH_FIELDS = {
    "matchId": "match_id",
    "mode": "game",
    "endedAt": "ended_at",
    "durationSeconds": "duration_seconds",
    "winnerTeam": "winner_team",
    "team": "player_team",
}
