"""Optional adapter for the public Community API (not the Blocklytics API)."""

from __future__ import annotations

from typing import Any

from .api import ApiError, BlockFrontApi, normalize_api_base_url


class CommunityApi:
    """Normalize Community API results into existing coordinator sensor keys."""

    def __init__(self, client: BlockFrontApi, base_url: str) -> None:
        self._client = client
        self._base_url = normalize_api_base_url(base_url)

    async def _fetch(self, endpoint: str, uuid: str) -> dict[str, Any]:
        # This origin has its own scheduler scope and never receives the other
        # provider's Bearer credentials.
        return await self._client._get_json(
            endpoint,
            params={"uuid": uuid},
            base_url=self._base_url,
            service_name="Community API",
        )

    async def async_get_player(self, uuid: str) -> dict[str, Any]:
        data = await self._fetch("player_data", uuid)
        if not isinstance(data.get("uuid"), str) or not isinstance(data.get("kills"), int):
            raise ApiError("Community API returned an invalid player profile")
        kills = data.get("kills")
        deaths = data.get("deaths")
        headshots = data.get("head_shots")
        if not isinstance(deaths, int) or isinstance(deaths, bool):
            raise ApiError("Community API returned invalid death statistics")
        result = dict(data)
        result["kd"] = round(kills / deaths, 2) if deaths > 0 else float(kills)
        result["hs_kr"] = round(headshots / kills, 3) if isinstance(headshots, int) and kills > 0 else None
        result["source"] = "community_api"
        result["source_stale"] = False  # HTTP returned data; upstream timestamp is not exposed.
        result["source_timestamp"] = None
        result["clan_uuid"] = data.get("clan")
        return result

    async def async_get_match_data(self, uuid: str) -> dict[str, Any]:
        data = await self._fetch("player_matches", uuid)
        matches = data.get("matches")
        if not isinstance(matches, list) or any(not isinstance(row, dict) for row in matches):
            raise ApiError("Community API returned invalid match history")
        return {
            "matches": matches,
            "pagination": None,
            "source": "community_api",
            "source_stale": False,
            "source_timestamp": None,
        }
