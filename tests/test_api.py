from __future__ import annotations

from typing import Any

import pytest

from custom_components.blockfront.api import (
    API_BASE_URL,
    ApiError,
    BlockFrontApi,
    PlayerNotFound,
    async_fetch_online_data,
    parse_official_online_count,
    parse_online_count,
    parse_service_status,
)


class FakeResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        payload: object | None = None,
        text: str = "",
    ) -> None:
        self.status = status
        self._payload = payload
        self._text = text

    async def json(self, *, content_type: str | None = None) -> object:
        return self._payload

    async def text(self) -> str:
        return self._text

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None


class FakeRequest:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self._response = response

    async def __aenter__(self) -> FakeResponse:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    async def __aexit__(self, *_: Any) -> None:
        return None


class FakeSession:
    def __init__(self, *responses: FakeResponse | Exception) -> None:
        self._responses = list(responses)
        self.requests: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> FakeRequest:
        self.requests.append((url, kwargs))
        return FakeRequest(self._responses.pop(0))


class FakeOnlineApi:
    def __init__(self, overview: object | Exception, website_count: int | Exception) -> None:
        self.overview = overview
        self.website_count = website_count
        self.calls: list[str] = []

    async def async_get_overview(self) -> object:
        self.calls.append("overview")
        if isinstance(self.overview, Exception):
            raise self.overview
        return self.overview

    async def async_get_official_online_count(self) -> int:
        self.calls.append("website")
        if isinstance(self.website_count, Exception):
            raise self.website_count
        return self.website_count


@pytest.mark.asyncio
async def test_resolve_player_returns_uuid() -> None:
    username = "denkz0ne"
    player_uuid = "85c194ce-8ae5-4736-bf14-7e9bdd204c66"
    session = FakeSession(FakeResponse(payload={"name": username, "uuid": player_uuid}))
    assert await BlockFrontApi(session).async_resolve_player(username) == player_uuid
    assert session.requests[0][0] == f"{API_BASE_URL}resolve"
    assert session.requests[0][1]["params"] == {"name": username}


@pytest.mark.asyncio
async def test_resolve_player_missing_uuid_is_not_found() -> None:
    api = BlockFrontApi(FakeSession(FakeResponse(payload={"name": "unknown"})))
    with pytest.raises(PlayerNotFound):
        await api.async_resolve_player("unknown")


@pytest.mark.asyncio
async def test_api_timeout_is_reported_as_api_error() -> None:
    api = BlockFrontApi(FakeSession(TimeoutError()))
    with pytest.raises(ApiError, match="timed out"):
        await api.async_get_overview()


@pytest.mark.asyncio
async def test_profile_accepts_optional_missing_values() -> None:
    player_uuid = "85c194ce-8ae5-4736-bf14-7e9bdd204c66"
    api = BlockFrontApi(FakeSession(FakeResponse(payload={"kills": 12, "deaths": None})))
    profile = await api.async_get_player(player_uuid)
    assert profile == {"kills": 12, "deaths": None}


@pytest.mark.asyncio
async def test_matches_endpoint_requires_list_and_allows_empty_list() -> None:
    player_uuid = "85c194ce-8ae5-4736-bf14-7e9bdd204c66"
    api = BlockFrontApi(FakeSession(FakeResponse(payload={"matches": []})))
    assert await api.async_get_matches(player_uuid) == []

    api = BlockFrontApi(FakeSession(FakeResponse(payload={"matches": {}})))
    with pytest.raises(ApiError, match="matches"):
        await api.async_get_matches(player_uuid)


def test_online_count_accepts_expected_overview_shape() -> None:
    assert parse_online_count({"online": {"playersOnline": 96}}) == 96


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"online": {}},
        {"online": {"playersOnline": -1}},
        {"online": {"playersOnline": True}},
    ],
)
def test_online_count_rejects_invalid_values(payload: object) -> None:
    with pytest.raises(ApiError):
        parse_online_count(payload)


def test_official_online_count_parses_server_rendered_html() -> None:
    assert parse_official_online_count("<h2><p>79 Players Online Now!</p></h2>") == 79


@pytest.mark.parametrize("html", ["No player count", "-1 Players Online Now!", "999 Online"])
def test_official_online_count_rejects_unexpected_html(html: str) -> None:
    with pytest.raises(ApiError, match="online count"):
        parse_official_online_count(html)


@pytest.mark.asyncio
async def test_online_data_uses_api_without_fetching_official_page() -> None:
    api = FakeOnlineApi({"online": {"playersOnline": 96}, "generatedAt": 1234}, 79)
    data = await async_fetch_online_data(api)  # type: ignore[arg-type]
    assert data["online_count"] == 96
    assert data["source"] == "blocklytics"
    assert api.calls == ["overview"]


@pytest.mark.asyncio
async def test_online_data_falls_back_once_when_api_is_unusable() -> None:
    api = FakeOnlineApi({"online": {}}, 79)
    data = await async_fetch_online_data(api)  # type: ignore[arg-type]
    assert data["online_count"] == 79
    assert data["source"] == "official_website"
    assert api.calls == ["overview", "website"]


@pytest.mark.asyncio
async def test_online_data_reports_both_sources_failing() -> None:
    api = FakeOnlineApi(ApiError("API timeout"), ApiError("page unavailable"))
    with pytest.raises(ApiError, match="API and official website"):
        await async_fetch_online_data(api)  # type: ignore[arg-type]
    assert api.calls == ["overview", "website"]


def test_service_status_degrades_when_feed_is_stale_or_failing() -> None:
    status = parse_service_status(
        {
            "version": "1.2.3",
            "uptimeS": 420,
            "feeds": [
                {"feed": "overview", "stale": False, "consecutiveFailures": 0},
                {"feed": "matches", "stale": True, "consecutiveFailures": 3},
            ],
        }
    )
    assert status["status"] == "degraded"
    assert status["stale_feed_count"] == 1
    assert status["version"] == "1.2.3"


def test_service_status_rejects_malformed_feeds() -> None:
    with pytest.raises(ApiError, match="feeds"):
        parse_service_status({"feeds": "bad"})
