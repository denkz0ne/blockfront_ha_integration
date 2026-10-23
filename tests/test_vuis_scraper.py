from __future__ import annotations

from typing import Any

import pytest

from custom_components.blockfront.api import ApiError
from custom_components.blockfront.vuis_scraper import VuisWebsite

PLAYER_UUID = "85c194ce-8ae5-4736-bf14-7e9bdd204c66"


class FakeResponse:
    def __init__(self, html: str, status: int = 200) -> None:
        self.status = status
        self._html = html

    async def text(self) -> str:
        return self._html

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None


class FakeSession:
    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []

    def get(self, url: str, **_: Any) -> FakeResponse:
        self.urls.append(url)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_player_stats_parse_rank_icons_personal_stats_and_uuid() -> None:
    session = FakeSession(
        FakeResponse(
            f"""
            <h2>Stats for player denkz0ne</h2>
            <img src="/avatar/{PLAYER_UUID}/head.png">
            <img src="/assets/bf_ranks/12.png">
            <img src="/assets/bf_skill_ranks/7.png">
            <div class="stat-block">
              Group: None<br>Rank: Captain<br>EXP Progress: 3,846 / 16,000<br>
              EXP Remaining: 12,154<br>Skill Rank: Iron Master<br>EXP: 72,847<br>
              Match Karma: 606<br>Time Played: 80.6h<br>Games: 228<br>
              K/D: 0.81<br>Headshots: 926<br>K/HS: 0.79<br>Kills: 1,178<br>
              Kill Streak: 12<br>Deaths: 1,455<br>Death Streak: 11<br>
              Captures: 20<br>Objective Score: 66<br>Wins: 41
            </div>
            """
        )
    )

    profile = await VuisWebsite(session).async_get_player("denkz0ne", PLAYER_UUID)

    assert profile["uuid"] == PLAYER_UUID
    assert profile["rank"] == "Captain"
    assert profile["rank_icon_id"] == 12
    assert profile["skill_rank"] == {"title": "Iron Master", "index": 7}
    assert profile["skill_rank_icon_id"] == 7
    assert profile["rank_exp_progress"] == 3846
    assert profile["rank_exp_required"] == 16000
    assert profile["rank_exp_remaining"] == 12154
    assert profile["time_played"] == 290160
    assert profile["kd"] == 0.81
    assert profile["highest_kill_streak"] == 12
    assert profile["highest_death_streak"] == 11
    assert profile["captures"] == 20
    assert profile["source"] == "vuis_website"
    assert session.urls == ["https://vuis.dev/bfstats/players/denkz0ne/stats"]


@pytest.mark.asyncio
async def test_recent_matches_parse_table_and_relative_end_time() -> None:
    session = FakeSession(
        FakeResponse(
            """
            <h2>Matches for player denkz0ne</h2>
            <table><tr><th>Game</th><th>Map</th><th>Result</th><th>Team</th>
            <th>Ended</th><th>Place</th><th>Kills</th><th>Deaths</th>
            <th>Assists</th><th>Score</th></tr>
            <tr><td>Domination</td><td>Palermo</td><td>Win</td><td>Axis</td>
            <td>2 hours ago</td><td>#6</td><td>10</td><td>7</td><td>2</td><td>40</td></tr>
            </table>
            """
        )
    )

    result = await VuisWebsite(session).async_get_match_data("denkz0ne")

    assert result["matches"] == [
        {
            "game": "Domination",
            "map": "Palermo",
            "result": "win",
            "player_team": "Axis",
            "ended_ago": "2 hours ago",
            "placement": 6,
            "kills": 10,
            "deaths": 7,
            "assists": 2,
            "score": 40,
            "source": "vuis_website",
        }
    ]
    assert result["source_timestamp"] is None


@pytest.mark.asyncio
async def test_player_stats_reject_page_for_different_player() -> None:
    session = FakeSession(FakeResponse("<h2>Stats for player anotheruser</h2>"))

    with pytest.raises(ApiError, match="different player"):
        await VuisWebsite(session).async_get_player("denkz0ne", PLAYER_UUID)
