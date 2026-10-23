"""Scrape player profile and recent matches from the public Vuis stats pages."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote

import aiohttp

from .api import ApiError

_BASE_URL = "https://vuis.dev/bfstats/players/"
_NUMBER = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")
_AVATAR_UUID = re.compile(r"/avatar/([0-9a-f-]{36})/", re.IGNORECASE)
_RANK_ICON = re.compile(r"/assets/bf_ranks/(\d+)\.png$")
_SKILL_ICON = re.compile(r"/assets/bf_skill_ranks/(\d+)\.png$")

_PROFILE_LABELS = {
    "exp": "exp",
    "match karma": "match_karma",
    "games": "total_games",
    "k/d": "kd",
    "headshots": "head_shots",
    "k/hs": "hs_kr",
    "kills": "kills",
    "kill streak": "highest_kill_streak",
    "fire kills": "fire_kills",
    "back-stabs": "back_stabs",
    "assists": "assists",
    "heal assists": "heal_assists",
    "no-scopes": "no_scopes",
    "deaths": "deaths",
    "death streak": "highest_death_streak",
    "first-bloods": "first_bloods",
    "wins": "wins",
    "prestige level": "prestige",
    "completed bootcamp": "bootcamp",
    "captures": "captures",
    "objective score": "objective_score",
    "infected rounds won": "infected_rounds_won",
    "infected matches won": "infected_matches_won",
    "bot kills": "bot_kills",
    "infected kills": "infected_kills",
    "vehicle kills": "vehicle_kills",
}


class _PageParser(HTMLParser):
    """Collect semantic stat blocks, table cells, headings, and image paths."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.rows: list[list[str]] = []
        self.images: list[str] = []
        self.heading = ""
        self._block_depth = 0
        self._block: list[str] = []
        self._heading = False
        self._heading_parts: list[str] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if (
            tag == "div"
            and self._block_depth == 0
            and "stat-block" in values.get("class", "").split()
        ):
            self._block_depth = 1
            self._block = []
        elif tag == "div" and self._block_depth:
            self._block_depth += 1
        elif tag == "br" and self._block_depth:
            self._block.append("\n")

        if tag == "h2":
            self._heading = True
            self._heading_parts = []
        elif tag == "img":
            src = values.get("src")
            if src:
                self.images.append(src)
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._block_depth:
            self._block_depth -= 1
            if self._block_depth:
                self._block.append("\n")
            else:
                self.blocks.append("".join(self._block))
                self._block = []
        elif tag == "h2" and self._heading:
            self.heading = " ".join("".join(self._heading_parts).split())
            self._heading = False
        elif tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._block_depth:
            self._block.append(data)
        if self._heading:
            self._heading_parts.append(data)
        if self._cell is not None:
            self._cell.append(data)


class VuisWebsite:
    """Fetch server-rendered Vuis pages and normalize them for HA entities."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _fetch(self, username: str, tab: str) -> _PageParser:
        safe_name = quote(username, safe="")
        url = f"{_BASE_URL}{safe_name}/{tab}"
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as response:
                if response.status == 404:
                    raise ApiError("Vuis player page was not found", status_code=404)
                if response.status >= 400:
                    raise ApiError(
                        f"Vuis stats page returned HTTP {response.status}",
                        status_code=response.status,
                    )
                html = await response.text()
        except ApiError:
            raise
        except (TimeoutError, aiohttp.ClientError) as err:
            raise ApiError(f"Vuis stats page request failed: {err.__class__.__name__}") from err

        parser = _PageParser()
        parser.feed(html)
        if not parser.heading.startswith("Stats for player ") and not parser.heading.startswith(
            "Matches for player "
        ):
            raise ApiError("Vuis stats page did not contain the expected player data")
        displayed_name = parser.heading.split("player ", 1)[-1].strip()
        if displayed_name.casefold() != username.casefold():
            raise ApiError("Vuis stats page returned a different player")
        return parser

    async def async_get_player(self, username: str, player_uuid: str) -> dict[str, Any]:
        """Parse personal stats while preserving the integration's stable keys."""
        page = await self._fetch(username, "stats")
        profile: dict[str, Any] = {
            "uuid": player_uuid,
            "username": username,
            "source": "vuis_website",
            "source_timestamp": None,
            "source_stale": None,
            "rank": None,
            "skill_rank": None,
            "time_played": None,
            "rank_exp_progress": None,
            "rank_exp_required": None,
            "rank_exp_remaining": None,
            "bootcamp": None,
            "clan": None,
            "clan_uuid": None,
        }

        for src in page.images:
            if match := _AVATAR_UUID.search(src):
                profile["uuid"] = match.group(1)
            elif match := _RANK_ICON.search(src):
                profile["rank_icon_id"] = int(match.group(1))
            elif match := _SKILL_ICON.search(src):
                profile["skill_rank_icon_id"] = int(match.group(1))

        for block in page.blocks:
            for line in block.splitlines():
                if ":" not in line:
                    continue
                label, raw_value = (part.strip() for part in line.split(":", 1))
                normalized_label = label.casefold()
                if normalized_label == "rank":
                    profile["rank"] = raw_value
                elif normalized_label == "skill rank":
                    profile["skill_rank"] = raw_value
                elif normalized_label == "exp progress":
                    values = re.fullmatch(r"([\d,]+)\s*/\s*([\d,]+)", raw_value)
                    if values:
                        profile["rank_exp_progress"] = int(values.group(1).replace(",", ""))
                        profile["rank_exp_required"] = int(values.group(2).replace(",", ""))
                elif normalized_label == "exp remaining":
                    profile["rank_exp_remaining"] = _parse_value(raw_value)
                elif normalized_label == "time played":
                    profile["time_played"] = _parse_duration(raw_value)
                elif normalized_label in _PROFILE_LABELS:
                    value = _parse_value(raw_value)
                    if value is not None:
                        profile[_PROFILE_LABELS[normalized_label]] = value

        if not isinstance(profile.get("exp"), int) or not isinstance(profile.get("kills"), int):
            raise ApiError("Vuis player page did not contain required profile statistics")
        if isinstance(profile.get("skill_rank"), str):
            profile["skill_rank"] = {
                "title": profile["skill_rank"],
                "index": profile.get("skill_rank_icon_id"),
            }
        kills = profile.get("kills")
        deaths = profile.get("deaths")
        if (
            profile.get("kd") is None
            and isinstance(kills, int)
            and isinstance(deaths, int)
            and deaths
        ):
            profile["kd"] = round(kills / deaths, 2)
        headshots = profile.get("head_shots")
        if (
            profile.get("hs_kr") is None
            and isinstance(headshots, int)
            and isinstance(kills, int)
            and kills
        ):
            profile["hs_kr"] = round(headshots / kills, 3)
        return profile

    async def async_get_match_data(self, username: str) -> dict[str, Any]:
        """Parse the recent-match table; Vuis currently reports relative dates."""
        page = await self._fetch(username, "matches")
        if not page.rows:
            raise ApiError("Vuis matches page did not contain a match table")
        headers = [item.casefold() for item in page.rows[0]]
        key_map = {
            "game": "game",
            "map": "map",
            "result": "result",
            "team": "player_team",
            "ended": "ended_ago",
            "place": "placement",
            "kills": "kills",
            "deaths": "deaths",
            "assists": "assists",
            "score": "score",
        }
        matches = []
        for row in page.rows[1:]:
            if len(row) != len(headers):
                continue
            match = {
                key_map[header]: value
                for header, value in zip(headers, row, strict=True)
                if header in key_map and value
            }
            for key in ("placement", "kills", "deaths", "assists", "score"):
                if key in match:
                    raw_value = (
                        str(match[key]).lstrip("#") if key == "placement" else str(match[key])
                    )
                    match[key] = _parse_value(raw_value)
            match["result"] = str(match.get("result", "")).casefold() or None
            match["source"] = "vuis_website"
            matches.append(match)
        if not matches:
            raise ApiError("Vuis matches page did not contain any readable matches")
        return {
            "matches": matches,
            "pagination": None,
            "source": "vuis_website",
            "source_stale": None,
            "source_timestamp": None,
        }


def _parse_value(raw_value: str) -> int | float | str | None:
    value = " ".join(raw_value.split())
    if value.casefold() in {"yes", "true"}:
        return True
    if value.casefold() in {"no", "false"}:
        return False
    normalized = value.replace(",", "")
    if _NUMBER.fullmatch(normalized):
        number = float(normalized) if "." in normalized else int(normalized)
        return number
    return value or None


def _parse_duration(value: str) -> int | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smhd])\s*", value, re.IGNORECASE)
    if not match:
        return None
    amount = float(match.group(1))
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2).casefold()]
    return round(amount * multiplier)
