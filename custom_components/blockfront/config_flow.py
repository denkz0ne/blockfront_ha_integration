"""Config and options flows for BlockFront."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ApiError, BlockFrontApi, PlayerNotFound, normalize_api_base_url
from .const import (
    CONF_API_BASE_URL,
    CONF_API_KEY,
    CONF_PLAYER_UUID,
    CONF_USERNAME,
    DEFAULT_OPTIONS,
    DOMAIN,
    MAX_INTERVAL_SECONDS,
    MIN_INTERVALS,
    OPTION_ACTIVITY_COOLDOWN,
    OPTION_ACTIVITY_ENTITY,
    OPTION_ACTIVITY_MATCH,
    OPTION_ADAPTIVE_MARGIN,
    OPTION_ADAPTIVE_POLLING,
    OPTION_IDLE_HEARTBEAT,
    OPTION_PRESENCE_MODE,
    OPTION_PROFILE_SOURCE,
    OPTION_MATCHES_SOURCE,
    SOURCE_BLOCKLYTICS,
    SOURCE_COMMUNITY,
)

_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,16}$")


class BlockFrontConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one public BlockFront player by username."""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        """Ask for a player name, then resolve it to a stable UUID."""
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            if not _USERNAME_PATTERN.fullmatch(username):
                errors[CONF_USERNAME] = "invalid_username"
            else:
                try:
                    api_base_url = normalize_api_base_url(user_input[CONF_API_BASE_URL])
                except (KeyError, ValueError):
                    errors[CONF_API_BASE_URL] = "invalid_api_url"
                else:
                    api_key = user_input.get(CONF_API_KEY, "").strip()
                    api = BlockFrontApi(
                        async_get_clientsession(self.hass),
                        api_key=api_key or None,
                        api_base_url=api_base_url,
                    )
                    try:
                        player_uuid = await api.async_resolve_player(username)
                    except PlayerNotFound:
                        errors["base"] = "invalid_player"
                    except ApiError:
                        errors["base"] = "cannot_connect"
                    else:
                        await self.async_set_unique_id(player_uuid)
                        self._abort_if_unique_id_configured()
                        entry_data = {
                            CONF_USERNAME: username,
                            CONF_PLAYER_UUID: player_uuid,
                            CONF_API_BASE_URL: api_base_url,
                        }
                        if api_key:
                            entry_data[CONF_API_KEY] = api_key
                        return self.async_create_entry(title=username, data=entry_data)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_API_BASE_URL): str,
                    vol.Optional(CONF_API_KEY, default=""): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> BlockFrontOptionsFlow:
        """Create the options flow for a config entry."""
        return BlockFrontOptionsFlow()


class BlockFrontOptionsFlow(OptionsFlow):
    """Configure each polling group independently."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> dict[str, Any]:
        """Show the private API URL, key, and validated polling intervals."""
        if user_input is not None:
            try:
                user_input[CONF_API_BASE_URL] = normalize_api_base_url(
                    user_input[CONF_API_BASE_URL]
                )
            except (KeyError, ValueError):
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(),
                    errors={CONF_API_BASE_URL: "invalid_api_url"},
                )
            saved_key = self.config_entry.options.get(CONF_API_KEY) or self.config_entry.data.get(
                CONF_API_KEY, ""
            )
            user_input[CONF_API_KEY] = user_input.get(CONF_API_KEY, "").strip() or saved_key
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(step_id="init", data_schema=self._schema())

    def _schema(self) -> vol.Schema:
        """Build settings schema while retaining existing values as defaults."""
        saved_url = self.config_entry.options.get(
            CONF_API_BASE_URL,
            self.config_entry.data.get(CONF_API_BASE_URL, ""),
        )
        schema: dict[vol.Marker, Any] = {
            vol.Required(CONF_API_BASE_URL, default=saved_url): str,
            vol.Optional(CONF_API_KEY, default=""): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
        for key, default in DEFAULT_OPTIONS.items():
            if key in {
                OPTION_ACTIVITY_ENTITY,
                OPTION_ACTIVITY_MATCH,
                OPTION_ACTIVITY_COOLDOWN,
                OPTION_IDLE_HEARTBEAT,
                OPTION_ADAPTIVE_POLLING,
                OPTION_ADAPTIVE_MARGIN,
                OPTION_PRESENCE_MODE,
                OPTION_PROFILE_SOURCE,
                OPTION_MATCHES_SOURCE,
            }:
                continue
            saved_value = self.config_entry.options.get(key, default)
            schema[vol.Required(key, default=saved_value)] = vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_INTERVALS[key], max=MAX_INTERVAL_SECONDS),
            )
        for source_key in (OPTION_PROFILE_SOURCE, OPTION_MATCHES_SOURCE):
            schema[vol.Required(source_key, default=self.config_entry.options.get(source_key, SOURCE_BLOCKLYTICS))] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[SOURCE_BLOCKLYTICS, SOURCE_COMMUNITY],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        entity_default = self.config_entry.options.get(OPTION_ACTIVITY_ENTITY)
        entity_marker = (
            vol.Optional(OPTION_ACTIVITY_ENTITY, default=entity_default)
            if entity_default
            else vol.Optional(OPTION_ACTIVITY_ENTITY)
        )
        schema[entity_marker] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
        )
        schema[vol.Optional(OPTION_ACTIVITY_MATCH, default="BlockFront")] = str
        schema[
            vol.Required(
                OPTION_ACTIVITY_COOLDOWN,
                default=self.config_entry.options.get(OPTION_ACTIVITY_COOLDOWN, 30),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=0, max=240))
        schema[
            vol.Required(
                OPTION_IDLE_HEARTBEAT,
                default=self.config_entry.options.get(OPTION_IDLE_HEARTBEAT, 60),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=15, max=360))
        schema[
            vol.Required(
                OPTION_ADAPTIVE_POLLING,
                default=self.config_entry.options.get(OPTION_ADAPTIVE_POLLING, True),
            )
        ] = selector.BooleanSelector()
        schema[
            vol.Required(
                OPTION_ADAPTIVE_MARGIN,
                default=self.config_entry.options.get(OPTION_ADAPTIVE_MARGIN, 10),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=0, max=50))
        schema[
            vol.Required(
                OPTION_PRESENCE_MODE,
                default=self.config_entry.options.get(OPTION_PRESENCE_MODE, "auto"),
            )
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=["auto", "force_active", "force_idle"],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
        return vol.Schema(schema)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry after options change."""
    await hass.config_entries.async_reload(entry.entry_id)
