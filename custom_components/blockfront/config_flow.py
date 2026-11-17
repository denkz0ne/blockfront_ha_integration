"""Config flow: resolve the configured username publicly and keep UUID optional."""

from uuid import UUID

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .official import DEFAULT_URL, OfficialApi, OfficialError, normalize_url
from .official_runtime import DEFAULT_INTERVALS, catalog, selected
from .vuis import VuisError, resolve_player, validate_username


class BlockFrontConfigFlow(ConfigFlow, domain="blockfront"):
    VERSION = 5

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                username = validate_username(user_input.get("username", ""))
            except ValueError:
                errors["username"] = "invalid_username"
                username = ""
            identity = None
            supplied_uuid = str(user_input.get("player_uuid") or "").strip()
            if supplied_uuid:
                try:
                    identity = str(UUID(supplied_uuid))
                except (ValueError, TypeError):
                    errors["player_uuid"] = "invalid_player"
            try:
                url = normalize_url(user_input.get("api_base_url") or DEFAULT_URL)
            except ValueError:
                errors["api_base_url"] = "invalid_api_url"
                url = DEFAULT_URL

            if not errors:
                session = async_get_clientsession(self.hass)
                try:
                    resolved_name, resolved_uuid = await resolve_player(session, username)
                except VuisError as err:
                    errors["base"] = (
                        "invalid_player"
                        if "not found" in str(err).casefold()
                        or "did not return a player profile" in str(err).casefold()
                        else "cannot_connect"
                    )
                else:
                    if identity and identity != resolved_uuid:
                        errors["player_uuid"] = "invalid_player"
                    else:
                        identity = resolved_uuid
                        api_key = str(user_input.get("api_key") or "").strip()
                        if api_key:
                            try:
                                await OfficialApi(session, url, api_key).get(
                                    "player", uuid=identity
                                )
                            except OfficialError:
                                errors["base"] = "invalid_api_key"
                        if not errors:
                            await self.async_set_unique_id(identity)
                            self._abort_if_unique_id_configured()
                            return self.async_create_entry(
                                title=resolved_name,
                                data={
                                    "username": resolved_name,
                                    "player_uuid": identity,
                                    "api_base_url": url,
                                    "api_key": api_key,
                                },
                            )

        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("username"): str,
                    vol.Optional("player_uuid", default=""): str,
                    vol.Required("api_base_url", default=DEFAULT_URL): str,
                    vol.Optional("api_key", default=""): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BlockFrontOptionsFlow()


class BlockFrontOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        entry = self.config_entry
        rows = await self.hass.async_add_executor_job(catalog)
        errors = {}
        if user_input is not None:
            try:
                user_input["api_base_url"] = normalize_url(
                    user_input.get("api_base_url") or DEFAULT_URL
                )
            except ValueError:
                errors["api_base_url"] = "invalid_api_url"
            saved_key = entry.options.get("api_key") or entry.data.get("api_key", "")
            new_key = str(user_input.pop("api_key", "") or "").strip()
            remove_key = user_input.pop("remove_api_key", False)
            user_input["api_key"] = "" if remove_key else new_key or saved_key
            if not errors and new_key and not remove_key:
                try:
                    await OfficialApi(
                        async_get_clientsession(self.hass),
                        user_input["api_base_url"],
                        new_key,
                    ).get("player", uuid=entry.data["player_uuid"])
                except OfficialError:
                    errors["base"] = "invalid_api_key"
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        enabled = entry.options.get(
            "enabled_metrics", [row["key"] for row in rows if selected(entry, row)]
        )
        schema = {
            vol.Required(
                "api_base_url",
                default=entry.options.get(
                    "api_base_url", entry.data.get("api_base_url", DEFAULT_URL)
                ),
            ): str,
            vol.Optional("api_key", default=""): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Optional("remove_api_key", default=False): bool,
            vol.Required("enabled_metrics", default=enabled): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    multiple=True,
                    options=[
                        {"value": row["key"], "label": f"{row['name']} ({row['endpoint']})"}
                        for row in rows
                    ],
                )
            ),
        }
        for endpoint, default in DEFAULT_INTERVALS.items():
            schema[
                vol.Required(
                    f"{endpoint}_interval",
                    default=entry.options.get(f"{endpoint}_interval", default),
                )
            ] = vol.All(vol.Coerce(int), vol.Range(min=60, max=86400))
        return self.async_show_form(step_id="init", errors=errors, data_schema=vol.Schema(schema))
