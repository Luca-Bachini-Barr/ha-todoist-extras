"""Config flow: paste the Todoist API token (Settings > Integrations > Developer)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import TodoistAuthError, TodoistClient, TodoistError
from .const import DOMAIN

TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)


class TodoistExtrasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a Todoist account."""

    VERSION = 1

    async def _check(self, token: str) -> tuple[dict[str, Any] | None, dict[str, str]]:
        client = TodoistClient(async_get_clientsession(self.hass), token)
        try:
            # Only the user is needed here; the full sync happens at setup.
            payload = await client.sync(resource_types=["user"])
        except TodoistAuthError:
            return None, {"base": "invalid_auth"}
        except TodoistError:
            return None, {"base": "cannot_connect"}
        user = payload.get("user") if isinstance(payload, dict) else None
        if not isinstance(user, dict) or not user.get("id"):
            # Without a user id we can't tell accounts apart; treat as a bad reply.
            return None, {"base": "cannot_connect"}
        return user, {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the API token and check it."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_API_TOKEN].strip()
            user, errors = await self._check(token)
            if user is not None:
                await self.async_set_unique_id(str(user.get("id") or "todoist"))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user.get("full_name") or user.get("email") or "Todoist",
                    data={CONF_API_TOKEN: token},
                )
        return self.async_show_form(
            step_id="user", data_schema=TOKEN_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """The token stopped working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new token for the same account."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_API_TOKEN].strip()
            user, errors = await self._check(token)
            if user is not None:
                await self.async_set_unique_id(str(user.get("id") or "todoist"))
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data={CONF_API_TOKEN: token}
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=TOKEN_SCHEMA, errors=errors
        )
