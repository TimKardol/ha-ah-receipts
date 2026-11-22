"""Config flow for AH Kassabon.

Setting up needs nothing. Logging in to the AH account is optional and lives
under Configure: AH's login page hands back a one-time code, which the person
pastes here. Home Assistant never sees the password, only the login token.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .ah_search import LOGIN_URL, AhAuthError, AhSearchError, async_exchange_code, code_from_input
from .const import DOMAIN

CODE_SCHEMA = vol.Schema({vol.Required("code"): str})


async def _login(hass, user_input: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, str]]:
    code = code_from_input(user_input["code"])
    if not code:
        return None, {"code": "invalid_code"}
    try:
        return await async_exchange_code(async_get_clientsession(hass), code), {}
    except AhAuthError:
        return None, {"code": "invalid_code"}
    except AhSearchError:
        return None, {"base": "cannot_connect"}


class KassabonConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return KassabonOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="AH Kassabon", data={})
        return self.async_show_form(step_id="user")

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            tokens, errors = await _login(self.hass, user_input)
            if tokens:
                entry = self._get_reauth_entry()
                return self.async_update_reload_and_abort(entry, data={**entry.data, "account": tokens})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=CODE_SCHEMA,
            errors=errors,
            description_placeholders={"url": LOGIN_URL},
        )


class KassabonOptionsFlow(OptionsFlow):
    """Configure: log in to or out of the AH account."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self.config_entry.data.get("account"):
            return self.async_show_menu(step_id="init", menu_options=["login", "logout"])
        return await self.async_step_login()

    async def async_step_login(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            tokens, errors = await _login(self.hass, user_input)
            if tokens:
                self._save({**self.config_entry.data, "account": tokens})
                return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="login",
            data_schema=CODE_SCHEMA,
            errors=errors,
            description_placeholders={"url": LOGIN_URL},
        )

    async def async_step_logout(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._save({k: v for k, v in self.config_entry.data.items() if k != "account"})
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="logout")

    def _save(self, data: dict[str, Any]) -> None:
        entry = self.config_entry
        self.hass.config_entries.async_update_entry(entry, data=data)
        self.hass.config_entries.async_schedule_reload(entry.entry_id)
