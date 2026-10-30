"""Official endpoint coordinators and a single entity catalog."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .official import DEFAULT_URL, PRIVATE, PUBLIC, OfficialApi, OfficialError, values_for

LOGGER = logging.getLogger(__name__)


def catalog():
    """Return stable legacy metric identities and explicitly new official metrics."""
    rows = json.loads(
        Path(__file__).with_name("official_entities.json").read_text(encoding="utf-8")
    )
    rows.append(
        {
            "key": "bootcamp",
            "endpoint": "player",
            "name": "Completed Bootcamp",
            "platform": "binary_sensor",
        }
    )
    translations = json.loads(Path(__file__).with_name("strings.json").read_text(encoding="utf-8"))
    for row in rows:
        if "name" not in row:
            row["name"] = (
                translations.get("entity", {})
                .get("sensor", {})
                .get(row["key"], {})
                .get("name", row["key"].replace("_", " ").title())
            )
    new = [
        ("monthly_score", "scoreboard", "Monthly score", "points"),
        ("monthly_rank", "scoreboard", "Monthly position", None),
        ("monthly_reset", "scoreboard", "Monthly reset", None),
        ("official_map_count", "map_stats", "Maps with statistics", "maps"),
        ("brigade_members", "clan", "Brigade members", "players"),
        ("brigade_founded", "clan", "Brigade founded", None),
    ]
    for key in ("matches", "wins", "kills", "deaths", "kd", "score", "win_rate"):
        new.append(
            (f"map_{key}", "map_stats", f"Selected map {key}", "%" if key == "win_rate" else None)
        )
    for key in ("ratings", "average", *(f"stars_{n}" for n in range(6))):
        new.append((f"map_{key}", "map_ratings", f"Selected map {key}", None))
    for key in ("axisScore", "alliedScore", "axisCasualties", "alliedCasualties"):
        new.append((f"match_{key}", "match", f"Latest match {key}", None))
    for key in ("count", "average", *(f"stars_{n}" for n in range(6))):
        new.append((f"team_rating_{key}", "map_ratings", f"Selected team rating {key}", None))
    for key in ("score", "rank"):
        new.append((f"brigade_monthly_{key}", "clan", f"Brigade monthly {key}", None))
    for class_id in range(10):
        rows.append(
            {
                "key": f"class_exp_{class_id}",
                "endpoint": "player",
                "name": f"Class {class_id} experience",
                "native_unit_of_measurement": "XP",
                "state_class": "total_increasing",
            }
        )
    for key, endpoint, name, unit in new:
        row = {"key": key, "endpoint": endpoint, "name": name}
        if unit:
            row["native_unit_of_measurement"] = unit
        if key in {"monthly_reset", "brigade_founded"}:
            row["device_class"] = "timestamp"
        elif key not in {"map_kd", "map_average"}:
            row["state_class"] = "measurement"
        rows.append(row)
    for endpoint in (*PUBLIC, *PRIVATE):
        rows.append(
            {
                "key": f"official_{endpoint}_status",
                "endpoint": endpoint,
                "name": f"Official {endpoint} availability",
                "diagnostic": True,
            }
        )
    return rows


def selected(entry, row):
    """Private metrics need a key; optional map/brigade/detail metrics default off."""
    if row["endpoint"] in PRIVATE and not entry.options.get("api_key", entry.data.get("api_key")):
        return False
    configured = entry.options.get("enabled_metrics")
    if configured is not None:
        return row["key"] in configured
    return row["endpoint"] not in {"clan", "match"} and not row["key"].startswith(
        ("map_", "team_rating_")
    )


class EndpointCoordinator(DataUpdateCoordinator):
    """Independent failures and intervals, shared transport throttling."""

    def __init__(self, hass, entry, api, endpoint, runtime):
        self.entry = entry
        self.api = api
        self.endpoint = endpoint
        self.runtime = runtime
        interval = entry.options.get(f"{endpoint}_interval", {**PUBLIC, **PRIVATE}[endpoint])
        super().__init__(
            hass,
            LOGGER,
            name=f"BlockFront {endpoint}",
            config_entry=entry,
            update_interval=timedelta(seconds=interval),
        )

    async def _async_update_data(self):
        params = {}
        identity = self.entry.data["player_uuid"]
        if self.endpoint in {"player", "player_matches", "scoreboard"}:
            params["uuid"] = identity
        if self.endpoint == "scoreboard":
            params["board"] = "players"
        if self.endpoint in {"map_stats", "map_ratings"}:
            selected_map = self.entry.options.get("selected_map", "")
            if selected_map:
                params["map"] = selected_map
        if self.endpoint in {"clan", "match"}:
            prerequisite = "player" if self.endpoint == "clan" else "player_matches"
            parent = self.runtime.get(prerequisite)
            if parent is not None:
                await parent.async_request_refresh()
            if parent is None or not parent.last_update_success or not parent.data:
                raise UpdateFailed("Required official dataset is unavailable")
            raw = parent.data["raw"]
            if self.endpoint == "clan":
                clan = raw.get("clan")
                tag = clan.get("tag") if isinstance(clan, dict) else None
                if not tag:
                    return {"values": {}, "attributes": {}, "raw": {}}
                params["tag"] = tag
            else:
                matches = raw.get("matches", [])
                latest = max(matches, key=lambda r: r.get("endedAt", 0)) if matches else {}
                if not latest.get("matchId"):
                    return {"values": {}, "attributes": {}, "raw": {}}
                params["id"] = latest["matchId"]
        try:
            payload = await self.api.get(self.endpoint, **params)
            values, attributes = values_for(
                self.endpoint,
                payload,
                selected_map=self.entry.options.get("selected_map", ""),
                mode=self.entry.options.get("selected_mode", "dom"),
                team=self.entry.options.get("selected_team", "Allies"),
            )
        except OfficialError as err:
            if err.status in (401, 403):
                self.data = None
            raise UpdateFailed(str(err)) from err
        attributes["last_successful_update"] = datetime.now(UTC).isoformat()
        return {"values": values, "attributes": attributes, "raw": payload}


def create_official_runtime(hass, entry, rows):
    """Only enabled endpoints and their prerequisites get polled."""
    api = OfficialApi(
        async_get_clientsession(hass),
        entry.options.get("api_base_url", entry.data.get("api_base_url", DEFAULT_URL)),
        entry.options.get("api_key", entry.data.get("api_key", "")),
    )
    endpoints = {row["endpoint"] for row in rows if selected(entry, row)}
    if "clan" in endpoints:
        endpoints.add("player")
    if "match" in endpoints:
        endpoints.add("player_matches")
    runtime = {}
    for endpoint in (*PUBLIC, *PRIVATE):
        if endpoint in endpoints:
            runtime[endpoint] = EndpointCoordinator(hass, entry, api, endpoint, runtime)
    return runtime
