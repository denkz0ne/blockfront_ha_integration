"""Tests for the optional community source adapter."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.blockfront.api import ApiError
from custom_components.blockfront.community_api import CommunityApi

TEST_BASE = "https://community.example.invalid/api/v1/"

UUID = "85c194ce-8ae5-4736-bf14-7e9bdd204c66"


@pytest.mark.asyncio
async def test_profile_maps_community_fields_to_existing_sensor_keys() -> None:
    client = AsyncMock()
    client._get_json.return_value = {
        "uuid": UUID, "username": "denkz0ne", "kills": 120,
        "deaths": 40, "head_shots": 30, "exp": 5000,
        "total_games": 9, "clan": None,
    }
    result = await CommunityApi(client, TEST_BASE).async_get_player(UUID)
    assert result["kd"] == 3
    assert result["hs_kr"] == 0.25
    assert result["exp"] == 5000
    assert result["source"] == "community_api"
    client._get_json.assert_awaited_once_with(
        "player_data", params={"uuid": UUID}, base_url=TEST_BASE,
        service_name="Community API",
    )


@pytest.mark.asyncio
async def test_matches_reuse_existing_shape() -> None:
    client = AsyncMock()
    match = {"match_id": "id-1", "kills": 15, "deaths": 4, "map": "Caen"}
    client._get_json.return_value = {"player": {"uuid": UUID}, "matches": [match]}
    result = await CommunityApi(client, TEST_BASE).async_get_match_data(UUID)
    assert result["matches"] == [match]
    assert result["source"] == "community_api"


@pytest.mark.asyncio
async def test_malformed_profile_is_not_accepted() -> None:
    client = AsyncMock()
    client._get_json.return_value = {"error": "unavailable"}
    with pytest.raises(ApiError):
        await CommunityApi(client, TEST_BASE).async_get_player(UUID)


@pytest.mark.asyncio
async def test_player_inventory_returns_existing_archive_shape() -> None:
    client = AsyncMock()
    inventory = [{"id": "item-1", "name": "Rifle", "type": "weapon"}]
    client._get_json.return_value = {"inventory": inventory, "player": {"uuid": UUID}}

    result = await CommunityApi(client, TEST_BASE).async_get_archive_data(
        UUID,
        {"class_exp": [{"id": 1, "exp": 1250}]},
    )

    assert result["inventory"]["items"] == inventory
    assert result["inventory"]["source"] == "community_api"
    assert result["classes"]["items"] == [{"id": 1, "exp": 1250}]
    client._get_json.assert_awaited_once_with(
        "player_inventory",
        params={"uuid": UUID, "include_details": "true"},
        base_url=TEST_BASE,
        service_name="Community API",
    )


@pytest.mark.asyncio
async def test_clan_and_cloud_endpoints_keep_their_payloads() -> None:
    client = AsyncMock()
    clan = {"uuid": "clan-uuid", "name": "Example"}
    client._get_json.side_effect = [
        clan,
        {"players_online": 12, "game_player_count": {"DOMINATION": 4}},
    ]
    api = CommunityApi(client, TEST_BASE)

    assert await api.async_get_clan("clan-uuid") == clan
    assert (await api.async_get_cloud_data())["players_online"] == 12
    assert client._get_json.await_count == 2


@pytest.mark.asyncio
async def test_inventory_missing_list_is_unknown_and_reports_error() -> None:
    client = AsyncMock()
    client._get_json.return_value = {"player": {"uuid": UUID}}

    result = await CommunityApi(client, TEST_BASE).async_get_archive_data(UUID, {})

    assert result["inventory"]["items"] is None
    assert result["inventory"]["source_stale"] is True
    assert "invalid player inventory" in result["inventory"]["error"]


@pytest.mark.asyncio
async def test_inventory_rate_limit_keeps_class_xp_and_reports_error() -> None:
    client = AsyncMock()
    client._get_json.side_effect = ApiError("rate limited", status_code=429)

    result = await CommunityApi(client, TEST_BASE).async_get_archive_data(
        UUID, {"class_exp": [{"id": 2, "exp": 200}]}
    )

    assert result["classes"]["items"] == [{"id": 2, "exp": 200}]
    assert result["inventory"]["items"] is None
    assert result["source_stale"] is True


@pytest.mark.asyncio
async def test_boolean_is_not_accepted_as_integer_profile_statistic() -> None:
    client = AsyncMock()
    client._get_json.return_value = {"uuid": UUID, "kills": True, "deaths": 0}

    with pytest.raises(ApiError):
        await CommunityApi(client, TEST_BASE).async_get_player(UUID)
