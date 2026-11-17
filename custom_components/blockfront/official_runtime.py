"""Vuis and optional official API coordinators plus the entity catalog."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .official import DEFAULT_URL, OfficialApi, OfficialError, number, values_for
from .vuis import (
    VuisClient,
    VuisError,
    parse_brigade,
    parse_brigade_scoreboard,
    parse_match_detail,
    parse_matches,
    parse_profile,
    validate_username,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_INTERVALS = {
    "vuis_profile": 900,
    "vuis_matches": 900,
    "vuis_brigade": 1800,
}


class VuisCoordinator(DataUpdateCoordinator):
    """Poll one Vuis data family; the optional official API fills missing fields."""

    def __init__(self, hass, entry, endpoint, client, official_api, runtime):
        self.entry = entry
        self.endpoint = endpoint
        self.client = client
        self.official_api = official_api
        self.runtime = runtime
        interval = entry.options.get(f"{endpoint}_interval", DEFAULT_INTERVALS[endpoint])
        super().__init__(
            hass,
            LOGGER,
            name=f"BlockFront {endpoint}",
            config_entry=entry,
            update_interval=timedelta(seconds=interval),
        )

    async def _async_update_data(self):
        try:
            if self.endpoint == "vuis_profile":
                values, attrs = await self._profile()
            elif self.endpoint == "vuis_matches":
                values, attrs = await self._matches()
            else:
                values, attrs = await self._brigade()
        except VuisError as err:
            fallback = await self._official_fallback()
            if fallback is None:
                raise UpdateFailed(str(err)) from err
            values, attrs = fallback
            attrs["vuis_error"] = str(err)
            attrs["source"] = "official_api_fallback"
        attrs["endpoint"] = self.endpoint
        attrs["last_successful_update"] = datetime.now(UTC).isoformat()
        return {"values": values, "attributes": attrs}

    async def _profile(self):
        username = validate_username(self.entry.data["username"])
        path = f"players/{quote(username, safe='')}/stats"
        source = await self.client.get(path)
        values, attrs = parse_profile(source, self.entry.data["player_uuid"])
        attrs.pop("player_uuid", None)
        attrs["profile_url"] = f"https://vuis.dev/bfstats/{path}"
        await self._enrich_profile(values, attrs)
        return values, attrs

    async def _matches(self):
        username = validate_username(self.entry.data["username"])
        path = f"players/{quote(username, safe='')}/matches"
        source = await self.client.get(path)
        values, attrs, match_id = parse_matches(source, username)
        if match_id:
            try:
                detail = await self.client.get(f"match/{match_id}")
                values.update(parse_match_detail(detail))
                attrs["match_detail_url"] = f"https://vuis.dev/bfstats/match/{match_id}"
            except VuisError as err:
                attrs["match_detail_error"] = str(err)
        await self._enrich_match(values, attrs)
        attrs["matches_url"] = f"https://vuis.dev/bfstats/{path}"
        return values, attrs

    async def _brigade(self):
        profile = self.runtime.get("vuis_profile")
        if profile is None:
            raise VuisError("The Vuis profile coordinator is unavailable")
        if profile.data is None:
            await profile.async_request_refresh()
        tag = ((profile.data or {}).get("values") or {}).get("brigade_tag")
        if not tag:
            return {}, {"source": "vuis.dev", "brigade_tag": None}

        results = await asyncio.gather(
            self.client.get(f"brigades/{quote(tag, safe='')}"),
            self.client.get("scoreboards/brigades"),
            return_exceptions=True,
        )
        values = {}
        errors = []
        if isinstance(results[0], str):
            values.update(parse_brigade(results[0], tag, self.entry.data["username"]))
        else:
            errors.append(results[0])
        if isinstance(results[1], str):
            values.update(parse_brigade_scoreboard(results[1], tag))
        else:
            errors.append(results[1])
        attrs = {"source": "vuis.dev", "brigade_tag": tag}
        await self._enrich_brigade(values, attrs, tag)
        if not values and errors:
            first = errors[0]
            if isinstance(first, VuisError):
                raise first
            raise VuisError("Could not read Vuis brigade statistics") from first
        attrs.update(
            {
                "brigade_url": f"https://vuis.dev/bfstats/brigades/{quote(tag, safe='')}",
                "scoreboard_url": "https://vuis.dev/bfstats/scoreboards/brigades",
                "partial_errors": [str(err) for err in errors],
            }
        )
        return values, attrs

    async def _enrich_brigade(self, values, attrs, tag):
        if not self.official_api.api_key or all(
            values.get(key) is not None for key in ("brigade_name", "brigade_member_count")
        ):
            return
        try:
            payload = await self.official_api.get("clan", tag=tag)
            official, official_attrs = values_for("clan", payload)
        except OfficialError as err:
            attrs["official_api_error"] = str(err)
            return
        if values.get("brigade_name") is None:
            values["brigade_name"] = official_attrs.get("name")
        if values.get("brigade_member_count") is None:
            values["brigade_member_count"] = official.get("brigade_members")
        if values.get("brigade_name") is not None or values.get("brigade_member_count") is not None:
            attrs["fallback_source"] = "official_api"

    async def _enrich_profile(self, values, attrs):
        if not self.official_api.api_key:
            return
        field_map = {
            "kills": "kills",
            "deaths": "deaths",
            "kd_ratio": "kd",
            "head_shots": "head_shots",
            "first_bloods": "first_bloods",
            "no_scopes": "no_scopes",
            "total_games": "total_games",
            "time_played": "time_played",
            "rank": "rank",
            "prestige": "prestige",
            "assists": "assists",
            "wins": "wins",
            "back_stabs": "back_stabs",
            "bot_kills": "bot_kills",
            "exp": "exp",
            "fire_kills": "fire_kills",
            "heal_assists": "heal_assists",
            "infected_kills": "infected_kills",
            "infected_matches_won": "infected_matches_won",
            "infected_rounds_won": "infected_rounds_won",
            "match_karma": "match_karma",
            "objective_score": "objective_score",
            "vehicle_kills": "vehicle_kills",
            "skill_rank": "skill_rank",
            "bootcamp": "bootcamp",
        }
        if not any(values.get(key) is None for key in field_map):
            return
        try:
            payload = await self.official_api.get(
                "player", uuid=self.entry.data["player_uuid"]
            )
            official, _ = values_for("player", payload)
        except OfficialError as err:
            attrs["official_api_error"] = str(err)
            return
        sources = {}
        for key, official_key in field_map.items():
            if values.get(key) is None and official.get(official_key) is not None:
                values[key] = official[official_key]
                sources[key] = "official_api"
        games, wins = values.get("total_games"), values.get("wins")
        if values.get("win_rate") is None and games and wins is not None:
            values["win_rate"] = 100 * wins / games
            sources["win_rate"] = "calculated_from_official_api"
        if sources:
            attrs["fallback_sources"] = sources

    async def _enrich_match(self, values, attrs):
        if not self.official_api.api_key:
            return
        if any(
            values.get(key) is None
            for key in (
                "latest_match",
                "latest_match_score",
                "latest_match_end",
                "latest_match_kills",
                "latest_match_deaths",
                "latest_match_assists",
                "latest_match_mode",
                "latest_match_team",
                "latest_match_map",
            )
        ):
            try:
                payload = await self.official_api.get(
                    "player_matches", uuid=self.entry.data["player_uuid"]
                )
                official, official_attrs = values_for("player_matches", payload)
            except OfficialError as err:
                attrs["official_api_error"] = str(err)
            else:
                mapped = {
                    "latest_match": official.get("latest_match"),
                    "latest_match_score": official.get("latest_match_score"),
                    "latest_match_end": official.get("latest_match_end"),
                    "latest_match_kills": official_attrs.get("kills"),
                    "latest_match_deaths": official_attrs.get("deaths"),
                    "latest_match_assists": official_attrs.get("assists"),
                    "latest_match_placement": official_attrs.get("placement"),
                    "latest_match_mode": official_attrs.get("game"),
                    "latest_match_team": official_attrs.get("player_team"),
                    "latest_match_map": official_attrs.get("map"),
                }
                sources = {}
                for key, value in mapped.items():
                    if values.get(key) is None and value is not None:
                        values[key] = value
                        sources[key] = "official_api"
                if sources:
                    attrs["fallback_sources"] = sources

        match_id = attrs.get("latest_match_id")
        if not match_id or all(
            values.get(key) is not None
            for key in ("latest_match_allies_score", "latest_match_axis_score")
        ):
            return
        try:
            payload = await self.official_api.get("match", id=match_id)
            official, _ = values_for("match", payload)
        except OfficialError as err:
            attrs["official_match_error"] = str(err)
            return
        scores = {}
        for key, official_key in (
            ("latest_match_allies_score", "match_alliedScore"),
            ("latest_match_axis_score", "match_axisScore"),
        ):
            if values.get(key) is None and official.get(official_key) is not None:
                values[key] = official[official_key]
                scores[key] = "official_api"
        if scores:
            attrs.setdefault("fallback_sources", {}).update(scores)

    async def _official_fallback(self):
        if not self.official_api.api_key:
            return None
        endpoint = "player" if self.endpoint == "vuis_profile" else "player_matches"
        if self.endpoint == "vuis_brigade":
            return None
        try:
            payload = await self.official_api.get(
                endpoint, uuid=self.entry.data["player_uuid"]
            )
            values, attrs = values_for(endpoint, payload)
        except OfficialError:
            return None
        if endpoint == "player":
            field_map = {
                "kills": "kills",
                "deaths": "deaths",
                "kd_ratio": "kd",
                "head_shots": "head_shots",
                "first_bloods": "first_bloods",
                "no_scopes": "no_scopes",
                "total_games": "total_games",
                "time_played": "time_played",
                "rank": "rank",
                "prestige": "prestige",
                "assists": "assists",
                "wins": "wins",
                "back_stabs": "back_stabs",
                "bot_kills": "bot_kills",
                "exp": "exp",
                "fire_kills": "fire_kills",
                "heal_assists": "heal_assists",
                "kill_streak": "kill_streak",
                "death_streak": "death_streak",
                "infected_kills": "infected_kills",
                "infected_matches_won": "infected_matches_won",
                "infected_rounds_won": "infected_rounds_won",
                "match_karma": "match_karma",
                "objective_score": "objective_score",
                "vehicle_kills": "vehicle_kills",
                "skill_rank": "skill_rank",
                "bootcamp": "bootcamp",
            }
            profile_values = {
                key: values.get(official_key)
                for key, official_key in field_map.items()
                if values.get(official_key) is not None
            }
            games, wins = profile_values.get("total_games"), profile_values.get("wins")
            if games and wins is not None:
                profile_values["win_rate"] = 100 * wins / games
            enabled = self.entry.options.get("enabled_metrics")
            if enabled is not None:
                profile_values = {
                    key: value for key, value in profile_values.items() if key in enabled
                }
            return profile_values, {
                "source": attrs.get("source", "official_api"),
                "generated_at": attrs.get("generated_at"),
                "fallback_sources": {key: "official_api" for key in profile_values},
            }
        values.update(
            {
                "latest_match_kills": attrs.get("kills"),
                "latest_match_deaths": attrs.get("deaths"),
                "latest_match_assists": attrs.get("assists"),
                "latest_match_placement": attrs.get("placement"),
                "latest_match_mode": attrs.get("game"),
                "latest_match_team": attrs.get("player_team"),
                "latest_match_map": attrs.get("map"),
            }
        )
        matches = payload.get("matches", [])
        latest = max(
            (row for row in matches if isinstance(row, dict)),
            key=lambda row: number(row.get("endedAt")) or 0,
            default={},
        )
        match_id = latest.get("matchId")
        if isinstance(match_id, str):
            match_uuid = re.fullmatch(
                r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                match_id,
            )
            if match_uuid:
                attrs["latest_match_id"] = match_uuid.group(0).lower()
                try:
                    match_payload = await self.official_api.get(
                        "match", id=attrs["latest_match_id"]
                    )
                    match_values, _ = values_for("match", match_payload)
                except OfficialError:
                    match_values = {}
                values["latest_match_allies_score"] = match_values.get("match_alliedScore")
                values["latest_match_axis_score"] = match_values.get("match_axisScore")
        safe_keys = {
            "latest_match",
            "latest_match_score",
            "latest_match_end",
            "latest_match_kills",
            "latest_match_deaths",
            "latest_match_assists",
            "latest_match_placement",
            "latest_match_mode",
            "latest_match_team",
            "latest_match_map",
            "latest_match_allies_score",
            "latest_match_axis_score",
        }
        values = {key: value for key, value in values.items() if key in safe_keys}
        attrs = {
            "source": attrs.get("source", "official_api"),
            "generated_at": attrs.get("generated_at"),
            "latest_match_id": None,
            "latest_match_relative_time": None,
            "latest_match_detail_available": False,
        }
        return values, attrs


def catalog():
    """Return selected Vuis fields and optional diagnostics."""
    rows = json.loads(
        Path(__file__).with_name("vuis_entities.json").read_text(encoding="utf-8")
    )
    translations = json.loads(Path(__file__).with_name("strings.json").read_text(encoding="utf-8"))
    for row in rows:
        if "name" not in row:
            row["name"] = (
                translations.get("entity", {})
                .get("sensor" if row.get("platform") != "binary_sensor" else "binary_sensor", {})
                .get(row["key"], {})
                .get("name", row["key"].replace("_", " ").title())
            )
    return rows


def selected(entry, row):
    """Respect explicit user selections; default to all supported Vuis data."""
    if row.get("diagnostic"):
        return False
    configured = entry.options.get("enabled_metrics")
    return row["key"] in configured if configured is not None else True


def create_official_runtime(hass, entry, rows):
    """Create only selected endpoint coordinators and their prerequisites."""
    endpoints = {row["endpoint"] for row in rows if selected(entry, row)}
    if "vuis_brigade" in endpoints:
        endpoints.add("vuis_profile")
    session = async_get_clientsession(hass)
    client = VuisClient(session)
    official_api = OfficialApi(
        session,
        entry.options.get("api_base_url", entry.data.get("api_base_url", DEFAULT_URL)),
        entry.options.get("api_key", entry.data.get("api_key", "")),
    )
    runtime = {}
    for endpoint in ("vuis_profile", "vuis_matches", "vuis_brigade"):
        if endpoint in endpoints:
            runtime[endpoint] = VuisCoordinator(
                hass, entry, endpoint, client, official_api, runtime
            )
    return runtime
