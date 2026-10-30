"""Official response contracts, isolation and failure handling."""

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.blockfront.official import (
    OfficialApi,
    OfficialError,
    normalize_url,
    timestamp,
    values_for,
)


def session_for(status=200, payload=None, headers=None):
    response = MagicMock(status=status, headers=headers or {})
    response.json = AsyncMock(return_value=payload if payload is not None else {})
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get.return_value = context
    return session


async def test_public_request_never_sends_key_and_private_requires_it():
    session = session_for(payload={"playersOnline": 17})
    api = OfficialApi(session, api_key="test-only-secret")
    await api.get("player_count")
    assert session.get.call_args.kwargs["headers"] == {}
    assert session.get.call_args.kwargs["allow_redirects"] is False
    api.next_request = 0
    await api.get("player", uuid="player")
    assert session.get.call_args.kwargs["headers"]["X-API-Key"] == "test-only-secret"
    no_key = OfficialApi(session)
    session.get.reset_mock()
    with pytest.raises(OfficialError, match="key required"):
        await no_key.get("player")
    session.get.assert_not_called()


async def test_conditional_get_and_no_cross_query_cache():
    session = session_for(payload={"player": {}}, headers={"ETag": '"one"'})
    api = OfficialApi(session)
    first = await api.get("scoreboard", uuid="a")
    session.get.return_value.__aenter__.return_value.status = 304
    api.next_request = 0
    assert await api.get("scoreboard", uuid="a") == first
    assert session.get.call_args.kwargs["headers"] == {"If-None-Match": '"one"'}
    api.next_request = 0
    with pytest.raises(OfficialError, match="without cached"):
        await api.get("scoreboard", uuid="b")


@pytest.mark.parametrize("status", [429, 503])
async def test_retry_after_shared_across_endpoints(status):
    session = session_for(status=status, headers={"Retry-After": "45"})
    api = OfficialApi(session)
    with pytest.raises(OfficialError):
        await api.get("player_count")
    session.get.reset_mock()
    with pytest.raises(OfficialError, match="backoff"):
        await api.get("map_stats")
    session.get.assert_not_called()


@pytest.mark.parametrize("error", [aiohttp.ClientConnectionError(), TimeoutError(), ValueError()])
async def test_transport_errors_are_sanitized(error):
    session = session_for()
    session.get.return_value.__aenter__.side_effect = error
    with pytest.raises(OfficialError, match="Could not read"):
        await OfficialApi(session).get("player_count")


@pytest.mark.parametrize("value", [None, True, -1, "12", 1.5, float("nan")])
def test_online_invalid_is_not_zero(value):
    with pytest.raises(OfficialError):
        values_for("player_count", {"playersOnline": value})


def test_online_zero_is_valid_and_monthly_is_not_career():
    assert values_for("player_count", {"playersOnline": 0})[0]["online_players"] == 0
    values, _ = values_for("scoreboard", {"player": {"rank": 671, "score": 488}})
    assert values["monthly_score"] == 488
    assert "exp" not in values and "season_score" not in values
    assert values_for("scoreboard", {"player": None})[0]["monthly_score"] is None


def test_documented_matches_and_empty_sample():
    row = {
        "endedAt": 1793380001526,
        "result": "WIN",
        "score": 340,
        "durationSeconds": 1015,
        "mode": "dom",
        "map": "Storm",
        "kills": 24,
    }
    values, attrs = values_for("player_matches", {"matches": [row]})
    assert values["latest_match"] == "win"
    assert values["latest_match_duration"] == 1015
    assert values["latest_match_end"] == timestamp(row["endedAt"])
    assert attrs["kills"] == 24
    assert values_for("player_matches", {"matches": []})[0]["latest_match"] is None


def test_selected_map_scope_and_ratio_conversion():
    payload = {
        "maps": [
            {
                "map": "Storm",
                "modes": [
                    {
                        "mode": "dom",
                        "teams": {
                            "Allies": {"winRate": 0.355, "kills": 18787, "matches": 355},
                            "Axis": {"winRate": 0.658, "kills": 21967},
                        },
                    }
                ],
            }
        ]
    }
    values, _ = values_for("map_stats", payload, selected_map="Storm")
    assert values["map_win_rate"] == 35.5
    assert values["map_kills"] == 18787
    assert "kills" not in values
    assert values_for("map_stats", payload, selected_map="Missing")[0]["map_kills"] is None


def test_no_profile_key_guessing_or_hidden_player_data():
    values, _ = values_for(
        "player",
        {
            "rank": {"title": "Captain"},
            "stats": {"kills": 100, "new_stat": 7},
            "class_exp": {"0": 1500, "1": 320},
        },
    )
    assert values["rank"] == "Captain" and values["class_exp"] == 1820
    assert "exp" not in values
    assert (
        values_for("scoreboard", {"player": {"hidden": True, "score": 10}})[0]["monthly_score"]
        is None
    )


@pytest.mark.parametrize("url", ["ftp://host/", "https://a:b@host/", "https://host/?key=x"])
def test_url_rejects_credential_and_query(url):
    with pytest.raises(ValueError):
        normalize_url(url)


def test_map_ratings_include_zero_star_votes_and_selected_team():
    payload = {
        "maps": [
            {
                "map": "Storm",
                "modes": [
                    {
                        "mode": "dom",
                        "ratings": 120,
                        "average": 4.2,
                        "stars": {"0": 2, "5": 60},
                        "teams": {"Allies": {"ratings": 60, "average": 4.1, "stars": {"5": 28}}},
                    }
                ],
            }
        ]
    }
    values, attrs = values_for("map_ratings", payload, selected_map="Storm")
    assert values["map_ratings"] == 120
    assert values["map_stars_0"] == 2
    assert values["team_rating_count"] == 60
    assert values["team_rating_stars_5"] == 28
    assert attrs["selected_rating_team"] == "Allies"


def test_profile_ratios_derive_only_from_matching_totals_and_seconds_are_explicit():
    values, _ = values_for(
        "player", {"stats": {"kills": 10, "deaths": 5, "head_shots": 4, "time_played": 9000}}
    )
    assert values["kd"] == 2
    assert values["hs_kr"] == 0.4
    assert values["time_played"] is None
    values, _ = values_for("player", {"stats": {"timePlayedSeconds": 300}})
    assert values["time_played"] == 300
