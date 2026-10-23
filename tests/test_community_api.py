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
