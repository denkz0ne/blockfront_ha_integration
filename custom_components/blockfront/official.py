"""Official API v2 transport and validated, scope-preserving values."""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import monotonic
from urllib.parse import urlsplit

import aiohttp

DEFAULT_URL = "https://api.blockfrontmc.com/api/v2/"
PUBLIC = {"player_count": 60, "scoreboard": 300, "map_stats": 900, "map_ratings": 3600}
PRIVATE = {"player": 900, "player_matches": 900, "clan": 1800, "match": 900}


class OfficialError(Exception):
    """A sanitized API failure, safe for HA diagnostics."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def normalize_url(value):
    """Accept only a credential-free HTTP(S) base URL."""
    value = value.strip()
    parts = urlsplit(value)
    try:
        _ = parts.port
    except ValueError as err:
        raise ValueError("Invalid API URL") from err
    if (
        parts.scheme not in {"https", "http"}
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or any(c.isspace() for c in value)
    ):
        raise ValueError("Invalid API URL")
    return value.rstrip("/") + "/"


def number(value):
    """Reject bools, non-numeric strings and non-finite values."""
    return value if type(value) in (int, float) and math.isfinite(value) else None


def timestamp(value):
    """Official timestamps are Unix milliseconds, not seconds."""
    if number(value) is None:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, UTC)
    except (ValueError, OverflowError, OSError):
        return None


class OfficialApi:
    """One bounded transport shared by all endpoint coordinators."""

    def __init__(self, session, base_url=DEFAULT_URL, api_key=""):
        self.session = session
        self.base_url = normalize_url(base_url)
        self.api_key = api_key
        self.cache = {}
        self.lock = asyncio.Lock()
        self.next_request = 0.0
        self.backoff_until = 0.0
        self.failures = 0

    async def get(self, endpoint, **params):
        """No redirects, no credential forwarding, conditional GET and shared backoff."""
        if endpoint not in PUBLIC and endpoint not in PRIVATE:
            raise OfficialError("Unsupported endpoint")
        if endpoint in PRIVATE and not self.api_key:
            raise OfficialError("API key required", 401)
        cache_key = (endpoint, tuple(sorted(params.items())))
        async with self.lock:
            now = monotonic()
            if now < self.backoff_until:
                raise OfficialError("Official API is in backoff")
            await asyncio.sleep(max(0, self.next_request - now))
            self.next_request = monotonic() + 0.3
            headers = {}
            if endpoint in PRIVATE:
                headers["X-API-Key"] = self.api_key
            cached = self.cache.get(cache_key)
            if cached and cached[0]:
                headers["If-None-Match"] = cached[0]
            try:
                async with self.session.get(
                    self.base_url,
                    params={"type": endpoint, **params},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                    allow_redirects=False,
                ) as response:
                    status = response.status
                    if status == 304:
                        if cached is None:
                            raise OfficialError("304 without cached data", status)
                        return cached[1]
                    if status in (429, 503):
                        self.failures += 1
                        retry = response.headers.get("Retry-After", "")
                        try:
                            seconds = max(0, float(retry))
                        except ValueError:
                            try:
                                seconds = max(
                                    0,
                                    (
                                        parsedate_to_datetime(retry) - datetime.now(UTC)
                                    ).total_seconds(),
                                )
                            except (TypeError, ValueError, OverflowError):
                                seconds = min(3600, 30 * 2 ** min(self.failures, 7))
                        if not math.isfinite(seconds):
                            seconds = 3600
                        self.backoff_until = monotonic() + max(1, seconds)
                        raise OfficialError(f"Official API returned HTTP {status}", status)
                    if status != 200:
                        if status in (401, 403):
                            self.cache.pop(cache_key, None)
                        raise OfficialError(f"Official API returned HTTP {status}", status)
                    payload = await response.json()
                    if not isinstance(payload, dict) or "error" in payload:
                        raise OfficialError("Invalid official API response")
                    self.cache[cache_key] = (response.headers.get("ETag"), payload)
                    self.failures = 0
                    return payload
            except (TimeoutError, aiohttp.ClientError, ValueError) as from_error:
                raise OfficialError("Could not read official API response") from from_error


def values_for(endpoint, payload, *, selected_map="", mode="dom", team="Allies"):
    """Normalize documented envelopes without mixing personal and world statistics."""
    values = {}
    attrs = {"source": "official_api", "generated_at": timestamp(payload.get("generatedAt"))}
    if endpoint == "player_count":
        value = number(payload.get("playersOnline"))
        if value is None or value < 0 or int(value) != value:
            raise OfficialError("Invalid online player count")
        values["online_players"] = int(value)
    elif endpoint == "scoreboard":
        player = payload.get("player")
        if player is not None and not isinstance(player, dict):
            raise OfficialError("Invalid player standing")
        player = player or {}
        if player.get("hidden"):
            player = {}
        values.update(
            monthly_score=number(player.get("score")),
            monthly_rank=number(player.get("rank")),
            monthly_reset=timestamp(payload.get("resetTime")),
        )
    elif endpoint == "player":
        stats = payload.get("stats")
        if not isinstance(stats, dict):
            raise OfficialError("Invalid player statistics")
        values.update({k: number(v) for k, v in stats.items() if isinstance(k, str)})
        values["bootcamp"] = (
            stats.get("bootcamp") if isinstance(stats.get("bootcamp"), bool) else None
        )
        for key, value in stats.items():
            if isinstance(key, str) and (number(value) is not None or isinstance(value, str)):
                values[f"official_stat_{key}"] = (
                    value if not isinstance(value, str) or len(value) <= 255 else None
                )
        # A bare time_played field has no documented unit. Never mix it into seconds.
        values["time_played"] = number(stats.get("timePlayedSeconds"))
        for ratio, numerator, denominator in (
            ("kd", "kills", "deaths"),
            ("hs_kr", "head_shots", "kills"),
        ):
            a, b = number(stats.get(numerator)), number(stats.get(denominator))
            if values.get(ratio) is None and a is not None and b is not None and b > 0:
                values[ratio] = a / b
        rank = payload.get("rank")
        values["rank"] = rank.get("title") if isinstance(rank, dict) else None
        clan = payload.get("clan")
        values["clan"] = clan.get("name") if isinstance(clan, dict) else None
        classes = payload.get("class_exp")
        if isinstance(classes, dict) and all(number(v) is not None for v in classes.values()):
            values["class_exp"] = sum(classes.values())
            attrs["class_exp"] = classes
            for class_id in range(10):
                values[f"class_exp_{class_id}"] = number(classes.get(str(class_id)))
        skill = stats.get("skill_rank")
        values["skill_rank"] = skill.get("title") if isinstance(skill, dict) else None
    elif endpoint == "player_matches":
        rows = payload.get("matches")
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise OfficialError("Invalid match list")
        rows = [r for r in rows if not r.get("hidden")]
        latest = max(rows, key=lambda r: number(r.get("endedAt")) or 0) if rows else {}
        result = latest.get("result")
        values.update(
            latest_match=result.lower() if isinstance(result, str) else None,
            latest_match_score=number(latest.get("score")),
            latest_match_duration=number(latest.get("durationSeconds")),
            latest_match_end=timestamp(latest.get("endedAt")),
        )
        attrs.update(
            {
                k: latest.get(k)
                for k in ("map", "mode", "environment", "team", "winnerTeam", "placement")
            }
        )
        attrs.update({k: number(latest.get(k)) for k in ("kills", "deaths", "assists", "score")})
        attrs.update(
            game=latest.get("mode"),
            player_team=latest.get("team"),
            winner_team=latest.get("winnerTeam"),
            ended_at=timestamp(latest.get("endedAt")),
            duration_seconds=number(latest.get("durationSeconds")),
            sample_size=len(rows),
        )
    elif endpoint in {"map_stats", "map_ratings"}:
        maps = payload.get("maps")
        if not isinstance(maps, list) or any(not isinstance(m, dict) for m in maps):
            raise OfficialError("Invalid map list")
        values["official_map_count"] = len(maps)
        row = next((m for m in maps if m.get("map") == selected_map), {})
        modes = row.get("modes", [])
        if not isinstance(modes, list):
            raise OfficialError("Invalid map modes")
        row = next((m for m in modes if isinstance(m, dict) and m.get("mode") == mode), {})
        teams = row.get("teams", {})
        if not isinstance(teams, dict):
            raise OfficialError("Invalid map teams")
        data = teams.get(team, {}) if endpoint == "map_stats" else row
        if not isinstance(data, dict):
            raise OfficialError("Invalid map statistics")
        for key in ("matches", "wins", "kills", "deaths", "kd", "score", "ratings", "average"):
            values[f"map_{key}"] = number(data.get(key))
        rate = number(data.get("winRate"))
        values["map_win_rate"] = rate * 100 if rate is not None else None
        stars = data.get("stars", {})
        for star in range(6):
            values[f"map_stars_{star}"] = (
                number(stars.get(str(star))) if isinstance(stars, dict) else None
            )
        attrs.update(
            map=selected_map or None, mode=mode, team=team if endpoint == "map_stats" else None
        )
        if endpoint == "map_ratings":
            rating_team = teams.get(team, {})
            if not isinstance(rating_team, dict):
                raise OfficialError("Invalid team ratings")
            values["team_rating_count"] = number(rating_team.get("ratings"))
            values["team_rating_average"] = number(rating_team.get("average"))
            team_stars = rating_team.get("stars", {})
            for star in range(6):
                values[f"team_rating_stars_{star}"] = (
                    number(team_stars.get(str(star))) if isinstance(team_stars, dict) else None
                )
            attrs["selected_rating_team"] = team
    elif endpoint == "clan":
        values.update(
            brigade_members=number(payload.get("memberCount")),
            brigade_founded=timestamp(payload.get("founded")),
        )
        score = payload.get("score")
        if isinstance(score, dict):
            values["brigade_monthly_score"] = number(score.get("monthly"))
            values["brigade_monthly_rank"] = number(score.get("rank"))
        attrs.update(tag=payload.get("tag"), name=payload.get("name"))
    elif endpoint == "match":
        values.update(
            {
                f"match_{k}": number(payload.get(k))
                for k in ("axisScore", "alliedScore", "axisCasualties", "alliedCasualties")
            }
        )
    return values, attrs
