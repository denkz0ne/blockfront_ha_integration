"""Local progression deltas and restart-safe match event deduplication."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

COUNTERS = ("exp", "kills", "deaths", "total_games", "time_played", "head_shots")
MATCH_EVENT = "blockfront_new_match"


class ProgressionStore:
    """Persist the latest source snapshot and IDs already announced."""

    def __init__(self, hass: HomeAssistant, key: str) -> None:
        self._store = Store[dict[str, Any]](hass, 1, f"blockfront_progress_{key}")
        self.snapshot: dict[str, Any] | None = None
        self.match_ids: set[str] = set()
        self.is_new_install = True

    async def async_load(self) -> None:
        """Load persisted counters and event IDs."""
        stored = await self._store.async_load()
        self.is_new_install = stored is None
        data = stored or {}
        self.snapshot = data.get("snapshot") if isinstance(data.get("snapshot"), dict) else None
        ids = data.get("match_ids", [])
        self.match_ids = {str(value) for value in ids if isinstance(value, str)}

    async def async_save(self) -> None:
        """Persist bounded dedup state."""
        await self._store.async_save(
            {"snapshot": self.snapshot, "match_ids": sorted(self.match_ids)[-5000:]}
        )

    def observe_profile(self, profile: dict[str, Any]) -> dict[str, int | float | None]:
        """Compute deltas only for a distinct upstream capture marker."""
        marker = profile.get("source_timestamp")
        previous = self.snapshot
        if not isinstance(marker, str) or previous is None or previous.get("marker") == marker:
            return {key: None for key in COUNTERS}
        current = {key: profile.get(key) for key in COUNTERS}
        old_values = previous.get("values", {})
        deltas: dict[str, int | float | None] = {}
        prestige_changed = profile.get("prestige") != previous.get("prestige")
        for key, value in current.items():
            old = old_values.get(key) if isinstance(old_values, dict) else None
            if (
                (key == "exp" and prestige_changed)
                or isinstance(value, bool)
                or isinstance(old, bool)
                or not isinstance(value, (int, float))
                or not isinstance(old, (int, float))
                or value < old
            ):
                deltas[key] = None
            else:
                deltas[key] = value - old
        self.snapshot = {"marker": marker, "values": current, "prestige": profile.get("prestige")}
        return deltas

    def seed_profile(self, profile: dict[str, Any]) -> None:
        """Establish a first-install baseline without fabricating deltas."""
        marker = profile.get("source_timestamp")
        if isinstance(marker, str):
            self.snapshot = {
                "marker": marker,
                "values": {key: profile.get(key) for key in COUNTERS},
                "prestige": profile.get("prestige"),
            }

    def seed_matches(self, matches: list[dict[str, Any]]) -> None:
        """Record current IDs on first setup without replaying old games."""
        self.match_ids = {
            str(match.get("match_id", match.get("id")))
            for match in matches
            if isinstance(match.get("match_id", match.get("id")), (str, int))
            and not isinstance(match.get("match_id", match.get("id")), bool)
        }

    async def observe_matches(self, hass: HomeAssistant, matches: list[dict[str, Any]]) -> None:
        """Fire one bounded HA event for each new stable match ID."""
        new_ids: list[str] = []
        for match in matches:
            match_id = match.get("match_id", match.get("id"))
            if not isinstance(match_id, (str, int)) or isinstance(match_id, bool):
                continue
            stable_id = str(match_id)
            if stable_id not in self.match_ids:
                self.match_ids.add(stable_id)
                new_ids.append(stable_id)
                hass.bus.async_fire(
                    MATCH_EVENT,
                    {
                        "match_id": stable_id,
                        "ended_at": _event_value(match.get("ended_at")),
                        "map": _event_value(match.get("map")),
                        "mode": _event_value(match.get("game", match.get("mode"))),
                        "score": _event_value(match.get("score")),
                        "result": _event_value(match.get("result")),
                    },
                )
        if new_ids:
            self.match_ids = set(sorted(self.match_ids)[-5000:])
            await self.async_save()


def _event_value(value: Any) -> str | int | float | None:
    """Keep HA event fields scalar and bounded."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        return value[:128]
    if isinstance(value, (int, float)):
        return value
    return None
