"""HTTP client for the public Blocklytics and BlockFront endpoints."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

import aiohttp

API_BASE_URL = "https://preview.blocklytics.naknu.li/api/v1/"
CLOUD_API_BASE_URL = "https://blockfrontapi.vuis.dev/api/v1/"
OFFICIAL_WEBSITE_URL = "https://www.blockfrontmc.com/"
REQUEST_TIMEOUT_SECONDS = 15

_ONLINE_COUNT_PATTERN = re.compile(
    r"(?<![\w-])(\d+)\s+Players\s+Online\s+Now!(?=\s|<|$)", re.IGNORECASE
)


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


class BlockFrontApi:
    """Small async client using Home Assistant's shared aiohttp session."""

    def __init__(
        self, session: aiohttp.ClientSession, *, timeout: int = REQUEST_TIMEOUT_SECONDS
    ) -> None:
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._last_rate_limit: dict[str, str] = {}
        self._last_retry_after: str | None = None

    async def _get_json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        base_url: str = API_BASE_URL,
        service_name: str = "Blocklytics",
    ) -> dict[str, Any]:
        url = f"{base_url}{path}"
        try:
            async with self._session.get(url, params=params, timeout=self._timeout) as response:
                headers = getattr(response, "headers", {})
                rate_limit = _rate_limit_headers(headers)
                retry_after = headers.get("Retry-After")
                self._last_rate_limit = rate_limit
                self._last_retry_after = retry_after
                if response.status == 404:
                    raise ApiError(
                        "Player or endpoint was not found",
                        status_code=404,
                        retry_after=retry_after,
                        rate_limit=rate_limit,
                    )
                if response.status >= 400:
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
        except ApiError:
            raise
        except (TimeoutError, aiohttp.ClientError) as err:
            if isinstance(err, TimeoutError):
                raise ApiError(f"{service_name} request timed out") from err
            raise ApiError(f"{service_name} request failed: {err.__class__.__name__}") from err

        if not isinstance(payload, dict):
            raise ApiError(f"{service_name} returned an invalid response")
        return payload

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
                "Official BlockFront website request failed: "
                f"{err.__class__.__name__}"
            ) from err

    async def async_resolve_player(self, username: str) -> str:
        """Resolve a username to a canonical UUID."""
        try:
            payload = await self._get_json("resolve", params={"name": username})
        except ApiError as err:
            if err.status_code == 404:
                raise PlayerNotFound("BlockFront player was not found", status_code=404) from err
            raise

        value = payload.get("uuid")
        if not isinstance(value, str):
            raise PlayerNotFound("BlockFront player was not found")
        try:
            return str(UUID(value))
        except ValueError as err:
            raise ApiError("Blocklytics returned an invalid player UUID") from err

    async def async_get_player(self, player_uuid: str) -> dict[str, Any]:
        """Fetch public lifetime statistics for a player."""
        return await self._get_json(f"players/{player_uuid}")

    async def async_get_matches(self, player_uuid: str) -> list[dict[str, Any]]:
        """Fetch the player's recent match list."""
        payload = await self._get_json(f"players/{player_uuid}/matches")
        matches = payload.get("matches")
        if not isinstance(matches, list) or any(not isinstance(item, dict) for item in matches):
            raise ApiError("Blocklytics returned an invalid matches list")
        return matches

    async def async_get_overview(self) -> dict[str, Any]:
        """Fetch the general overview response."""
        return await self._get_json("overview")

    async def async_get_cloud_data(self) -> dict[str, Any]:
        """Fetch live cloud player totals and per-mode counts directly."""
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
        return await self._get_json("status")

    async def async_get_official_online_count(self) -> int:
        """Fetch and parse the online count rendered on the official site."""
        return parse_official_online_count(await self._get_text(OFFICIAL_WEBSITE_URL))


async def async_fetch_online_data(api: BlockFrontApi) -> dict[str, Any]:
    """Fetch the API online count, falling back to the official web page."""
    try:
        overview = await api.async_get_overview()
        return {
            "online_count": parse_online_count(overview),
            "source": "blocklytics",
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
    """Validate the cloud page's player totals and per-mode data."""
    if not isinstance(payload, dict):
        raise ApiError("BlockFront cloud API returned an invalid response")

    online = payload.get("players_online")
    counts = payload.get("game_player_count")
    if isinstance(online, bool) or not isinstance(online, int) or online < 0:
        raise ApiError("BlockFront cloud API online player count was missing or invalid")
    if not isinstance(counts, dict):
        raise ApiError("BlockFront cloud API game-mode counts were missing or invalid")

    parsed_counts: dict[str, int] = {}
    for mode, count in counts.items():
        if (
            not isinstance(mode, str)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
        ):
            raise ApiError("BlockFront cloud API returned invalid game-mode counts")
        parsed_counts[mode] = count

    return {
        "online_count": online,
        "game_player_count": parsed_counts,
        "scoreboard_reset_time": payload.get("scoreboard_reset_time"),
        "rate_limit": payload.get("_rate_limit", {}),
        "retry_after": payload.get("_retry_after"),
    }


async def async_fetch_cloud_data(api: BlockFrontApi) -> dict[str, Any]:
    """Fetch direct cloud stats, falling back only the total to the official site."""
    try:
        value = parse_cloud_data(await api.async_get_cloud_data())
    except ApiError as api_error:
        try:
            online_count = await api.async_get_official_online_count()
        except ApiError as website_error:
            raise ApiError(
                "Cloud player data unavailable from API and official website: "
                f"{website_error}",
                status_code=api_error.status_code,
                retry_after=api_error.retry_after,
                rate_limit=api_error.rate_limit,
            ) from api_error
        return {
            "online_count": online_count,
            "game_player_count": None,
            "scoreboard_reset_time": None,
            "rate_limit": api_error.rate_limit,
            "retry_after": api_error.retry_after,
            "source": "official_website",
            "polling_status": "rate_limited" if api_error.status_code == 429 else "unavailable",
            "api_error": str(api_error),
        }

    return {
        **value,
        "source": "blockfront_cloud_api",
        "polling_status": "available",
        "api_error": None,
    }


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


def parse_online_count(payload: object) -> int:
    """Return a validated player count from the Blocklytics overview payload."""
    if not isinstance(payload, dict):
        raise ApiError("Blocklytics online count response was malformed")
    online = payload.get("online")
    if not isinstance(online, dict):
        raise ApiError("Blocklytics online count response was malformed")
    count = online.get("playersOnline")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ApiError("Blocklytics online count was missing or invalid")
    return count


def parse_official_online_count(html: str) -> int:
    """Parse only the expected server-rendered official-site count phrase."""
    match = _ONLINE_COUNT_PATTERN.search(html)
    if match is None:
        raise ApiError("Official BlockFront website online count was not found")
    return int(match.group(1))


def parse_service_status(payload: object) -> dict[str, Any]:
    """Summarize API reachability and the freshness of upstream feeds."""
    if not isinstance(payload, dict) or not isinstance(payload.get("feeds"), list):
        raise ApiError("Blocklytics service status response has invalid feeds")

    feeds = payload["feeds"]
    if not feeds or any(not isinstance(feed, dict) for feed in feeds):
        raise ApiError("Blocklytics service status response has invalid feeds")

    affected = [
        feed
        for feed in feeds
        if feed.get("stale") is True
        or (isinstance(feed.get("consecutiveFailures"), int) and feed["consecutiveFailures"] > 0)
    ]
    errors = [
        str(feed["lastError"])
        for feed in affected
        if isinstance(feed.get("lastError"), str) and feed["lastError"]
    ]
    return {
        "status": "degraded" if affected else "online",
        "stale_feed_count": len(affected),
        "version": payload.get("version"),
        "uptime_seconds": payload.get("uptimeS"),
        "upstream_error": "; ".join(errors[:3]) or None,
    }
