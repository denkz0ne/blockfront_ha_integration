"""Snapshot progression and match event tests."""

from typing import Any

import pytest

from custom_components.blockfront.progression import MATCH_EVENT, ProgressionStore


def make_store(snapshot: dict[str, Any] | None = None) -> ProgressionStore:
    store = ProgressionStore.__new__(ProgressionStore)
    store.snapshot = snapshot
    store.match_ids = set()
    return store


def test_deltas_require_a_distinct_source_marker_and_do_not_call_them_daily() -> None:
    store = make_store(
        {
            "marker": "2026-10-22T10:00:00Z",
            "values": {
                "exp": 100,
                "kills": 20,
                "deaths": 5,
                "total_games": 8,
                "time_played": 3600,
                "head_shots": 4,
            },
            "prestige": 0,
        }
    )
    profile = {
        "source_timestamp": "2026-10-22T16:00:00Z",
        "exp": 160,
        "kills": 23,
        "deaths": 6,
        "total_games": 9,
        "time_played": 4200,
        "head_shots": 5,
        "prestige": 0,
    }
    assert store.observe_profile(profile)["kills"] == 3
    assert store.observe_profile(profile)["kills"] is None


def test_prestige_or_counter_reset_makes_only_affected_deltas_unknown() -> None:
    store = make_store(
        {
            "marker": "before",
            "values": {
                "exp": 100,
                "kills": 20,
                "deaths": 5,
                "total_games": 8,
                "time_played": 10,
                "head_shots": 4,
            },
            "prestige": 0,
        }
    )
    deltas = store.observe_profile(
        {
            "source_timestamp": "after",
            "exp": 5,
            "kills": 22,
            "deaths": 5,
            "total_games": 8,
            "time_played": 11,
            "head_shots": 4,
            "prestige": 1,
        }
    )
    assert deltas["exp"] is None
    assert deltas["kills"] == 2
    assert deltas["time_played"] == 1


@pytest.mark.asyncio
async def test_new_match_event_is_stable_and_bounded() -> None:
    fired: list[tuple[str, dict[str, Any]]] = []

    class Bus:
        def async_fire(self, event_type: str, data: dict[str, Any]) -> None:
            fired.append((event_type, data))

    class Hass:
        bus = Bus()

    store = make_store()

    async def save() -> None:
        return None

    store.async_save = save  # type: ignore[method-assign]
    await store.observe_matches(
        Hass(),
        [
            {
                "match_id": "match-1",
                "ended_at": "x" * 500,
                "map": "bridge",
                "game": "domination",
                "score": 15,
                "result": "win",
            }
        ],
    )
    await store.observe_matches(Hass(), [{"match_id": "match-1", "map": "bridge"}])
    assert len(fired) == 1
    assert fired[0][0] == MATCH_EVENT
    assert len(fired[0][1]["ended_at"]) == 128
