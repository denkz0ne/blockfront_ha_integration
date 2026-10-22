"""BlockFront public statistics integration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .const import DOMAIN

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import BlockFrontConfigEntry


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Serve the bundled rank images to Home Assistant's frontend."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("static_paths_registered"):
        assets_path = Path(__file__).parent / "assets"
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(
                    "/api/blockfront/icons",
                    str(assets_path),
                    cache_headers=True,
                )
            ]
        )
        domain_data["static_paths_registered"] = True
    if not domain_data.get("dataset_service_registered"):
        import voluptuous as vol

        async def _get_dataset(call):
            registry = er.async_get(hass)
            entity = registry.async_get(call.data["entity_id"])
            if entity is None:
                raise HomeAssistantError("Entity is not registered")
            entry = hass.config_entries.async_get_entry(entity.config_entry_id)
            runtime = getattr(entry, "runtime_data", None) if entry is not None else None
            if entry is None or entry.domain != DOMAIN or runtime is None:
                raise HomeAssistantError("Entity does not belong to a loaded BlockFront entry")
            dataset = call.data["dataset"]
            coordinator = runtime.coordinators[dataset]
            data = coordinator.data or {}
            return {
                "dataset": dataset,
                "value": data.get("value"),
                "source_timestamp": (data.get("value") or {}).get("source_timestamp")
                if isinstance(data.get("value"), dict)
                else None,
                "last_attempt": coordinator.last_attempt_at.isoformat()
                if coordinator.last_attempt_at
                else data.get("last_attempt"),
                "last_successful_update": data.get("last_successful_update"),
                "stale": data.get("stale", True),
                "error": data.get("last_error"),
            }

        hass.services.async_register(
            DOMAIN,
            "get_dataset",
            _get_dataset,
            schema=vol.Schema(
                {
                    vol.Required("entity_id"): cv.entity_id,
                    vol.Required("dataset"): vol.In(
                        (
                            "profile",
                            "matches",
                            "analytics",
                            "history",
                            "archive",
                            "global",
                            "online",
                            "status",
                        )
                    ),
                }
            ),
            supports_response=SupportsResponse.ONLY,
        )
        domain_data["dataset_service_registered"] = True
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate saved API-key field names without retaining provider branding."""
    data = dict(entry.data)
    options = dict(entry.options)
    legacy_keys = {
        key
        for store in (data, options)
        for key in store
        if key.endswith("_api_key") and key != "api_key"
    }
    if "api_key" not in options and "api_key" not in data:
        for store in (options, data):
            legacy_key = next((key for key in legacy_keys if key in store), None)
            if legacy_key is not None:
                store["api_key"] = store[legacy_key]
                break
    for store in (data, options):
        for key in legacy_keys:
            store.pop(key, None)
    hass.config_entries.async_update_entry(entry, data=data, options=options, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BlockFrontConfigEntry) -> bool:
    """Set up a BlockFront player and its independently polled sensor groups."""
    from .config_flow import async_reload_entry
    from .const import MIN_INTERVALS, PLATFORMS, UPDATE_INTERVALS
    from .coordinator import create_runtime, update_presence
    from .progression import COUNTERS, ProgressionStore

    removed_mode_sensors = {
        "cloud_bootcamp_players",
        "cloud_domination_players",
        "cloud_offensive_players",
        "cloud_defusal_players",
        "cloud_team_deathmatch_players",
        "cloud_gun_game_players",
        "cloud_free_for_all_players",
        "cloud_infected_players",
        "cloud_trouble_town_players",
    }
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if any(entity.unique_id.endswith(f"_{key}") for key in removed_mode_sensors):
            registry.async_remove(entity.entity_id)

    runtime = create_runtime(hass, entry)
    entry.runtime_data = runtime
    if runtime.presence_entity:
        current = hass.states.get(runtime.presence_entity)
        if current is not None:
            update_presence(runtime, current.state)

        async def _wake_player_data() -> None:
            for group in ("profile", "matches", "analytics", "history", "archive"):
                coordinator = runtime.coordinators[group]
                last_attempt = coordinator.last_attempt_at
                minimum = MIN_INTERVALS[UPDATE_INTERVALS[group]]
                if last_attempt is None or (
                    datetime.now(UTC) - last_attempt
                ).total_seconds() >= minimum:
                    await coordinator.async_refresh()

        def _schedule_cooldown_check() -> None:
            cooldown = runtime.presence_tracker.cooldown.total_seconds()

            @callback
            def _cooldown_finished(_now) -> None:
                state = hass.states.get(runtime.presence_entity)
                if state is not None:
                    previous = runtime.presence
                    update_presence(runtime, state.state)
                    if previous is not runtime.presence and runtime.presence.value == "active":
                        hass.async_create_task(_wake_player_data())
                    elif (
                        previous.value == "cooldown"
                        and runtime.presence.value == "inactive"
                        and runtime.postgame_refresh_due
                    ):
                        runtime.postgame_refresh_due = False

                        async def _reconcile_post_game() -> None:
                            await runtime.coordinators["profile"].async_refresh()
                            await runtime.coordinators["matches"].async_refresh()

                        hass.async_create_task(_reconcile_post_game())

            entry.async_on_unload(async_call_later(hass, cooldown, _cooldown_finished))

        @callback
        def _presence_changed(event) -> None:
            new_state = event.data.get("new_state")
            if new_state is not None:
                previous = runtime.presence
                update_presence(runtime, new_state.state)
                if previous is not runtime.presence and runtime.presence.value == "active":
                    hass.async_create_task(_wake_player_data())
                elif runtime.presence.value == "cooldown":
                    _schedule_cooldown_check()

        entry.async_on_unload(
            async_track_state_change_event(hass, [runtime.presence_entity], _presence_changed)
        )

    for group in (
        "profile",
        "matches",
        "status",
        "online",
        "analytics",
        "history",
        "global",
        "archive",
    ):
        coordinator = runtime.coordinators[group]
        if group in {"profile", "matches", "analytics", "history", "archive"}:
            if coordinator.update_interval is None:
                continue
        await coordinator.async_refresh()

    progression = ProgressionStore(hass, entry.unique_id or entry.entry_id)
    await progression.async_load()
    profile = (runtime.coordinators["profile"].data or {}).get("value", {})
    matches = (runtime.coordinators["matches"].data or {}).get("value", {}).get("matches", [])
    if isinstance(profile, dict):
        if progression.is_new_install:
            progression.seed_profile(profile)
            runtime.progression = {key: None for key in COUNTERS}
        else:
            runtime.progression = progression.observe_profile(profile)
    if isinstance(matches, list):
        if progression.is_new_install:
            progression.seed_matches(matches)
        else:
            await progression.observe_matches(hass, matches)
    await progression.async_save()

    @callback
    def _profile_updated() -> None:
        current = (runtime.coordinators["profile"].data or {}).get("value", {})
        if isinstance(current, dict):
            runtime.progression = progression.observe_profile(current)
            hass.async_create_task(progression.async_save())
        if runtime.presence_entity:
            state = hass.states.get(runtime.presence_entity)
            if state is not None:
                update_presence(runtime, state.state)

    @callback
    def _matches_updated() -> None:
        current_matches = (
            (runtime.coordinators["matches"].data or {}).get("value", {}).get("matches", [])
        )
        if isinstance(current_matches, list):
            hass.async_create_task(progression.observe_matches(hass, current_matches))

    entry.async_on_unload(runtime.coordinators["profile"].async_add_listener(_profile_updated))
    entry.async_on_unload(runtime.coordinators["matches"].async_add_listener(_matches_updated))
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BlockFrontConfigEntry) -> bool:
    """Unload integration platforms."""
    from .const import PLATFORMS

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
