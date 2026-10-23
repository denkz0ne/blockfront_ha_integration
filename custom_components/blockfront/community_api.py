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
        if not isinstance(data.get("uuid"), str):
            raise ApiError("Community API returned an invalid player profile")
        kills = data.get("kills")
        deaths = data.get("deaths")
        headshots = data.get("head_shots")
        for name, value in (("kills", kills), ("deaths", deaths), ("head_shots", headshots)):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
            ):
                raise ApiError(f"Community API returned invalid {name} statistics")
        result = dict(data)
        result["kd"] = (
            round(kills / deaths, 2)
            if isinstance(kills, (int, float)) and isinstance(deaths, (int, float)) and deaths > 0
            else None
        )
        result["hs_kr"] = (
            round(headshots / kills, 3)
            if isinstance(headshots, (int, float)) and isinstance(kills, (int, float)) and kills > 0
            else None
        )
        result["source"] = "community_api"
        result["source_stale"] = None  # HTTP success does not reveal the upstream capture time.
        result["source_timestamp"] = None
        result["clan_uuid"] = data.get("clan")
        return result

    async def async_get_clan(self, uuid: str) -> dict[str, Any]:
        """Return validated details for the player's clan."""
        data = await self._fetch("clan_data", uuid)
        if not isinstance(data, dict) or not any(
            isinstance(data.get(key), str) and data[key]
            for key in ("uuid", "clan_id", "id", "name")
        ):
            raise ApiError("Community API returned invalid clan data")
        return data

    async def async_get_cloud_data(self) -> dict[str, Any]:
        """Fetch global online counts and scoreboard data."""
        data = await self._client._get_json(
            "cloud_data", base_url=self._base_url, service_name="Community API"
        )
        online = data.get("players_online")
        if isinstance(online, bool) or not isinstance(online, int) or online < 0:
            raise ApiError("Community API returned invalid online player count")
        mode_counts = data.get("game_player_count")
        if mode_counts is not None and (
            not isinstance(mode_counts, dict)
            or any(
                not isinstance(key, str)
                or isinstance(count, bool)
                or not isinstance(count, int)
                or count < 0
                for key, count in mode_counts.items()
            )
        ):
            raise ApiError("Community API returned invalid mode player counts")
        return data

    async def async_get_archive_data(self, uuid: str, profile: dict[str, Any]) -> dict[str, Any]:
        """Adapt profile class XP and inventory to the existing archive dataset."""
        try:
            data = await self._client._get_json(
                "player_inventory",
                params={"uuid": uuid, "include_details": "true"},
                base_url=self._base_url,
                service_name="Community API",
            )
            items = data.get("inventory")
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise ApiError("Community API returned invalid player inventory")
            inventory = {
                "items": items,
                "captured_at": None,
                "source_timestamp": None,
                "source_stale": None,
                "source": "community_api",
                "error": None,
            }
        except ApiError as err:
            inventory = {
                "items": None,
                "captured_at": None,
                "source_timestamp": None,
                "source_stale": True,
                "source": "community_api",
                "error": str(err),
            }
        class_exp = profile.get("class_exp")
        if class_exp is not None and (
            not isinstance(class_exp, list) or any(not isinstance(item, dict) for item in class_exp)
        ):
            raise ApiError("Community API returned invalid class XP")
        return {
            "classes": {
                "items": class_exp,
                "captured_at": None,
                "source_timestamp": None,
                "source_stale": None,
                "source": "community_api",
                "error": None,
            },
            "inventory": inventory,
            "source": "community_api",
            "source_stale": inventory["source_stale"],
        }

    async def async_get_match_data(self, uuid: str) -> dict[str, Any]:
        data = await self._fetch("player_matches", uuid)
        matches = data.get("matches")
        if not isinstance(matches, list) or any(not isinstance(row, dict) for row in matches):
            raise ApiError("Community API returned invalid match history")
        return {
            "matches": matches,
            "pagination": None,
            "source": "community_api",
            "source_stale": None,
            "source_timestamp": None,
        }
