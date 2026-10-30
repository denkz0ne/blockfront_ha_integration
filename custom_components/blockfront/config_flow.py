"""Public official API with optional authorized access."""

from uuid import UUID

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .official import DEFAULT_URL, PRIVATE, PUBLIC, OfficialApi, OfficialError, normalize_url
from .official_runtime import catalog, selected


class BlockFrontConfigFlow(ConfigFlow, domain="blockfront"):
    VERSION = 4

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                identity = str(UUID(user_input["player_uuid"]))
            except (ValueError, TypeError):
                errors["player_uuid"] = "invalid_player"
            try:
                url = normalize_url(user_input["api_base_url"])
            except ValueError:
                errors["api_base_url"] = "invalid_api_url"
            if not errors:
                api = OfficialApi(
                    async_get_clientsession(self.hass), url, user_input.get("api_key", "").strip()
                )
                try:
                    await api.get("player_count")
                    if api.api_key:
                        await api.get("player", uuid=identity)
                except OfficialError:
                    errors["base"] = "cannot_connect"
                else:
                    await self.async_set_unique_id(identity)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=user_input["username"],
                        data={
                            **user_input,
                            "player_uuid": identity,
                            "api_base_url": url,
                            "api_key": api.api_key,
                        },
                    )
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("username"): str,
                    vol.Required("player_uuid"): str,
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
                user_input["api_base_url"] = normalize_url(user_input["api_base_url"])
            except ValueError:
                errors["api_base_url"] = "invalid_api_url"
            saved_key = entry.options.get("api_key", entry.data.get("api_key", ""))
            new_key = user_input.pop("api_key", "").strip()
            remove_key = user_input.pop("remove_api_key", False)
            user_input["api_key"] = "" if remove_key else new_key or saved_key
            if not errors and new_key and not remove_key:
                try:
                    await OfficialApi(
                        async_get_clientsession(self.hass), user_input["api_base_url"], new_key
                    ).get("player", uuid=entry.data["player_uuid"])
                except OfficialError:
                    errors["base"] = "cannot_connect"
            if not errors:
                if "api_key" in entry.data:
                    self.hass.config_entries.async_update_entry(
                        entry, data={k: v for k, v in entry.data.items() if k != "api_key"}
                    )
                if new_key and not saved_key and not remove_key:
                    user_input["enabled_metrics"] = list(
                        dict.fromkeys(
                            [
                                *user_input.get("enabled_metrics", []),
                                *(
                                    r["key"]
                                    for r in rows
                                    if r["endpoint"] in {"player", "player_matches"}
                                ),
                            ]
                        )
                    )
                return self.async_create_entry(title="", data=user_input)
        enabled = entry.options.get(
            "enabled_metrics", [r["key"] for r in rows if selected(entry, r)]
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
                        {"value": r["key"], "label": f"{r.get('name', r['key'])} ({r['endpoint']})"}
                        for r in rows
                    ],
                )
            ),
            vol.Optional("selected_map", default=entry.options.get("selected_map", "")): str,
            vol.Required("selected_mode", default=entry.options.get("selected_mode", "dom")): str,
            vol.Required(
                "selected_team", default=entry.options.get("selected_team", "Allies")
            ): str,
        }
        for endpoint, default in {**PUBLIC, **PRIVATE}.items():
            schema[
                vol.Required(
                    f"{endpoint}_interval",
                    default=entry.options.get(f"{endpoint}_interval", default),
                )
            ] = vol.All(vol.Coerce(int), vol.Range(min=60, max=86400))
        return self.async_show_form(step_id="init", errors=errors, data_schema=vol.Schema(schema))
